#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from dashboard_widget_manager import (
    ROOT,
    assert_publishable,
    ensure_nojekyll,
    load_registry,
    replace_or_insert_zone,
    verify_html,
)


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def github_headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN missing")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }


def repo_slug() -> tuple[str, str, str]:
    user = os.getenv("GITHUB_USERNAME", "sohweekian")
    repo = os.getenv("GITHUB_PAGES_REPO", "bluelotus")
    branch = os.getenv("GITHUB_BRANCH", "main")
    return user, repo, branch


def gh_get(path: str) -> dict:
    user, repo, _ = repo_slug()
    url = f"https://api.github.com/repos/{user}/{repo}/contents/{path}"
    req = urllib.request.Request(url, headers=github_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def gh_put(path: str, content: bytes, sha: str, message: str) -> str:
    user, repo, branch = repo_slug()
    url = f"https://api.github.com/repos/{user}/{repo}/contents/{path}"
    body = {
        "message": message,
        "content": base64.b64encode(content).decode(),
        "sha": sha,
        "branch": branch,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="PUT",
        headers=github_headers(),
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["content"]["sha"]


def push_nojekyll() -> None:
    ensure_nojekyll()
    user, repo, branch = repo_slug()
    path = ".nojekyll"
    url = f"https://api.github.com/repos/{user}/{repo}/contents/{path}"
    sha = None
    try:
        req = urllib.request.Request(url, headers=github_headers())
        with urllib.request.urlopen(req, timeout=30) as resp:
            sha = json.loads(resp.read()).get("sha")
    except Exception:
        pass
    content = b"static dashboard\n"
    body = {
        "message": "chore(pages): preserve static dashboard nojekyll",
        "content": base64.b64encode(content).decode(),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="PUT",
        headers=github_headers(),
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        json.loads(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="Update BlueLotus dashboard thesis widgets")
    parser.add_argument("--restore", action="store_true", help="Recreate widget zone if missing")
    parser.add_argument("--verify-public", action="store_true", help="Run public verifier after push")
    args = parser.parse_args()

    load_env()
    registry = load_registry()
    page = gh_get("index.html")
    html = base64.b64decode(page["content"]).decode("utf-8")
    updated = replace_or_insert_zone(html, registry, restore=args.restore)
    assert_publishable(updated, registry)
    errors = verify_html(updated, registry)
    if errors:
        raise RuntimeError("; ".join(errors))
    push_nojekyll()
    if updated == html:
        print("PASS dashboard widget zone already current")
    else:
        new_sha = gh_put(
            "index.html",
            updated.encode("utf-8"),
            page["sha"],
            "chore(dashboard): render thesis widgets from registry",
        )
        print(f"PASS pushed index.html with registry widgets sha={new_sha}")
    if args.verify_public:
        time.sleep(8)
        verifier = ROOT / "scripts" / "verify_dashboard_widgets_public.py"
        result = subprocess.run([sys.executable, str(verifier)], cwd=str(ROOT))
        if result.returncode != 0:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
