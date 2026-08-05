"""Thin GitHub REST + GraphQL client with rate-limit aware retry/backoff."""
import os
import random
import time

import requests

GITHUB_API_REST = "https://api.github.com"
GITHUB_API_GRAPHQL = "https://api.github.com/graphql"


class GitHubAPIError(Exception):
    pass


class GitHubAPI:
    def __init__(self, token=None, max_retries=6, timeout=30):
        self.token = token or os.environ.get("ACCESS_TOKEN")
        if not self.token:
            raise RuntimeError(
                "ACCESS_TOKEN environment variable is not set. "
                "See SETUP.md for how to create and load a Personal Access Token."
            )
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "neofetch-profile-readme-bot",
            }
        )

    def _request_with_backoff(self, method, url, **kwargs):
        delay = 2.0
        last_resp = None
        last_exc = None

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(delay + random.uniform(0, 1))
                delay = min(delay * 2, 60)
                continue

            last_resp = resp

            # Primary or secondary rate limit
            if resp.status_code in (403, 429):
                remaining = resp.headers.get("X-RateLimit-Remaining")
                reset = resp.headers.get("X-RateLimit-Reset")
                if remaining == "0" and reset:
                    wait = max(int(reset) - int(time.time()), 1)
                    wait = min(wait, 900)
                    print(f"[github_api] Rate limit hit, sleeping {wait}s until reset ...")
                    time.sleep(wait)
                else:
                    retry_after = resp.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after else delay
                    print(
                        f"[github_api] Got {resp.status_code} (attempt {attempt}/{self.max_retries}), "
                        f"backing off {wait:.0f}s ..."
                    )
                    time.sleep(wait + random.uniform(0, 1))
                    delay = min(delay * 2, 60)
                continue

            # GitHub returns 202 while it computes stats (e.g. contributor stats endpoint)
            if resp.status_code == 202:
                wait = min(2 + attempt * 2, 20)
                print(f"[github_api] Stats still computing (202), retrying in {wait}s ...")
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                time.sleep(delay + random.uniform(0, 1))
                delay = min(delay * 2, 60)
                continue

            return resp

        if last_exc:
            raise GitHubAPIError(f"Request to {url} failed after {self.max_retries} attempts: {last_exc}")
        status = last_resp.status_code if last_resp is not None else "?"
        raise GitHubAPIError(f"Request to {url} failed after {self.max_retries} attempts (last status {status})")

    def rest_get(self, path, params=None):
        url = path if path.startswith("http") else f"{GITHUB_API_REST}{path}"
        resp = self._request_with_backoff("GET", url, params=params)
        if resp.status_code == 204:
            return None
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def graphql(self, query, variables=None):
        resp = self._request_with_backoff(
            "POST", GITHUB_API_GRAPHQL, json={"query": query, "variables": variables or {}}
        )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload and payload["errors"]:
            raise GitHubAPIError(str(payload["errors"]))
        return payload["data"]
