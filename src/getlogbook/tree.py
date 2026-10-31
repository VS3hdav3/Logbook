"""Anchoring and the branch -> commit -> entry tree.

Re-anchor ladder (first hit wins, the rung is recorded and shown, never presented as fact):
  exact sha -> patch-id -> PR number -> tree hash -> unresolved (kept under its branch node).
Entries are never rewritten; everything here is derived at read time.
"""
from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

from . import git as g
from .store import atomic_write, user_id

SPINE_LIMIT = 500
_PR = re.compile(r"\(#(\d+)\)")
_LAYERS = [("raw", ("raw_", "src_", "source_")), ("staging", ("stg_", "staging_")), ("intermediate", ("int_",)),
           ("mart", ("fct_", "dim_", "mart_", "rpt_"))]
_DIRS = {"raw": "raw", "sources": "raw", "staging": "staging", "intermediate": "intermediate", "marts": "mart", "mart": "mart"}


def layer_of(name_or_path):
    p = PurePosixPath(str(name_or_path).replace("\\", "/"))
    for part in p.parts[:-1]:
        if part.lower() in _DIRS:
            return _DIRS[part.lower()]
    stem = p.stem.lower()
    for layer, prefixes in _LAYERS:
        if stem.startswith(prefixes):
            return layer
    return None


def models_of(paths):
    """dbt-style model names: stems of .sql/.py files. Works for any repo; non-model files just yield stems too."""
    seen, out = set(), []
    for p in paths:
        pp = PurePosixPath(p.replace("\\", "/"))
        if pp.suffix.lower() in (".sql", ".py") and pp.stem not in seen:
            seen.add(pp.stem)
            out.append(pp.stem)
    return out


def spine(repo, limit=SPINE_LIMIT):
    rc, out, _ = g.try_run(["log", "--first-parent", f"-n{limit}", "--format=%H%x1f%T%x1f%P%x1f%an%x1f%aI%x1f%s%x1f%ae"], repo.root)
    rows = []
    for line in out.splitlines() if rc == 0 else []:
        h, t, p, an, ad, s, ae = (line.split("\x1f") + [""] * 7)[:7]
        rows.append({"sha": h, "tree": t, "parent": p.split()[0] if p else "", "author": an, "date": ad, "subject": s, "email": ae})
    return rows


def get_derived(repo, head=None):
    """Per-HEAD cache of expensive git lookups (patch-ids, renames, tracked model names), kept in memory and on disk."""
    d = getattr(repo, "_derived", None)
    if d is not None and (head is None or d.get("head") == head):
        return d
    head = head if head is not None else (g.head_sha(repo.root) or "")
    try:
        d = json.loads((repo.cdir / "derived.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if d.get("head") != head:
        d = {"head": head}
    repo._derived = d
    return d


def save_derived(repo):
    try:
        atomic_write(repo.cdir / "derived.json", json.dumps(repo._derived))
    except OSError:
        pass


def patch_ids(repo, limit=SPINE_LIMIT):
    """patch-id -> sha for the spine (one subprocess pair, only called when an entry needs it)."""
    rc, patch, _ = g.try_run(["log", "--first-parent", f"-n{limit}", "-p", "--format=%H"], repo.root)
    if rc or not patch.strip():
        return {}
    rc, out, _ = g.try_run(["patch-id", "--stable"], repo.root, input=patch)
    return {line.split()[0]: line.split()[1] for line in out.splitlines() if len(line.split()) == 2} if rc == 0 else {}


class Anchorer:
    def __init__(self, repo):
        self.repo = repo
        self.sp = spine(repo)
        self.by_sha = {c["sha"]: i for i, c in enumerate(self.sp)}
        repo._committers = {user_id(c["email"]) for c in self.sp if c["email"]}  # reuse this log: no extra subprocess
        self.by_tree = {}
        self.by_pr = {}
        for c in self.sp:
            self.by_tree.setdefault(c["tree"], c["sha"])
            m = _PR.search(c["subject"])
            if m:
                self.by_pr.setdefault(m.group(1), c["sha"])
        self._pids = None
        self.derived = get_derived(repo, self.sp[0]["sha"] if self.sp else "")
        self.shallow = (repo.common / "shallow").exists()  # no subprocess needed
        self.exists = None

    def prime(self, shas):
        """One batched existence check for every anchor sha we are about to place."""
        self.exists = g.existing_commits(self.repo.root, shas)

    def _has(self, sha):
        return sha in self.exists if self.exists is not None else g.commit_exists(self.repo.root, sha)

    def place(self, a):
        """-> (sha_on_spine | None, state, rung). state: exact | rewritten | orphaned | unknown | unanchored."""
        sha = a.get("sha", "")
        if not sha:
            return None, "unanchored", ""
        if sha in self.by_sha:
            return sha, "exact", "sha"
        if self._has(sha):
            return sha, "exact", "sha (off first-parent line)"
        if a.get("patch_id"):
            if self._pids is None:
                if "patch_ids" not in self.derived:
                    self.derived["patch_ids"] = patch_ids(self.repo)
                    save_derived(self.repo)
                self._pids = self.derived["patch_ids"]
            if a["patch_id"] in self._pids:
                return self._pids[a["patch_id"]], "rewritten", "patch-id"
        if a.get("pr") and a["pr"] in self.by_pr:
            return self.by_pr[a["pr"]], "rewritten", "PR number"
        if a.get("tree") and a["tree"] in self.by_tree:
            return self.by_tree[a["tree"]], "rewritten", "tree hash"
        return None, ("unknown" if self.shallow else "orphaned"), ""

    def behind(self, sha):
        """Commits between the matched commit and HEAD (distance from the nearest *matched* commit)."""
        if sha in self.by_sha:
            return self.by_sha[sha]
        rc, out, _ = g.try_run(["rev-list", "--count", f"{sha}..HEAD"], self.repo.root)
        return int(out.strip()) if rc == 0 and out.strip().isdigit() else None
