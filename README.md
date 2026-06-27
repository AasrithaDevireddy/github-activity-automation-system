# GitHub Activity Automation System

A configurable, automated tool that keeps your GitHub contribution graph active by making scheduled commits to existing repositories and periodically creating new stub projects — all driven by the GitHub REST API v3, with zero manual effort once set up.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Prerequisites](#prerequisites)
3. [Setup Instructions](#setup-instructions)
4. [Configuration Guide](#configuration-guide)
5. [API Key Setup](#api-key-setup)
6. [Running the Agents](#running-the-agents)
7. [Scheduling](#scheduling)
8. [Kill Switch](#kill-switch)
9. [Troubleshooting](#troubleshooting)
10. [Project Structure](#project-structure)
11. [Design Decisions & Trade-offs](#design-decisions--trade-offs)
12. [Running Tests](#running-tests)

---

## Project Overview

The system contains two automated agents:

- **Daily Commit Agent** (`daily_commit.py`) — Selects a random non-forked, non-archived repository from your GitHub account each day and pushes 1–3 commits to a tracking file, keeping your contribution graph green.
- **Project Creator Agent** (`project_creator.py`) — Periodically creates a brand-new public GitHub repository seeded with language-appropriate starter files (README, `.gitignore`, and a source file). Optionally uses the HuggingFace Inference API to generate unique project ideas; falls back to a built-in list if the API is unavailable.

Both agents are idempotent, fully configurable via `config.json`, and log every action to both stdout and a rotating log file.

---

## Prerequisites

| Tool | Minimum Version | Notes |
|---|---|---|
| Python | 3.10+ | `python --version` to check |
| Git | 2.x | Required for cloning only |
| pip | bundled with Python | |

No OS-level dependencies beyond the above. Works on Linux, macOS, and Windows.

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/github-activity-automation.git
cd github-activity-automation
```

### 2. Create a virtual environment

```bash
# Linux / macOS
python3 -m venv venv
source venv/bin/activate

# Windows CMD
python -m venv venv
venv\Scripts\activate.bat

# Windows PowerShell
python -m venv venv
venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Open .env in your editor and fill in your tokens (see API Key Setup below)
```

### 5. Verify the setup

```bash
python daily_commit.py --force
```

You should see log output and a new commit in one of your GitHub repositories.

---

## Configuration Guide

All settings live in `config.json`. **Never edit Python source code to change behaviour** — everything is controlled here.

```jsonc
{
  "kill_switch": false,          // Set to true to immediately halt all agents

  "daily_commit": {
    "tracking_file": "activity.log",  // File appended to in each target repo
    "min_commits": 1,                 // Minimum commits per run (integer ≥ 1)
    "max_commits": 3,                 // Maximum commits per run (integer ≥ min_commits)
    "commit_messages": [              // Pool of commit messages; one is chosen at random
      "chore: update activity log [automated]",
      ...
    ],
    "state_file": "state/daily_commit_state.json"  // Where run state is persisted
  },

  "project_creator": {
    "supported_languages": ["python", "javascript"],  // Languages the agent may use
    "default_language": "python",      // Used if no --lang flag is passed
    "state_file": "state/project_creator_state.json",
    "run_interval_days": 3,            // Minimum days between project creations
    "project_ideas": [...],            // Built-in fallback idea list
    "use_ai_api": true,                // Try HuggingFace API for ideas when true
    "ai_api_provider": "huggingface",  // Reserved for future providers
    "repo_visibility": "public"        // "public" or "private"
  },

  "logging": {
    "log_file": "logs/automation.log", // Path to the rotating log file
    "log_level": "INFO",               // DEBUG | INFO | WARNING | ERROR
    "max_log_size_mb": 10,             // Max size before log rotation
    "backup_count": 3                  // Number of rotated log files to keep
  }
}
```

---

## API Key Setup

### GitHub Personal Access Token (required)

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**.
2. Click **Generate new token (classic)**.
3. Give it a descriptive name (e.g. `automation-system`).
4. Select the **`repo`** scope (full control of private repositories). This is the minimum required scope.
5. Click **Generate token** and copy it immediately — you won't see it again.
6. Open your `.env` file and set:

```env
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

> ⚠️ **Never commit your `.env` file.** It is excluded by `.gitignore`.

### HuggingFace Token (optional)

Used to generate unique project ideas via the Inference API. If omitted, the system falls back to `config.json`'s built-in idea list.

1. Create a free account at [huggingface.co](https://huggingface.co).
2. Go to **Settings → Access Tokens → New token** (read scope is sufficient).
3. Add to `.env`:

```env
HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
```

---

## Running the Agents

### Daily Commit Agent

```bash
# Normal run — no-op if already ran today
python daily_commit.py

# Force a run regardless of last run date (useful for testing)
python daily_commit.py --force
```

### Project Creator Agent

```bash
# Normal run — respects run_interval_days from config
python project_creator.py

# Force a run now
python project_creator.py --force

# Force a specific language
python project_creator.py --force --lang python
python project_creator.py --force --lang javascript
```

---

## Scheduling

### Option A — GitHub Actions (recommended, zero maintenance)

The included `.github/workflows/automation.yml` workflow runs:
- **Daily Commit Agent** every day at 09:00 UTC.
- **Project Creator Agent** every Monday at 10:00 UTC.

**Setup steps:**

1. Push this repo to GitHub.
2. Go to **Settings → Secrets and variables → Actions**.
3. Add a secret named `AUTOMATION_GITHUB_TOKEN` with your GitHub PAT.
4. Optionally add `HUGGINGFACE_TOKEN`.
5. The workflow will run on schedule automatically.

You can also trigger it manually via **Actions → GitHub Activity Automation → Run workflow**.

> **Note:** GitHub Actions state files (in `state/`) are committed back by the workflow after each run so idempotency is preserved across runs.

### Option B — cron (Linux / macOS)

```bash
crontab -e
```

Add these lines (adjust paths to your actual venv and project directory):

```cron
# Daily Commit Agent — every day at 09:00 local time
0 9 * * * cd /path/to/github-activity-automation && /path/to/venv/bin/python daily_commit.py >> logs/cron.log 2>&1

# Project Creator Agent — every Monday at 10:00 local time
0 10 * * 1 cd /path/to/github-activity-automation && /path/to/venv/bin/python project_creator.py >> logs/cron.log 2>&1
```

Load environment variables before running (cron does not read `.env` automatically):

```cron
0 9 * * * cd /path/to/project && export $(cat .env | xargs) && /path/to/venv/bin/python daily_commit.py
```

### Option C — Windows Task Scheduler

1. Open **Task Scheduler → Create Basic Task**.
2. Set trigger to **Daily** at your preferred time.
3. Set action to **Start a Program**:
   - Program: `C:\path\to\venv\Scripts\python.exe`
   - Arguments: `daily_commit.py`
   - Start in: `C:\path\to\github-activity-automation`
4. Repeat for the Project Creator Agent with a weekly trigger.
5. Ensure `GITHUB_TOKEN` is set as a system environment variable (Control Panel → System → Advanced → Environment Variables).

---

## Kill Switch

To **immediately halt both agents** without touching source code:

**Option 1 — Edit `config.json`:**
```json
{
  "kill_switch": true,
  ...
}
```

Both agents check this flag at startup and exit cleanly before making any API calls.

**To re-enable:** Set `"kill_switch": false`.

---

## Troubleshooting

### 1. `GITHUB_TOKEN is not set`

**Cause:** The `.env` file is missing or the variable is not exported.

**Fix:**
```bash
# Check if the file exists
cat .env

# Load it manually
export $(cat .env | xargs)   # Linux/macOS
```

Alternatively, set the variable directly in your shell:
```bash
export GITHUB_TOKEN=ghp_yourtoken
```

---

### 2. `GitHub API error 401: Bad credentials`

**Cause:** The token is invalid, expired, or has insufficient scopes.

**Fix:**
1. Go to GitHub → Settings → Developer settings → Personal access tokens.
2. Verify the token exists and has the **`repo`** scope.
3. If expired, generate a new token and update `.env`.

---

### 3. `GitHub API error 422: Repository creation failed`

**Cause:** A repository with the generated name already exists under your account.

**Fix:** The Project Creator tracks created repos in `state/project_creator_state.json`. If the state file is missing or out of sync, the agent may attempt to create a duplicate.

- Delete the conflicting repository on GitHub, **or**
- Add the slug to `"created_projects"` in the state file manually.

---

### 4. Agent ran but no commit appeared on GitHub

**Cause:** The commit was made to a branch other than the one GitHub counts for contributions (must be the default branch of a non-fork repo).

**Fix:** Verify that the repository you own is not a fork and that the default branch is `main` or `master`. Check `logs/automation.log` for the exact branch used.

---

### 5. `No non-forked, non-archived repositories found`

**Cause:** All repositories in your account are either forks or archived.

**Fix:** Create at least one original (non-forked) repository and make sure it is not archived. You can run the Project Creator Agent first with `--force` to create one automatically.

---

### 6. HuggingFace API errors / timeouts

**Cause:** The free-tier model may be cold-starting or rate-limited.

**Fix:** This is handled automatically — the agent logs a warning and falls back to the built-in idea list. No action required. To disable AI entirely: set `"use_ai_api": false` in `config.json`.

---

## Project Structure

```
github-activity-automation/
├── daily_commit.py          # Daily Commit Agent entry point
├── project_creator.py       # Project Creator Agent entry point
├── github_client.py         # GitHub REST API v3 wrapper (all HTTP calls)
├── utils.py                 # Shared utilities: config, logging, state, kill switch
├── config.json              # All configurable settings (edit this, not source code)
├── requirements.txt         # Pinned Python dependencies
├── .env.example             # Template for environment variables (copy → .env)
├── .gitignore               # Excludes .env, logs/, state/, venv/
├── .github/
│   └── workflows/
│       └── automation.yml   # GitHub Actions workflow for scheduled runs
├── state/                   # Runtime state (auto-created; gitignored by default)
│   ├── daily_commit_state.json
│   └── project_creator_state.json
├── logs/                    # Rotating log files (auto-created; gitignored)
│   └── automation.log
└── tests/
    └── test_agents.py       # Unit tests (idempotency, repo selection, state, slugs)
```

---

## Design Decisions & Trade-offs

### State persistence: JSON files over SQLite

Chose flat JSON files for state persistence because the data model is trivially simple (a few scalar values + one list). SQLite would add complexity with no benefit at this scale. JSON files are human-readable, easy to inspect/edit manually, and require no additional dependencies.

### Raw `requests` over PyGithub

Used `requests` directly instead of the `PyGithub` wrapper library to keep the dependency footprint minimal and maintain explicit control over API calls, headers, and rate-limit handling. The GitHub REST API v3 is straightforward enough that a thin wrapper (`github_client.py`) provides everything needed without a heavy ORM-style abstraction.

### Branch detection

The agent fetches the default branch from the API rather than assuming `main` or `master`, ensuring compatibility with repositories created under older GitHub conventions.

### HuggingFace integration

Integrated as an optional enhancement with a graceful fallback. The agent degrades transparently when the API is unavailable, rate-limited, or the token is absent — it never blocks or crashes.

### Idempotency

State is written to disk only after at least one successful commit. If an agent run fails partway through, re-running it will retry rather than silently skipping.

---

## Running Tests

```bash
# Install dependencies (if not already done)
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run with coverage (optional)
pip install pytest-cov
pytest tests/ -v --cov=. --cov-report=term-missing
```

Tests cover: idempotency logic, repository avoidance selection, interval checking, slug generation, and state persistence round-trips.
