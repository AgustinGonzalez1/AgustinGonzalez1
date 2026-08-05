"""Collects all the raw numbers shown in the neofetch-style stats card."""
import base64
import datetime as dt
import json

from .github_api import GitHubAPIError

LOC_STATS_MAX_RETRIES = 12

# npm package name (as it appears as a dependency key) -> (display name, brand color)
FRAMEWORK_MAP = {
    "react": ("React", "#61dafb"),
    "next": ("Next.js", "#ffffff"),
    "vue": ("Vue.js", "#41b883"),
    "nuxt": ("Nuxt", "#00dc82"),
    "nuxt3": ("Nuxt", "#00dc82"),
    "@angular/core": ("Angular", "#dd0031"),
    "svelte": ("Svelte", "#ff3e00"),
    "express": ("Express", "#8b8b8b"),
    "fastify": ("Fastify", "#8b8b8b"),
    "@nestjs/core": ("NestJS", "#e0234e"),
    "gatsby": ("Gatsby", "#663399"),
    "@remix-run/react": ("Remix", "#8b8b8b"),
    "astro": ("Astro", "#ff5d01"),
    "svelte-kit": ("SvelteKit", "#ff3e00"),
    "@sveltejs/kit": ("SvelteKit", "#ff3e00"),
    "django": ("Django", "#092e20"),
    "flask": ("Flask", "#8b8b8b"),
    "fastapi": ("FastAPI", "#009688"),
}


def scan_frameworks(api, repos, framework_cache):
    """Scans each repo's package.json dependencies for known frameworks.
    Cached per-repo by `pushedAt`, same idea as collect_loc, so unchanged
    repos aren't re-fetched. Just populates the cache -- ranking happens in
    collect_weighted_most_popular, weighted by the user's actual LOC in
    each repo rather than a flat per-repo count."""
    framework_cache = dict(framework_cache or {})

    for repo in repos:
        full_name = repo["nameWithOwner"]
        pushed_at = repo["pushedAt"]
        cached = framework_cache.get(full_name)

        if cached and cached.get("pushedAt") == pushed_at:
            continue

        owner, name = full_name.split("/", 1)
        try:
            content = api.rest_get(f"/repos/{owner}/{name}/contents/package.json")
        except GitHubAPIError as exc:
            print(f"[stats] WARNING: could not fetch package.json for {full_name} ({exc}); skipping.")
            content = None

        found = []
        if content and content.get("encoding") == "base64":
            try:
                manifest = json.loads(base64.b64decode(content["content"]))
                deps = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
                found = [pkg for pkg in deps if pkg in FRAMEWORK_MAP]
            except (ValueError, TypeError):
                found = []

        framework_cache[full_name] = {"pushedAt": pushed_at, "frameworks": found}

    return framework_cache

USER_INFO_QUERY = """
query {
  viewer {
    login
    createdAt
    followers { totalCount }
    repositories(ownerAffiliations: [OWNER]) { totalCount }
  }
}
"""

CONTRIBUTED_REPOS_QUERY = """
query ($login: String!) {
  user(login: $login) {
    repositoriesContributedTo(
      first: 1
      includeUserRepositories: true
      contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]
    ) {
      totalCount
    }
  }
}
"""

# Separate from the count above: this fetches the actual repos (excluding
# ones the user owns, which are already covered by OWNED_REPOS_QUERY) that
# the user has *committed* to, so "Most Popular" can see languages used in
# other people's repos too, not just the user's own.
COMMIT_CONTRIBUTED_REPOS_QUERY = """
query ($login: String!, $after: String) {
  user(login: $login) {
    repositoriesContributedTo(
      first: 50
      after: $after
      includeUserRepositories: false
      contributionTypes: [COMMIT]
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        isFork
        pushedAt
        languages(first: 10, orderBy: { field: SIZE, direction: DESC }) {
          edges {
            size
            node { name color }
          }
        }
      }
    }
  }
}
"""

OWNED_REPOS_QUERY = """
query ($login: String!, $after: String) {
  user(login: $login) {
    repositories(first: 50, after: $after, ownerAffiliations: [OWNER]) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        nameWithOwner
        isFork
        stargazerCount
        pushedAt
        languages(first: 10, orderBy: { field: SIZE, direction: DESC }) {
          edges {
            size
            node { name color }
          }
        }
      }
    }
  }
}
"""

CONTRIB_YEAR_QUERY = """
query ($from: DateTime!, $to: DateTime!) {
  viewer {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""


def collect_owned_repos(api, login):
    """Paginates through every repo owned by `login` (public + private, forks included)."""
    repos = []
    after = None
    while True:
        data = api.graphql(OWNED_REPOS_QUERY, {"login": login, "after": after})
        block = data["user"]["repositories"]
        repos.extend(block["nodes"])
        if not block["pageInfo"]["hasNextPage"]:
            break
        after = block["pageInfo"]["endCursor"]
    return repos


def collect_contributed_repos_count(api, login):
    data = api.graphql(CONTRIBUTED_REPOS_QUERY, {"login": login})
    return data["user"]["repositoriesContributedTo"]["totalCount"]


def collect_commit_contributed_repos(api, login):
    """Paginates through repos (not owned by `login`) that `login` has
    committed to -- so language/framework stats aren't limited to the
    user's own repos."""
    repos = []
    after = None
    while True:
        data = api.graphql(COMMIT_CONTRIBUTED_REPOS_QUERY, {"login": login, "after": after})
        block = data["user"]["repositoriesContributedTo"]
        repos.extend(block["nodes"])
        if not block["pageInfo"]["hasNextPage"]:
            break
        after = block["pageInfo"]["endCursor"]
    return repos


def collect_total_commits(api, created_at_iso):
    """Sums commit contributions (public + private) across every year since account creation.

    contributionsCollection only accepts <=1 year windows, so we walk year by year.
    """
    created = dt.datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
    start_year = created.year
    now = dt.datetime.now(dt.timezone.utc)
    total = 0
    for year in range(start_year, now.year + 1):
        frm = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        to = dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)
        if to > now:
            to = now
        if frm > to:
            continue
        data = api.graphql(CONTRIB_YEAR_QUERY, {"from": frm.isoformat(), "to": to.isoformat()})
        cc = data["viewer"]["contributionsCollection"]
        total += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
    return total


def collect_weighted_most_popular(repos, loc_cache, framework_cache, top_n=6):
    """Ranks languages and frameworks by the user's *actual* LOC contribution
    per repo (from loc_cache), not by raw repo byte totals or a flat
    per-repo dependency count -- so a repo you barely touched doesn't count
    as much as one you've put thousands of lines into. A repo's LOC is
    split across its languages proportionally to that repo's own byte
    breakdown, since GitHub doesn't expose LOC-per-language directly.
    """
    lang_weight = {}
    lang_colors = {}
    fw_weight = {}
    total_weight = 0.0
    fw_total_weight = 0.0

    for repo in repos:
        full_name = repo["nameWithOwner"]
        loc_entry = loc_cache.get(full_name)
        if not loc_entry:
            continue
        user_loc = loc_entry.get("additions", 0) + loc_entry.get("deletions", 0)
        if user_loc <= 0:
            continue

        edges = repo["languages"]["edges"]
        repo_total_bytes = sum(e["size"] for e in edges) or 1
        for edge in edges:
            name = edge["node"]["name"]
            share = edge["size"] / repo_total_bytes
            lang_weight[name] = lang_weight.get(name, 0) + user_loc * share
            lang_colors[name] = edge["node"]["color"] or "#8b8b8b"
        total_weight += user_loc

        fw_entry = framework_cache.get(full_name)
        found = fw_entry.get("frameworks") if fw_entry else None
        if found:
            fw_total_weight += user_loc
            for pkg in found:
                fw_weight[pkg] = fw_weight.get(pkg, 0) + user_loc

    languages = []
    if total_weight:
        ranked = sorted(lang_weight.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        languages = [
            {"name": name, "percent": round(w / total_weight * 100, 1), "color": lang_colors[name]}
            for name, w in ranked
        ]

    frameworks = []
    if fw_total_weight:
        ranked = sorted(fw_weight.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        frameworks = [
            {
                "name": FRAMEWORK_MAP[pkg][0],
                "percent": round(w / fw_total_weight * 100, 1),
                "color": FRAMEWORK_MAP[pkg][1],
            }
            for pkg, w in ranked
        ]

    return languages, frameworks


def collect_loc(api, login, repos, loc_cache):
    """Sums additions/deletions authored by `login` across `repos`.

    Uses the /stats/contributors endpoint (which can return 202 while GitHub
    computes it, handled by the retry logic in GitHubAPI). Results are cached
    per-repo keyed by `pushedAt`, so a repo that hasn't been pushed to since
    the last run is skipped entirely instead of re-scanned.
    """
    loc_cache = dict(loc_cache or {})
    added_total = 0
    deleted_total = 0

    for repo in repos:
        full_name = repo["nameWithOwner"]
        pushed_at = repo["pushedAt"]
        cached = loc_cache.get(full_name)

        if cached and cached.get("pushedAt") == pushed_at:
            added_total += cached["additions"]
            deleted_total += cached["deletions"]
            continue

        owner, name = full_name.split("/", 1)
        try:
            contributors = api.rest_get(
                f"/repos/{owner}/{name}/stats/contributors", max_retries=LOC_STATS_MAX_RETRIES
            ) or []
        except GitHubAPIError as exc:
            print(f"[stats] WARNING: contributor stats not ready for {full_name} ({exc}); skipping for now.")
            continue

        additions = deletions = 0
        for contributor in contributors:
            author = contributor.get("author") or {}
            if (author.get("login") or "").lower() == login.lower():
                for week in contributor.get("weeks", []):
                    additions += week.get("a", 0)
                    deletions += week.get("d", 0)
                break

        loc_cache[full_name] = {
            "pushedAt": pushed_at,
            "additions": additions,
            "deletions": deletions,
        }
        added_total += additions
        deleted_total += deletions

    return added_total, deleted_total, loc_cache
