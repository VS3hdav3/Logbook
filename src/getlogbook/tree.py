"""Anchoring and the branch -> commit -> entry tree.

Re-anchor ladder (first hit wins, the rung is recorded and shown, never presented as fact):
  exact sha -> patch-id -> PR number -> tree hash -> unresolved (kept under its branch node).
Entries are never rewritten; everything here is derived at read time.
"""
from __future__ import annotations

import json
import re
import time
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


def anchor_for(repo, sha=None, paths=None, dirty=None, pr=""):
    """Snapshot of an anchor. Denormalised on purpose: it must still render when the commit is gone."""
    head, br, _, is_dirty = g.state(repo.root)
    sha = sha or head
    a = {"sha": sha or "", "branch": br, "pr": pr, "dirty": is_dirty if dirty is None else dirty}
    if sha:
        info = g.commit_info(repo.root, sha) or {}
        a.update(tree=info.get("tree", ""), parent=info.get("parent", ""), subject=info.get("subject", ""),
                 date=info.get("date", ""), patch_id=g.patch_id(repo.root, sha) or "")
        if paths is None:
            paths = g.changed_paths(repo.root, sha)
    a["paths"] = list(paths or [])
    a["models"] = models_of(a["paths"])
    return a


def renames(repo, limit=SPINE_LIMIT):
    """old name -> newest name, from rename detection over the first-parent line. Derived cache, heuristic."""
    d = get_derived(repo)
    if "renames" in d:
        return d["renames"]
    rc, out, _ = g.try_run(["log", "--first-parent", f"-n{limit}", "-M", "--name-status", "--diff-filter=R", "--format="], repo.root)
    pairs = []  # newest first
    for line in out.splitlines() if rc == 0 else []:
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            pairs.append((parts[1], parts[2]))
    alias = {}
    for old, new in reversed(pairs):  # oldest first, so chains resolve to the latest name
        for k, v in list(alias.items()):
            if v == old:
                alias[k] = new
        alias[old] = new
    d["renames"] = alias
    save_derived(repo)
    return alias


def aliases_for(repo, name):
    """All historical names for a model (stems), for query expansion."""
    al = renames(repo)
    stems = {PurePosixPath(k).stem: PurePosixPath(v).stem for k, v in al.items()}
    names = {name}
    for old, new in stems.items():
        if name in (old, new):
            names |= {old, new}
    return names


def age_days(created):
    try:
        return max(0, int((time.time() - time.mktime(time.strptime(created[:19], "%Y-%m-%dT%H:%M:%S"))) // 86400))
    except (ValueError, OverflowError):
        return None


def view(repo, loaded, anch):
    """Flat, JSON-safe dict for one entry (UI and CLI share this)."""
    e, a = loaded.entry, loaded.entry.anchor
    sha, state, rung = anch.place(a)
    behind = anch.behind(sha) if sha else None
    layers = sorted({l for l in (layer_of(p) for p in a.get("paths", [])) if l} |
                    {l for l in (layer_of(m) for m in a.get("models", [])) if l})
    return {"id": e.id, "kind": e.kind, "topic": e.topic, "body": e.body, "provenance": e.provenance,
            "scope": loaded.scope, "author": repo.label(loaded), "mine": loaded.user == repo.user,
            "trusted": loaded.user in repo.trusted(), "state": state, "rung": rung, "behind": behind,
            "age_days": age_days(e.created), "created": e.created, "captured_via": e.captured_via,
            "branch": a.get("branch", ""), "subject": a.get("subject", ""), "sha": a.get("sha", ""), "placed": sha or "",
            "paths": a.get("paths", []), "models": a.get("models", []), "layers": layers, "dirty": a.get("dirty", False),
            "supersedes": e.supersedes, "redacted": e.redacted}
