"""Collects all the raw numbers shown in the neofetch-style stats card."""
import datetime as dt

from .github_api import GitHubAPIError

LOC_STATS_MAX_RETRIES = 12

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
