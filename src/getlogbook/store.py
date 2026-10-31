"""Repo handle, private log, shared log on custom refs. Everything is plain files + git plumbing.

Shared layout (one writer per ref, so no merge conflicts):
    refs/logbook/log/<user>/<device>            own writes (never overwritten by fetch)
    refs/logbook-remote/<remote>/log/<u>/<d>    everyone else's, fetched with a separate refspec
Each ref's tip tree holds every entry as entries/<id>.json (state lives in the tree, history is not needed).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from . import git as g

PREFIX = "refs/logbook/log"
REMOTE_NS = "refs/logbook-remote"
BRANCH_PREFIX = "refs/heads/logbook/log"
_REF_RE = re.compile(r"/(?:branch)?log/([0-9a-f]{6,16})/([0-9a-f]{2,16})$")
MAX_BLOB = 65536
MAX_PER_REF = 5000
DEFAULT_POLICY = {"publish": True, "inject_from": "trusted", "attribution": "pseudonym",
                  "max_entry_bytes": 16384, "retention_days": 0}


def user_id(email):
    """Stable, pseudonymous id for a person: same on every machine, derived from their git email."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:10]


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(2).hex()}.tmp")
    tmp.write_text(data, encoding="utf-8", newline="\n")
    for i in range(6):  # antivirus / OneDrive can briefly lock the target on Windows
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    os.replace(tmp, path)


class Loaded:
    __slots__ = ("entry", "scope", "user", "device", "ref")

    def __init__(self, entry, scope, user="", device="", ref=""):  # scope: shared | private
        self.entry, self.scope, self.user, self.device, self.ref = entry, scope, user, device, ref


class Repo:
    def __init__(self, cwd="."):
        self.root, self.common = g.repo_paths(cwd)
        self.cdir = self.common / "logbook"  # shared by all worktrees of this clone

    # config ---------------------------------------------------------------
    def cfg(self):
        try:
            return json.loads((self.cdir / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_cfg(self, c):
        atomic_write(self.cdir / "config.json", json.dumps(c, indent=2, sort_keys=True))

    def init(self):
        c = self.cfg()
        email = g.config_get(self.root, "user.email").lower()
        if not email:
            raise SystemExit("logbook: set `git config user.email` first (used only to derive a stable pseudonymous id).")
        c.setdefault("user", user_id(email))
        c.setdefault("device", os.urandom(3).hex())
        c.setdefault("display", g.config_get(self.root, "user.name"))
        c.setdefault("trusted", [])
        c.setdefault("deny", [])
        c.setdefault("transport", "refs")
        c.setdefault("interpreter", __import__("sys").executable)
        self.save_cfg(c)
        for d in ("private", "sessions", "spool", "seen"):
            (self.cdir / d).mkdir(parents=True, exist_ok=True)
        return c
