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
from .entry import from_json

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

    @property
    def user(self):
        return self.cfg().get("user", "")

    @property
    def device(self):
        return self.cfg().get("device", "")

    def policy(self):
        """Repo policy (tracked file, owner-controlled). Only ever *restricts* the client."""
        p = dict(DEFAULT_POLICY)
        try:
            p.update(json.loads((self.root / ".logbook" / "policy.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        return p

    def attribution(self):
        order = ["none", "pseudonym", "named"]  # policy sets the ceiling
        want = self.cfg().get("attribution", "pseudonym")
        cap = self.policy().get("attribution", "pseudonym")
        return order[min(order.index(want) if want in order else 1, order.index(cap) if cap in order else 1)]

    def committers(self):
        """Ids of people with commits on this branch's first-parent line (set for free by the Anchorer, else one git log)."""
        if getattr(self, "_committers", None) is None:
            out = g.try_run(["log", "--first-parent", "-n500", "--format=%ae"], self.root)[1]
            self._committers = {user_id(e) for e in out.split() if e.strip()}
        return self._committers

    def trusted(self):
        """Whose notes may be injected into an agent's context. Storage, search and the viewer cover everyone regardless.
        Default: you, anyone with a commit on this line of history, and anyone you ran `trust` on.
        policy inject_from=self narrows it to you; cfg trust_committers=false turns the committer rule off."""
        t = {self.user}
        if self.policy().get("inject_from") != "self":
            t |= set(self.cfg().get("trusted", []))
            if self.cfg().get("trust_committers", True):
                t |= self.committers()
        return t

    def own_ref(self):
        base = BRANCH_PREFIX if self.cfg().get("transport") == "branches" else PREFIX
        return f"{base}/{self.user}/{self.device}"

    # private log ---------------------------------------------------------
    @property
    def pdir(self):
        return self.cdir / "private"

    def add_private(self, e):
        atomic_write(self.pdir / f"{e.id}.json", e.to_json())

    def get_private(self, eid):
        try:
            return from_json((self.pdir / f"{eid}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def drop_private(self, eid):
        try:
            (self.pdir / f"{eid}.json").unlink()
            return True
        except OSError:
            return False
