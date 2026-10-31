"""`logbook demo`: a scratch dbt-like repo, a bare remote, and three people (Alice, Bob, and a hostile Mallory).
Doubles as an integration test: every claim is checked and the exit code says whether they held."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from . import capture, sync
from .store import Repo

FAILS = []


def say(s=""):
    print(s)


def head(s):
    print(f"\n=== {s}")


def check(cond, msg):
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def sh(*a, cwd):
    r = subprocess.run(a, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{a}: {r.stderr}")
    return r.stdout.strip()


def person(root, remote, name, email, shallow=False):
    d = root / name.lower()
    url = "file://" + str(remote).replace("\\", "/")
    sh("git", "clone", "-q", *(["--depth=1"] if shallow else []), url, str(d), cwd=root)
    sh("git", "config", "user.email", email, cwd=d)
    sh("git", "config", "user.name", name, cwd=d)
    return d


def commit(d, msg, files):
    for p, text in files.items():
        f = d / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    sh("git", "add", "-A", cwd=d)
    sh("git", "commit", "-q", "-m", msg, cwd=d)
    return sh("git", "rev-parse", "HEAD", cwd=d)


def run(dir=None, serve=False):
    root = Path(dir) if dir else Path(tempfile.mkdtemp(prefix="logbook-demo-"))
    root.mkdir(parents=True, exist_ok=True)
    say(f"scratch space: {root}")

    head("1. A dbt-like repo, a shared remote, and Alice")
    remote = root / "remote.git"
    sh("git", "init", "-q", "--bare", str(remote), cwd=root)
    seed = root / "seed"
    sh("git", "clone", "-q", "file://" + str(remote).replace("\\", "/"), str(seed), cwd=root)
    sh("git", "config", "user.email", "alice@example.com", cwd=seed)
    sh("git", "config", "user.name", "Alice", cwd=seed)
    commit(seed, "initial models", {
        "models/staging/stg_orders.sql": "select * from raw_orders",
        "models/staging/stg_payments.sql": "select * from raw_payments",
        "models/marts/fct_revenue.sql": "select sum(amount) as revenue from stg_payments"})
    sh("git", "push", "-q", "origin", "HEAD", cwd=seed)
    alice = root / "alice"
    sh("git", "clone", "-q", "file://" + str(remote).replace("\\", "/"), str(alice), cwd=root)
    sh("git", "config", "user.email", "alice@example.com", cwd=alice)
    sh("git", "config", "user.name", "Alice", cwd=alice)
    ra = Repo(alice)
    ra.init()
    capture.install_git_hook(ra)
    sync.ensure_fetch_config(ra)
    say(f"Alice is {ra.user}; git post-commit floor installed (chained, never overwrites a hook)")
