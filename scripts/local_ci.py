"""Run the checks locally, then post a `signoff` status on the tested commit.

This repo has no GitHub Actions. Run this before you open or update a pull
request, after you push:

    git push
    python3 scripts/local_ci.py               # checks, then signoff
    python3 scripts/local_ci.py --no-signoff  # checks only

The checks:
1. Rebuild v2 with `uv run scripts/build_v2.py`.
2. Fail if the rebuild changed anything in v2/. The committed files must
   match a fresh build.
3. Run the offline tests. The MariaDB import test runs only when MYSQL_HOST
   is set, and the status description says when it did not run.

A signoff covers one commit. The script refuses to post when the worktree is
dirty, when HEAD changes during the run, or when GitHub does not have the
commit yet. It needs uv and an authenticated gh.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = [
    "uv", "run", "--with", "pyarrow>=15", "--with", "duckdb", "--with", "pandas",
    "python", "-m", "unittest", "discover", "tests",
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def dirty() -> str:
    return git("status", "--porcelain", "--untracked-files=all")


def step(name: str, command: list[str]) -> None:
    print(f"\n== {name}: {' '.join(command)}", flush=True)
    if subprocess.run(command, cwd=ROOT).returncode != 0:
        sys.exit(f"\nFAILED: {name}. No signoff was posted.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the checks locally, then post a signoff status on the tested commit.", allow_abbrev=False)
    parser.add_argument("--no-signoff", action="store_true", help="run the checks without posting a status")
    return parser.parse_args(argv)


def main() -> None:
    signoff = not parse_args(sys.argv[1:]).no_signoff
    if signoff and dirty():
        sys.exit(f"The worktree is not clean. Commit the exact tree before signoff:\n{dirty()}")
    sha = git("rev-parse", "HEAD")

    step("rebuild v2", ["uv", "run", "scripts/build_v2.py"])
    changed = git("status", "--porcelain", "--untracked-files=all", "--", "v2")
    if changed:
        sys.exit(f"\nFAILED: the rebuild changed v2/. No signoff was posted.\n{changed}")
    print("v2/ matches a fresh build.")
    step("offline tests", TESTS)

    description = "Local CI: build and tests"
    if not os.environ.get("MYSQL_HOST"):
        description += " without MariaDB"
    if not signoff:
        print(f"\nPassed: {description}. No signoff (--no-signoff).")
        return

    if git("rev-parse", "HEAD") != sha or dirty():
        sys.exit("\nThe commit or worktree changed during the run. No signoff was posted.")
    repo = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()
    if subprocess.run(["gh", "api", f"repos/{repo}/commits/{sha}", "--silent"], cwd=ROOT).returncode != 0:
        sys.exit(f"\nGitHub does not have {sha}. Push it first. No signoff was posted.")
    subprocess.run(
        [
            "gh", "api", "--method", "POST", f"repos/{repo}/statuses/{sha}", "--silent",
            "-f", "state=success", "-f", "context=signoff", "-f", f"description={description}",
        ],
        cwd=ROOT, check=True,
    )
    print(f"\nPosted signoff for {sha}: {description}")


if __name__ == "__main__":
    main()
