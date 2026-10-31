"""Thin wrapper over the git CLI. Needs git >= 2.31 (--path-format=absolute)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _env(extra=None):
    e = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    if extra:
        e.update(extra)
    return e


def try_run(args, cwd, input=None, env=None):
    if isinstance(input, str):
        input = input.encode("utf-8")
    p = subprocess.run(["git", "-C", str(cwd), *args], input=input, capture_output=True, env=_env(env))
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def run(args, cwd, input=None, env=None):
    rc, out, err = try_run(args, cwd, input, env)
    if rc:
        raise GitError(f"git {' '.join(args)}: {err.strip()}")
    return out


def repo_paths(cwd):
    """(toplevel, common git dir) in one subprocess."""
    out = run(["rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"], cwd).splitlines()
    return Path(out[0].strip()), Path(out[1].strip())


def state(cwd):
    """(head sha or None, branch, changed paths, dirty) in one subprocess."""
    rc, out, _ = try_run(["status", "--porcelain=v2", "--branch", "-z"], cwd)
    head, br, paths = None, "HEAD", []
    for rec in out.split("\0") if rc == 0 else []:
        if rec.startswith("# branch.oid "):
            head = None if rec.endswith("(initial)") else rec.split()[2]
        elif rec.startswith("# branch.head "):
            br = rec.split(" ", 2)[2]
        elif rec[:2] in ("1 ", "u "):
            paths.append(rec.split(" ", 8 if rec[0] == "1" else 10)[-1])
        elif rec[:2] == "2 ":
            paths.append(rec.split(" ", 9)[-1])
        elif rec[:2] == "? ":
            paths.append(rec[2:])
    return head, br, paths, bool(paths)


def existing_commits(cwd, shas):
    """Which of these shas are commits present locally (one subprocess)."""
    shas = [s for s in dict.fromkeys(shas) if s]
    if not shas:
        return set()
    p = subprocess.run(["git", "-C", str(cwd), "cat-file", "--batch-check"], input=("\n".join(shas) + "\n").encode(),
                       capture_output=True, env=_env())
    return {l.split()[0] for l in p.stdout.decode("utf-8", "replace").splitlines() if len(l.split()) >= 2 and l.split()[1] == "commit"}


def toplevel(cwd):
    return Path(run(["rev-parse", "--show-toplevel"], cwd).strip())
