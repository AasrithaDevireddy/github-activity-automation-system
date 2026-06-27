"""
daily_commit.py — Daily Commit Agent for GitHub Activity Automation System.

Usage:
    python daily_commit.py           # Normal run (no-op if already ran today)
    python daily_commit.py --force   # Bypass once-per-day guard (for testing)
"""

import argparse
import random
import sys
from datetime import datetime

from dotenv import load_dotenv

from github_client import GitHubClient, GitHubError
from utils import (
    get_github_token,
    is_kill_switch_active,
    load_config,
    load_state,
    save_state,
    setup_logger,
    today_str,
)

load_dotenv()


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Daily Commit Agent — keeps your GitHub contribution graph active."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the once-per-day guard and run even if already ran today.",
    )
    return parser.parse_args()


def select_repository(repos: list[dict], last_repo: str) -> dict:
    """
    Choose a random repository from the list, avoiding the repo used in
    the previous run when multiple options exist.
    """
    if len(repos) == 0:
        raise ValueError("No eligible repositories found.")

    candidates = [r for r in repos if r["name"] != last_repo]
    if not candidates:
        candidates = repos  # Only one repo — no avoidance possible

    return random.choice(candidates)


def build_commit_content(existing_content: str, commit_index: int) -> str:
    """Append a timestamped line to the tracking file content."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    new_line = f"[{timestamp}] automated commit #{commit_index}\n"
    return existing_content + new_line


def run_daily_commit(force: bool = False) -> None:
    config = load_config()
    logger = setup_logger("daily_commit", config)

    logger.info("Daily Commit Agent starting.")

    # ── Kill switch ───────────────────────────────────────────────────────────
    if is_kill_switch_active(config, logger):
        sys.exit(0)

    # ── Idempotency check ─────────────────────────────────────────────────────
    dc_cfg = config["daily_commit"]
    state = load_state(dc_cfg["state_file"])
    last_run_date = state.get("last_run_date", "")

    if not force and last_run_date == today_str():
        logger.info(
            "Already ran today (%s). Use --force to override. Exiting.", today_str()
        )
        return

    # ── GitHub auth ───────────────────────────────────────────────────────────
    try:
        token = get_github_token()
    except EnvironmentError as exc:
        logger.error("Missing GitHub token: %s", exc)
        sys.exit(1)

    client = GitHubClient(token)

    # ── Get authenticated user ────────────────────────────────────────────────
    try:
        user = client.get_authenticated_user()
        owner = user["login"]
        logger.info("Authenticated as '%s'.", owner)
    except GitHubError as exc:
        logger.error("Failed to authenticate with GitHub: %s", exc)
        sys.exit(1)

    # ── Fetch repos ───────────────────────────────────────────────────────────
    try:
        repos = client.list_user_repos()
        logger.info("Found %d eligible repositories.", len(repos))
    except GitHubError as exc:
        logger.error("Failed to list repositories: %s", exc)
        sys.exit(1)

    if not repos:
        logger.error("No non-forked, non-archived repositories found. Exiting.")
        sys.exit(1)

    # ── Select target repo ────────────────────────────────────────────────────
    last_repo = state.get("last_repo", "")
    target_repo = select_repository(repos, last_repo)
    repo_name = target_repo["name"]
    logger.info("Selected repository: '%s' (previous: '%s').", repo_name, last_repo or "none")

    # ── Determine commit count ────────────────────────────────────────────────
    min_commits = int(dc_cfg.get("min_commits", 1))
    max_commits = int(dc_cfg.get("max_commits", 3))
    commit_count = random.randint(min_commits, max_commits)
    logger.info("Will make %d commit(s) to '%s'.", commit_count, repo_name)

    # ── Get default branch ────────────────────────────────────────────────────
    try:
        branch = client.get_default_branch(owner, repo_name)
    except GitHubError as exc:
        logger.error("Could not determine default branch for '%s': %s", repo_name, exc)
        sys.exit(1)

    # ── Fetch or initialise tracking file ────────────────────────────────────
    tracking_file = dc_cfg.get("tracking_file", "activity.log")
    try:
        file_meta = client.get_file(owner, repo_name, tracking_file)
    except GitHubError as exc:
        logger.error("Error fetching tracking file: %s", exc)
        sys.exit(1)

    import base64

    if file_meta:
        current_content = base64.b64decode(
            file_meta["content"].replace("\n", "")
        ).decode("utf-8")
        file_sha = file_meta["sha"]
    else:
        current_content = f"# Automated activity log for {repo_name}\n"
        file_sha = None

    # ── Make commits ──────────────────────────────────────────────────────────
    message_pool = dc_cfg.get("commit_messages", ["chore: automated commit"])
    successful_commits = 0

    for i in range(1, commit_count + 1):
        message = random.choice(message_pool)
        new_content = build_commit_content(current_content, i)

        try:
            result = client.create_or_update_file(
                owner=owner,
                repo=repo_name,
                path=tracking_file,
                message=message,
                content=new_content,
                sha=file_sha,
                branch=branch,
            )
            file_sha = result["content"]["sha"]
            current_content = new_content
            successful_commits += 1
            logger.info("Commit %d/%d succeeded: '%s'.", i, commit_count, message)
        except GitHubError as exc:
            logger.error("Commit %d/%d failed: %s", i, commit_count, exc)
            break

    if successful_commits == 0:
        logger.error("No commits succeeded. State will not be updated.")
        sys.exit(1)

    # ── Persist state ─────────────────────────────────────────────────────────
    state.update(
        {
            "last_run_date": today_str(),
            "last_repo": repo_name,
            "last_commit_count": successful_commits,
        }
    )
    save_state(dc_cfg["state_file"], state)
    logger.info(
        "Daily Commit Agent finished. %d commit(s) pushed to '%s'.",
        successful_commits,
        repo_name,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = parse_args()
    run_daily_commit(force=args.force)
