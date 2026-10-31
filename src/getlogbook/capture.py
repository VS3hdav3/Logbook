"""Capture: hook entry point, spool, reconcile, git post-commit floor, hook installers.

Design rules (from the review panels):
  * A hook only writes a small spool file and (maybe) spawns a detached worker. No model, no network, < 100 ms.
  * A hook never fails the agent: everything is caught, logged to errors.log, exit code 0.
  * `reconcile()` is the one sweep: spool -> transcript slices -> drafts; crash recovery; commits with no entry.
  * Drafts built without a model are provenance=inferred and are never injected (no 'why').
"""
from __future__ import annotations

import contextlib
import os
import time

from .entry import BODY_FIELDS, Entry, from_json, new_id
from .store import atomic_write

MARK_BEGIN, MARK_END = "# >>> logbook >>>", "# <<< logbook <<<"
CLAUDE_EVENTS = ["SessionStart", "UserPromptSubmit", "Stop", "PreCompact", "SessionEnd"]


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---- entries made by people/agents ---------------------------------------------------------------------------
def make_entry(repo, kind, topic, body, paths=None, provenance="agent-written", via="cli", pending=False, supersedes=()):
    from . import tree
    body = {k: str(v)[:2000] for k, v in body.items() if k in BODY_FIELDS and v}
    e = Entry(id=new_id(), kind=kind, topic=topic[:200], body=body, provenance=provenance, captured_via=via,
              supersedes=list(supersedes), created=now(),
              display=repo.cfg().get("display", "") if repo.attribution() == "named" else "")
    if pending:  # change entries are written before the commit exists; post-commit attaches the sha
        e.anchor = {"paths": list(paths or [])}
        atomic_write(repo.cdir / "pending" / f"{e.id}.json", e.to_json())
    else:
        e.anchor = tree.anchor_for(repo, paths=paths)
        repo.add_private(e)
    return e


def post_commit(repo):
    """Attach pending change entries to the commit that was just made. Infers nothing here (reconcile does)."""
    from . import tree
    n = 0
    pdir = repo.cdir / "pending"
    for p in sorted(pdir.glob("*.json")) if pdir.exists() else []:
        try:
            e = from_json(p.read_text(encoding="utf-8"))
            e.anchor = tree.anchor_for(repo)  # paths come from the commit itself
            repo.add_private(e)
            p.unlink()
            n += 1
        except (OSError, ValueError) as ex:
            repo.error(f"post-commit {p.name}: {ex}")
    return n


# ---- spool + detached worker ---------------------------------------------------------------------------------
@contextlib.contextmanager
def _lock(path, timeout=1.0):
    """Tiny cross-platform lock (O_EXCL file, stale after 10 s). Yields False if it could not be taken."""
    path.parent.mkdir(parents=True, exist_ok=True)
    end, fd = time.time() + timeout, None
    while time.time() < end:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > 10:
                    path.unlink()
            except OSError:
                pass
            time.sleep(0.02)
    try:
        yield fd is not None
    finally:
        if fd is not None:
            os.close(fd)
            try:
                path.unlink()
            except OSError:
                pass
