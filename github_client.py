"""
github_client.py — Thin wrapper around the GitHub REST API v3.

All network calls are made here.  Callers receive plain Python dicts/lists;
HTTP errors are converted to descriptive exceptions so agents can handle them
gracefully without crashing.
"""

import base64
import time
from typing import Optional

import requests

GITHUB_API_BASE = "https://api.github.com"


class GitHubError(Exception):
    """Raised for GitHub API errors with status code and message."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"GitHub API error {status_code}: {message}")


class GitHubClient:
    """Authenticated GitHub REST API v3 client."""

    def __init__(self, token: str, timeout: int = 15) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self._timeout = timeout

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> dict | list | None:
        """Execute a request and raise GitHubError on non-2xx responses."""
        url = f"{GITHUB_API_BASE}{path}"
        try:
            resp = self._session.request(
                method, url, timeout=self._timeout, **kwargs
            )
        except requests.exceptions.Timeout:
            raise GitHubError(0, f"Request to {url} timed out after {self._timeout}s")
        except requests.exceptions.ConnectionError as exc:
            raise GitHubError(0, f"Network error reaching {url}: {exc}")

        if resp.status_code == 204:
            return None  # No content

        if not resp.ok:
            try:
                detail = resp.json().get("message", resp.text)
            except ValueError:
                detail = resp.text
            raise GitHubError(resp.status_code, detail)

        # Respect rate-limit headers proactively
        remaining = int(resp.headers.get("X-RateLimit-Remaining", 9999))
        if remaining < 10:
            reset_ts = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            sleep_secs = max(0, reset_ts - time.time()) + 1
            time.sleep(sleep_secs)

        return resp.json() if resp.content else None

    # ── User ─────────────────────────────────────────────────────────────────

    def get_authenticated_user(self) -> dict:
        """Return the authenticated user's profile."""
        return self._request("GET", "/user")

    # ── Repositories ─────────────────────────────────────────────────────────

    def list_user_repos(self) -> list[dict]:
        """
        Return all non-forked, non-archived repos belonging to the
        authenticated user (handles pagination automatically).
        """
        repos: list[dict] = []
        page = 1
        while True:
            page_data = self._request(
                "GET",
                "/user/repos",
                params={
                    "type": "owner",
                    "per_page": 100,
                    "page": page,
                },
            )
            if not page_data:
                break
            filtered = [
                r for r in page_data if not r.get("fork") and not r.get("archived")
            ]
            repos.extend(filtered)
            if len(page_data) < 100:
                break
            page += 1
        return repos

    def create_repo(self, name: str, description: str, private: bool = False) -> dict:
        """Create a new repository under the authenticated user's account."""
        return self._request(
            "POST",
            "/user/repos",
            json={
                "name": name,
                "description": description,
                "private": private,
                "auto_init": False,
            },
        )

    # ── File / content operations ─────────────────────────────────────────────

    def get_file(self, owner: str, repo: str, path: str) -> Optional[dict]:
        """
        Return the file metadata + content for path, or None if it does not exist.
        """
        try:
            return self._request("GET", f"/repos/{owner}/{repo}/contents/{path}")
        except GitHubError as exc:
            if exc.status_code == 404:
                return None
            raise

    def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        content: str,
        sha: Optional[str] = None,
        branch: str = "main",
    ) -> dict:
        """
        Create (sha=None) or update (sha=<existing sha>) a file via the
        GitHub Contents API.  content must be a plain UTF-8 string; this
        method handles base64 encoding internally.
        """
        payload: dict = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        return self._request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{path}",
            json=payload,
        )

    def get_default_branch(self, owner: str, repo: str) -> str:
        """Return the default branch name for a repository."""
        repo_data = self._request("GET", f"/repos/{owner}/{repo}")
        return repo_data.get("default_branch", "main")
