"""Builds the neofetch-style stats card as a hand-written SVG (no rasterization).

Layout: a spinning "V" logo (Vulcanis branding) on the left, dot-leader
"label ..... value" info fields on the right grouped into
fastfetch/neofetch-style sections. Every section (including the
"user@github" header) uses the same "title + dashes" divider, and every
value is right-anchored to the same column so values always line up flush
against the right edge, regardless of label length. Lines/the logo animate
with CSS (a staggered fade-in for lines, a scaleX oscillation on the logo
that fakes a spin around its vertical axis). Output is fully deterministic
(no timestamps or randomness) so identical stats always produce
byte-identical SVGs -- that is what keeps the GitHub Action idempotent (git
has nothing to commit when nothing actually changed).
"""
import textwrap
from xml.sax.saxutils import escape

FONT_STACK = "'Cascadia Code','Fira Code',Consolas,'Liberation Mono',Menlo,monospace"

THEMES = {
    "dark": {
        "bg": "#282a36",
        "border": "#6272a4",
        "prompt_user": "#50fa7b",
        "prompt_host": "#50fa7b",
        "label": "#8be9fd",
        "value": "#f8f8f2",
        "muted": "#6272a4",
        "logo": "#bd93f9",
        "logo_shadow": "#5d4a80",
        "logo_light": "#e2d4fc",
        "section": "#ff79c6",
        "add": "#50fa7b",
        "del": "#ff5555",
    },
    "light": {
        "bg": "#fdf6e3",
        "border": "#d0d7de",
        "prompt_user": "#1a7f37",
        "prompt_host": "#1a7f37",
        "label": "#0969da",
        "value": "#24292f",
        "muted": "#afb8c1",
        "logo": "#8250df",
        "logo_shadow": "#4a2f8a",
        "logo_light": "#c9b3f5",
        "section": "#cf222e",
        "add": "#1a7f37",
        "del": "#cf222e",
    },
}

INFO_FONT_SIZE = 12
INFO_CHAR_WIDTH = INFO_FONT_SIZE * 0.6
INFO_LINE_HEIGHT = 17
SPACER_HEIGHT = 8
HR_HEIGHT = 10
MIN_DOTS = 3

PROMPT_FONT_SIZE = 14
PROMPT_CHAR_WIDTH = PROMPT_FONT_SIZE * 0.6

LOGO_BOX_WIDTH = 170
LOGO_FONT_SIZE = 12
LOGO_CHAR_WIDTH = LOGO_FONT_SIZE * 0.62
LOGO_LINE_HEIGHT = LOGO_FONT_SIZE * 1.15
LOGO_CHAR = "█"
LOGO_HEIGHT_ROWS = 11
LOGO_WIDTH_COLS = 21
LOGO_STROKE = 3
LOGO_DEPTH = 5


def _build_logo_rows():
    """A bold 'V' drawn as a block-character grid (ascii-art style) instead
    of a smooth vector stroke, to match the terminal aesthetic."""
    rows = []
    for r in range(LOGO_HEIGHT_ROWS):
        left = r
        right = (LOGO_WIDTH_COLS - 1) - r - (LOGO_STROKE - 1)
        cells = [" "] * LOGO_WIDTH_COLS
        for k in range(LOGO_STROKE):
            if 0 <= left + k < LOGO_WIDTH_COLS:
                cells[left + k] = LOGO_CHAR
            if 0 <= right + k < LOGO_WIDTH_COLS:
                cells[right + k] = LOGO_CHAR
        rows.append("".join(cells))
    return rows

LEFT_MARGIN = 24
TOP_MARGIN = 30
BOTTOM_PADDING = 20
DIVIDER_GAP = 24
INFO_BLOCK_WIDTH = 420
COLUMN_GAP = 24


def _esc(text):
    return escape(str(text))


def _fmt_int(n):
    return f"{n:,}"


def _leader_dots(label, value, label_x, value_end_x):
    """How many '.' characters bridge label -> value so the value always
    ends flush at `value_end_x`, regardless of label/value length."""
    label_w = len(label) * INFO_CHAR_WIDTH
    value_w = len(value) * INFO_CHAR_WIDTH
    gap_px = (value_end_x - label_x) - label_w - value_w - 2 * INFO_CHAR_WIDTH
    return max(MIN_DOTS, round(gap_px / INFO_CHAR_WIDTH))


def _fits(label, value, label_x, value_end_x):
    label_w = len(label) * INFO_CHAR_WIDTH
    value_w = len(value) * INFO_CHAR_WIDTH
    min_dots_w = MIN_DOTS * INFO_CHAR_WIDTH
    return label_x + label_w + 2 * INFO_CHAR_WIDTH + min_dots_w + value_w <= value_end_x


class _RowBuilder:
    def __init__(self):
        self.rows = []
        self._delay = 0.0

    def _next_delay(self):
        d = self._delay
        self._delay += 0.045
        return round(d, 3)

    def prompt(self, user, host):
        self.rows.append({"kind": "prompt", "user": user, "host": host, "delay": self._next_delay()})

    def spacer(self):
        self.rows.append({"kind": "spacer"})

    def section(self, title):
        self.rows.append({"kind": "section", "title": title, "delay": self._next_delay()})

    def text(self, label, value):
        self.rows.append({"kind": "text", "label": label, "value": value, "delay": self._next_delay()})

    def stat_row(self, left_label, left_value, right_label=None, right_value=None):
        self.rows.append(
            {
                "kind": "stat_row",
                "left_label": left_label,
                "left_value": left_value,
                "right_label": right_label,
                "right_value": right_value,
                "delay": self._next_delay(),
            }
        )

    def loc_row(self, net, added, deleted):
        self.rows.append(
            {"kind": "loc_row", "net": net, "added": added, "deleted": deleted, "delay": self._next_delay()}
        )


def _build_rows(stats):
    rb = _RowBuilder()

    rb.prompt(stats["username"], "github")

    rb.text("OS", stats["os_list"])
    rb.text("Uptime", stats["uptime"])
    rb.text("IDE", stats["ide"])
    rb.spacer()

    rb.text("Languages.Programming", ", ".join(stats["languages_programming"]))
    rb.text("Languages.Computer", ", ".join(stats["languages_computer"]))
    rb.text("Languages.Real", ", ".join(stats["languages_real"]))
    rb.spacer()

    rb.section("Hobbies")
    rb.text("Hobbies.Software", stats["hobby_software"])
    rb.text("Hobbies.Real", stats["hobby_real"])
    rb.spacer()

    rb.section("Contact")
    rb.text("Email", stats["contact_email"])
    rb.text("LinkedIn", stats["contact_linkedin"])
    rb.text("Discord", stats["contact_discord"])
    rb.spacer()

    rb.section("GitHub Stats")
    repos_value = f"{_fmt_int(stats['repos_owned'])} {{Contrib: {_fmt_int(stats['repos_contributed'])}}}"
    rb.stat_row("Repos", repos_value, "Stars", _fmt_int(stats["stars"]))
    rb.stat_row("Commits", _fmt_int(stats["commits"]), "Followers", _fmt_int(stats["followers"]))
    net_loc = stats["loc_added"] - stats["loc_deleted"]
    rb.loc_row(net_loc, stats["loc_added"], stats["loc_deleted"])

    return rb.rows


def _prepare_text_row(row, info_x, info_right_edge):
    label, value = row["label"], row["value"]
    if _fits(label, value, info_x, info_right_edge):
        row["dots"] = "." * _leader_dots(label, value, info_x, info_right_edge)
        row["value_lines"] = [value]
        row["flush"] = True
        return

    # Value too long even with minimal dots -> wrap it, left-aligned.
    row["dots"] = "." * MIN_DOTS
    prefix_chars = len(label) + MIN_DOTS + 2
    value_x = info_x + prefix_chars * INFO_CHAR_WIDTH
    max_chars = max(10, int((info_right_edge - value_x - 4) / INFO_CHAR_WIDTH))
    row["value_lines"] = textwrap.wrap(value, width=max_chars, break_long_words=False) or [""]
    row["value_x"] = value_x
    row["flush"] = False


def render_svg(stats, mode="dark"):
    theme = THEMES[mode]
    rows = _build_rows(stats)

    info_x = LEFT_MARGIN + LOGO_BOX_WIDTH + DIVIDER_GAP
    info_right_edge = info_x + INFO_BLOCK_WIDTH
    width = round(info_right_edge + LEFT_MARGIN)

    # Left column carries longer values ("42 {Contrib: 17}", LOC totals),
    # right column only ever holds short numbers (stars, followers) -- so
    # split the space unevenly instead of 50/50.
    col1_width = (INFO_BLOCK_WIDTH - COLUMN_GAP) * 0.62
    col1_x, col1_end = info_x, info_x + col1_width
    col2_x, col2_end = info_x + col1_width + COLUMN_GAP, info_right_edge

    for row in rows:
        if row["kind"] == "text":
            _prepare_text_row(row, info_x, info_right_edge)

    parts = []
    y = TOP_MARGIN
    row_heights = []
    for row in rows:
        if row["kind"] == "spacer":
            row_heights.append(SPACER_HEIGHT)
        elif row["kind"] == "text":
            row_heights.append(INFO_LINE_HEIGHT * len(row["value_lines"]))
        else:
            row_heights.append(INFO_LINE_HEIGHT)

    content_height = sum(row_heights)
    height = round(content_height + TOP_MARGIN + BOTTOM_PADDING)

    # --- "V" logo (left column), drawn as ascii-art block chars with a
    # dark offset copy behind it to fake a 3D extruded/beveled block. ---
    logo_rows = _build_logo_rows()
    logo_w = LOGO_WIDTH_COLS * LOGO_CHAR_WIDTH
    logo_h = LOGO_HEIGHT_ROWS * LOGO_LINE_HEIGHT
    logo_x = LEFT_MARGIN + (LOGO_BOX_WIDTH - logo_w) / 2
    logo_y = TOP_MARGIN + (content_height - logo_h) / 2

    logo_lines = []
    ly = LOGO_LINE_HEIGHT
    for logo_row in logo_rows:
        logo_lines.append(f'<text x="0" y="{ly:.1f}" xml:space="preserve">{_esc(logo_row)}</text>')
        ly += LOGO_LINE_HEIGHT
    logo_body = "".join(logo_lines)

    shadow_x, shadow_y = logo_x + LOGO_DEPTH, logo_y + LOGO_DEPTH
    highlight_x, highlight_y = logo_x - LOGO_DEPTH * 0.4, logo_y - LOGO_DEPTH * 0.4
    parts.append(
        f'<g transform="translate({shadow_x:.1f},{shadow_y:.1f})" '
        f'fill="{theme["logo_shadow"]}" style="font-family:{FONT_STACK};font-size:{LOGO_FONT_SIZE}px;">'
        f"{logo_body}</g>"
    )
    parts.append(
        f'<g transform="translate({highlight_x:.1f},{highlight_y:.1f})" fill-opacity="0.55" '
        f'fill="{theme["logo_light"]}" style="font-family:{FONT_STACK};font-size:{LOGO_FONT_SIZE}px;">'
        f"{logo_body}</g>"
    )
    parts.append(
        f'<g transform="translate({logo_x:.1f},{logo_y:.1f})" '
        f'fill="{theme["logo"]}" style="font-family:{FONT_STACK};font-size:{LOGO_FONT_SIZE}px;">'
        f"{logo_body}</g>"
    )

    divider_x = LEFT_MARGIN + LOGO_BOX_WIDTH + DIVIDER_GAP / 2
    parts.append(
        f'<line x1="{divider_x:.1f}" y1="{TOP_MARGIN - 6}" x2="{divider_x:.1f}" '
        f'y2="{TOP_MARGIN - 6 + content_height}" class="divider" />'
    )

    def dashes_after(text_start_x, char_w, text, y_pos):
        text_width = len(text) * char_w
        dash_start = text_start_x + text_width + 10
        if dash_start < info_right_edge:
            parts.append(f'<line x1="{dash_start:.1f}" y1="{y_pos}" x2="{info_right_edge}" y2="{y_pos}" class="hr" />')

    # --- info column (right) ---
    for row in rows:
        kind = row["kind"]

        if kind == "spacer":
            y += SPACER_HEIGHT
            continue

        if kind == "prompt":
            header_text = f'{row["user"]}@{row["host"]}'
            parts.append(
                f'<text x="{info_x}" y="{y}" class="prompt fadein" style="animation-delay:{row["delay"]}s">'
                f'<tspan fill="{theme["prompt_user"]}" font-weight="bold">{_esc(row["user"])}</tspan>'
                f'<tspan fill="{theme["value"]}">@</tspan>'
                f'<tspan fill="{theme["prompt_host"]}" font-weight="bold">{_esc(row["host"])}</tspan>'
                f"</text>"
            )
            dashes_after(info_x, PROMPT_CHAR_WIDTH, header_text, y - 4)
            y += INFO_LINE_HEIGHT
            continue

        if kind == "section":
            title = row["title"]
            parts.append(
                f'<text x="{info_x}" y="{y}" class="section fadein" '
                f'fill="{theme["section"]}" style="animation-delay:{row["delay"]}s">{_esc(title)}</text>'
            )
            dashes_after(info_x, INFO_CHAR_WIDTH, title, y - 3.5)
            y += INFO_LINE_HEIGHT
            continue

        if kind == "text":
            value_lines = row["value_lines"]
            parts.append(
                f'<text x="{info_x}" y="{y}" class="line fadein" style="animation-delay:{row["delay"]}s">'
                f'<tspan fill="{theme["label"]}">{_esc(row["label"])}</tspan>'
                f'<tspan fill="{theme["muted"]}"> {row["dots"]} </tspan>'
                f"{'' if row['flush'] else _esc(value_lines[0])}"
                f"</text>"
            )
            if row["flush"]:
                parts.append(
                    f'<text x="{info_right_edge}" y="{y}" text-anchor="end" class="line fadein" '
                    f'style="animation-delay:{row["delay"]}s" fill="{theme["value"]}">{_esc(value_lines[0])}</text>'
                )
            y += INFO_LINE_HEIGHT
            for extra_line in value_lines[1:]:
                parts.append(
                    f'<text x="{row["value_x"]:.1f}" y="{y}" class="line fadein" '
                    f'style="animation-delay:{row["delay"]}s" fill="{theme["value"]}">{_esc(extra_line)}</text>'
                )
                y += INFO_LINE_HEIGHT
            continue

        if kind == "stat_row":
            ll, lv = row["left_label"], row["left_value"]
            dots_l = "." * _leader_dots(ll, lv, col1_x, col1_end)
            parts.append(
                f'<text x="{col1_x}" y="{y}" class="line fadein" style="animation-delay:{row["delay"]}s">'
                f'<tspan fill="{theme["label"]}">{_esc(ll)}</tspan>'
                f'<tspan fill="{theme["muted"]}"> {dots_l} </tspan>'
                f"</text>"
            )
            parts.append(
                f'<text x="{col1_end}" y="{y}" text-anchor="end" class="line fadein" '
                f'style="animation-delay:{row["delay"]}s" fill="{theme["value"]}">{_esc(lv)}</text>'
            )
            if row["right_label"]:
                rl, rv = row["right_label"], row["right_value"]
                dots_r = "." * _leader_dots(rl, rv, col2_x, col2_end)
                parts.append(
                    f'<text x="{col2_x}" y="{y}" class="line fadein" style="animation-delay:{row["delay"]}s">'
                    f'<tspan fill="{theme["label"]}">{_esc(rl)}</tspan>'
                    f'<tspan fill="{theme["muted"]}"> {dots_r} </tspan>'
                    f"</text>"
                )
                parts.append(
                    f'<text x="{col2_end}" y="{y}" text-anchor="end" class="line fadein" '
                    f'style="animation-delay:{row["delay"]}s" fill="{theme["value"]}">{_esc(rv)}</text>'
                )
            y += INFO_LINE_HEIGHT
            continue

        if kind == "loc_row":
            label = "Lines of Code"
            net_str = _fmt_int(row["net"])
            dots_l = "." * _leader_dots(label, net_str, col1_x, col1_end)
            parts.append(
                f'<text x="{col1_x}" y="{y}" class="line fadein" style="animation-delay:{row["delay"]}s">'
                f'<tspan fill="{theme["label"]}">{label}</tspan>'
                f'<tspan fill="{theme["muted"]}"> {dots_l} </tspan>'
                f"</text>"
            )
            parts.append(
                f'<text x="{col1_end}" y="{y}" text-anchor="end" class="line fadein" '
                f'style="animation-delay:{row["delay"]}s" fill="{theme["value"]}">{_esc(net_str)}</text>'
            )
            parts.append(
                f'<text x="{col2_end}" y="{y}" text-anchor="end" class="line fadein" '
                f'style="animation-delay:{row["delay"]}s">'
                f'<tspan fill="{theme["add"]}">{_esc(_fmt_int(row["added"]))}++</tspan>'
                f'<tspan fill="{theme["value"]}">  </tspan>'
                f'<tspan fill="{theme["del"]}">{_esc(_fmt_int(row["deleted"]))}--</tspan>'
                f"</text>"
            )
            y += INFO_LINE_HEIGHT
            continue

    body = "\n  ".join(parts)

    style = f"""
    <style>
      text {{ font-family: {FONT_STACK}; font-size: {INFO_FONT_SIZE}px; }}
      .prompt {{ font-size: {PROMPT_FONT_SIZE}px; }}
      .section {{ font-weight: bold; font-size: {INFO_FONT_SIZE}px; }}
      .line {{ font-size: {INFO_FONT_SIZE}px; }}
      .divider {{ stroke: {theme["border"]}; stroke-width: 1; }}
      .hr {{ stroke: {theme["muted"]}; stroke-width: 1; stroke-dasharray: 2,2; }}
      .fadein {{
        opacity: 0;
        animation: fadeIn 0.5s ease-out forwards;
      }}
      @keyframes fadeIn {{
        from {{ opacity: 0; transform: translateX(-4px); }}
        to   {{ opacity: 1; transform: translateX(0); }}
      }}
    </style>
    """

    svg = f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" \
xmlns="http://www.w3.org/2000/svg" role="img" aria-label="neofetch-style GitHub stats for {_esc(stats['username'])}">
  {style}
  <rect x="0" y="0" width="{width}" height="{height}" rx="10" fill="{theme["bg"]}" stroke="{theme["border"]}" />
  {body}
</svg>
"""
    return svg
