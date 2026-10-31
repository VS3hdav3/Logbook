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
from .store import atomic_write

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
