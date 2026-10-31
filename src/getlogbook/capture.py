"""Capture: hook entry point, spool, reconcile, git post-commit floor, hook installers.

Design rules (from the review panels):
  * A hook only writes a small spool file and (maybe) spawns a detached worker. No model, no network, < 100 ms.
  * A hook never fails the agent: everything is caught, logged to errors.log, exit code 0.
  * `reconcile()` is the one sweep: spool -> transcript slices -> drafts; crash recovery; commits with no entry.
  * Drafts built without a model are provenance=inferred and are never injected (no 'why').
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import git as g
from .entry import BODY_FIELDS, Entry, from_json, new_id
from .store import Repo, atomic_write

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


def spawn_detached(args, cwd):
    if os.environ.get("LOGBOOK_NO_SPAWN"):  # tests
        return
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, cwd=str(cwd))
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        try:  # escape the agent's job object if allowed, otherwise fall back
            subprocess.Popen(args, creationflags=flags | 0x01000000, **kw)  # CREATE_BREAKAWAY_FROM_JOB
        except OSError:
            subprocess.Popen(args, creationflags=flags, **kw)
    else:
        subprocess.Popen(args, start_new_session=True, **kw)


def spool_event(repo, event, agent, payload):
    head, branch, paths, _ = g.state(repo.root)  # one subprocess
    item = {"event": event, "agent": agent, "t": time.time(), "head": head or "", "branch": branch,
            "paths": paths[:40], "session": str(payload.get("session_id", ""))[:80], "transcript": str(payload.get("transcript_path", "")),
            "prompt": str(payload.get("prompt", ""))[:2000], "last": str(payload.get("last_assistant_message", ""))[:4000]}
    atomic_write(repo.cdir / "spool" / f"{int(time.time() * 1000):013d}-{os.urandom(3).hex()}.json", json.dumps(item))
    if item["session"] and item["transcript"]:  # copy the new bytes now: agents prune old transcripts
        checkpoint(repo, item["session"], item["transcript"])


def handle_hook(event, agent, raw):
    """Entry point for `logbook capture`. Returns text for stdout (may be ''). Never raises."""
    repo = None
    try:
        payload = json.loads(raw) if raw and raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        repo = Repo(payload.get("cwd") or ".")
        cfg = repo.cfg()
        if not cfg.get("user"):
            return ""
        out = ""
        if event in ("SessionStart", "UserPromptSubmit", "PreToolUse"):
            from . import recall  # only the prompt-time hooks need retrieval; Stop/SessionEnd stay lean
            files = []
            ti = payload.get("tool_input")
            if event == "PreToolUse" and isinstance(ti, dict) and ti.get("file_path"):
                try:
                    files = [Path(ti["file_path"]).resolve().relative_to(repo.root.resolve()).as_posix()]
                except (ValueError, OSError):
                    files = []
            out = recall.hook_json(event, recall.digest(repo, event, payload.get("prompt", ""), files, str(payload.get("session_id", ""))))
        if event in ("Stop", "PreCompact", "SessionEnd"):  # prompt-time hooks stay read-only and fast
            spool_event(repo, event, agent, payload)
        if event in ("SessionStart", "PreCompact", "SessionEnd"):
            spawn_detached([cfg.get("interpreter") or sys.executable, "-m", "getlogbook", "reconcile", "--quiet"], repo.root)
        return out
    except Exception as ex:  # a hook must never break the agent
        try:
            (repo.error if repo else (lambda m: None))(f"capture {event}: {ex!r}")
        except Exception:
            pass
        return ""


# ---- reconcile -----------------------------------------------------------------------------------------------
def _msg(obj):
    m = obj.get("message") if isinstance(obj.get("message"), dict) else obj
    role = m.get("role") or obj.get("type") or ""
    c = m.get("content")
    if isinstance(c, list):
        c = " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return role, c.strip() if isinstance(c, str) else ""
