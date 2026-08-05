#!/usr/bin/env python3
"""Generate dark_mode.svg / light_mode.svg: a neofetch-style GitHub stats card.

Usage:
    ACCESS_TOKEN=ghp_xxx python today.py
    python today.py --mock          # render sample data, no API calls / no token needed

See SETUP.md for token scopes and local setup instructions.
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import cache
from src.github_api import GitHubAPI, GitHubAPIError
from src.stats import (
    USER_INFO_QUERY,
    collect_commit_contributed_repos,
    collect_contributed_repos_count,
    collect_loc,
    collect_owned_repos,
    collect_total_commits,
    collect_weighted_most_popular,
    scan_frameworks,
)
from src.svg_render import render_svg

ROOT = os.path.dirname(os.path.abspath(__file__))
MOST_POPULAR_COUNT = 6

# --- Personalize this section for your own profile -------------------------
OS_LIST = "Linux, Windows"
IDE = "VSCode"
LANGUAGES_PROGRAMMING = ["JavaScript", "TypeScript", "Python"]
LANGUAGES_COMPUTER = ["React", "Next.js", "Vue.js", "Node.js"]
LANGUAGES_REAL = ["Spanish"]
HOBBY_SOFTWARE = "Web Scraping"
HOBBY_REAL = "Making YouTube videos"
CONTACT_EMAIL = "agus.devvv@gmail.com"
CONTACT_LINKEDIN = "linkedin.com/in/ricardoagustingonzalez"
CONTACT_DISCORD = "agustin.dev"
CONTACT_PORTFOLIO = "www.vulcanis.com.ar"
# -----------------------------------------------------------------------------


def _uptime_string(created_at_iso):
    created = dt.datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    days = (now - created).days
    years, rem_days = divmod(days, 365)
    months = rem_days // 30
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    parts.append(f"{months} month{'s' if months != 1 else ''}")
    return ", ".join(parts)


def _combine_most_popular(languages, frameworks, top_n):
    """Both languages and frameworks are already weighted by the user's LOC
    contribution (see collect_weighted_most_popular), just normalized
    against slightly different denominators (all repos vs. only repos with
    a package.json) -- close enough to blend into one ranking."""
    combined = sorted(languages + frameworks, key=lambda item: item["percent"], reverse=True)
    return combined[:top_n]


def gather_stats(api):
    data = api.graphql(USER_INFO_QUERY)
    viewer = data["viewer"]
    login = viewer["login"]

    print(f"[today] Gathering stats for {login} ...")

    repos = collect_owned_repos(api, login)
    non_fork_repos = [r for r in repos if not r["isFork"]]
    print(f"[today] {len(repos)} owned repos ({len(non_fork_repos)} non-fork)")

    commit_contributed_repos = collect_commit_contributed_repos(api, login)
    print(f"[today] {len(commit_contributed_repos)} other repos committed to")

    # "Most Popular" looks at everything the user has actually put code
    # into -- their own repos plus repos they've committed to elsewhere --
    # not just what they own.
    owned_names = {r["nameWithOwner"] for r in non_fork_repos}
    combined_repos = non_fork_repos + [r for r in commit_contributed_repos if r["nameWithOwner"] not in owned_names]

    stars = sum(r["stargazerCount"] for r in non_fork_repos)

    commits = collect_total_commits(api, viewer["createdAt"])

    loc_cache = cache.load("loc_cache.json", {})
    loc_added, loc_deleted, loc_cache = collect_loc(api, login, combined_repos, loc_cache)
    cache.save("loc_cache.json", loc_cache)

    framework_cache = cache.load("framework_cache.json", {})
    framework_cache = scan_frameworks(api, combined_repos, framework_cache)
    cache.save("framework_cache.json", framework_cache)

    top_languages, top_frameworks = collect_weighted_most_popular(
        combined_repos, loc_cache, framework_cache, top_n=MOST_POPULAR_COUNT
    )
    most_popular = _combine_most_popular(top_languages, top_frameworks, MOST_POPULAR_COUNT)

    contributed_count = collect_contributed_repos_count(api, login)

    return {
        "username": login,
        "os_list": OS_LIST,
        "uptime": _uptime_string(viewer["createdAt"]),
        "ide": IDE,
        "languages_programming": LANGUAGES_PROGRAMMING,
        "languages_computer": LANGUAGES_COMPUTER,
        "languages_real": LANGUAGES_REAL,
        "hobby_software": HOBBY_SOFTWARE,
        "hobby_real": HOBBY_REAL,
        "contact_email": CONTACT_EMAIL,
        "contact_linkedin": CONTACT_LINKEDIN,
        "contact_discord": CONTACT_DISCORD,
        "contact_portfolio": CONTACT_PORTFOLIO,
        "most_popular": most_popular,
        "repos_owned": viewer["repositories"]["totalCount"],
        "repos_contributed": contributed_count,
        "stars": stars,
        "commits": commits,
        "followers": viewer["followers"]["totalCount"],
        "loc_added": loc_added,
        "loc_deleted": loc_deleted,
    }


def mock_stats():
    return {
        "username": "AgustinGonzalez1",
        "os_list": OS_LIST,
        "uptime": "4 years, 3 months programming",
        "ide": IDE,
        "languages_programming": LANGUAGES_PROGRAMMING,
        "languages_computer": LANGUAGES_COMPUTER,
        "languages_real": LANGUAGES_REAL,
        "hobby_software": HOBBY_SOFTWARE,
        "hobby_real": HOBBY_REAL,
        "contact_email": CONTACT_EMAIL,
        "contact_linkedin": CONTACT_LINKEDIN,
        "contact_discord": CONTACT_DISCORD,
        "contact_portfolio": CONTACT_PORTFOLIO,
        "most_popular": [
            {"name": "TypeScript", "percent": 41.2, "color": "#3178c6"},
            {"name": "React", "percent": 33.3, "color": "#61dafb"},
            {"name": "Python", "percent": 27.8, "color": "#3572A5"},
            {"name": "JavaScript", "percent": 18.5, "color": "#f1e05a"},
            {"name": "Next.js", "percent": 14.2, "color": "#ffffff"},
            {"name": "CSS", "percent": 9.6, "color": "#563d7c"},
        ],
        "repos_owned": 42,
        "repos_contributed": 17,
        "stars": 128,
        "commits": 3541,
        "followers": 96,
        "loc_added": 184320,
        "loc_deleted": 62110,
    }


def write_if_changed(path, content):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            if f.read() == content:
                print(f"[today] {os.path.basename(path)} unchanged, skipping write")
                return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[today] wrote {os.path.basename(path)}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="use sample data instead of calling the GitHub API")
    args = parser.parse_args()

    if args.mock:
        stats = mock_stats()
    else:
        try:
            api = GitHubAPI()
        except RuntimeError as exc:
            print(f"[today] ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            stats = gather_stats(api)
        except GitHubAPIError as exc:
            print(f"[today] ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

    dark_svg = render_svg(stats, mode="dark")
    light_svg = render_svg(stats, mode="light")

    changed = False
    changed |= write_if_changed(os.path.join(ROOT, "dark_mode.svg"), dark_svg)
    changed |= write_if_changed(os.path.join(ROOT, "light_mode.svg"), light_svg)

    cache.save("last_stats.json", stats)

    if not changed:
        print("[today] No changes detected, nothing new to commit.")


if __name__ == "__main__":
    main()
