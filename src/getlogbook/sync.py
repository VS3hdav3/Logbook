"""Fetch/push of logbook refs. Others' refs land in refs/logbook-remote/<remote>/ so a fetch can never
clobber your own unpushed ref. We never write remote.<r>.push (that would hijack a plain `git push`)."""
from __future__ import annotations

import re
from pathlib import Path

from . import git as g
from .store import BRANCH_PREFIX, PREFIX, REMOTE_NS, Repo


_REFUSED = re.compile(r"denied|declined|refusing|not permitted|protected|forbidden|403|pre-receive|hook|unable to create", re.I)
_DIVERGED = re.compile(r"non-fast-forward|fetch first|stale info|rejected.*already exists", re.I)


def fetch_specs(remote):
    return [f"+{PREFIX}/*:{REMOTE_NS}/{remote}/log/*", f"+{BRANCH_PREFIX}/*:{REMOTE_NS}/{remote}/branchlog/*"]


def remotes(repo):
    return g.run(["remote"], repo.root).split()


def ensure_fetch_config(repo, remote="origin"):
    have = g.try_run(["config", "--get-all", f"remote.{remote}.fetch"], repo.root)[1].splitlines()
    added = 0
    for spec in fetch_specs(remote):
        if spec not in have:
            g.run(["config", "--add", f"remote.{remote}.fetch", spec], repo.root)
            added += 1
    return added


def fetch(repo, remote="origin", depth=None):
    args = ["fetch", "--no-tags", "--quiet"] + ([f"--depth={depth}"] if depth else []) + [remote, *fetch_specs(remote)]
    rc, _, err = g.try_run(args, repo.root)
    return {"ok": rc == 0, "error": err.strip() if rc else ""}


def push(repo, remote="origin", force=False):
    ref = repo.own_ref()
    if g.try_run(["rev-parse", "--verify", "-q", ref], repo.root)[0]:
        return {"ok": True, "via": "nothing to push", "ref": ref}
    flag = []
    if force:  # single writer per ref, so force is safe; the lease still protects against a surprise remote tip
        tip = g.try_run(["ls-remote", remote, ref], repo.root)[1].split()
        flag = [f"--force-with-lease={ref}:{tip[0]}"] if tip else ["--force"]
    rc, _, err = g.try_run(["push", "--quiet", *flag, remote, f"{ref}:{ref}"], repo.root)
    if rc == 0:
        return {"ok": True, "via": repo.cfg().get("transport", "refs"), "ref": ref}
    if _DIVERGED.search(err):
        return {"ok": False, "error": "remote copy of your ref diverged (another clone of this device id?): " + err.strip(), "ref": ref}
    if repo.cfg().get("transport") != "branches" and _REFUSED.search(err):
        # host refused a custom ref namespace: fall back to orphan branches and remember the choice
        bref = f"{BRANCH_PREFIX}/{repo.user}/{repo.device}"
        tip = g.run(["rev-parse", ref], repo.root).strip()
        g.run(["update-ref", bref, tip], repo.root)
        rc2, _, err2 = g.try_run(["push", "--quiet", *flag, remote, f"{bref}:{bref}"], repo.root)
        if rc2 == 0:
            c = repo.cfg()
            c["transport"] = "branches"
            repo.save_cfg(c)
            return {"ok": True, "via": "branches (host rejected custom refs)", "ref": bref}
        err = err2 or err
    return {"ok": False, "error": err.strip(), "ref": ref}


def sync(repo, remote="origin", fetch_only=False, depth=None):
    out = {"fetch": fetch(repo, remote, depth)}
    if not fetch_only:
        out["push"] = push(repo, remote)
    shared, _ = repo.load_shared()
    out["writers"] = len({(l.user, l.device) for l in shared})
    out["entries"] = len(shared)
    return out


def doctor(repo, remote="origin"):
    """List of (level, message). Levels: ok | warn | fail."""
    r = []
    ok = lambda m: r.append(("ok", m))
    warn = lambda m: r.append(("warn", m))
    c = repo.cfg()
    if not c.get("user"):
        r.append(("fail", "not initialised: run `logbook init`"))
        return r
    ok(g.run(["version"], repo.root).strip())
    ok(f"interpreter pinned: {c.get('interpreter')}")
    ok(f"transport: {c.get('transport', 'refs')}; attribution: {repo.attribution()}")
    if g.is_shallow(repo.root):
        warn("shallow clone: anchors to missing commits show as 'unverified' (git fetch --unshallow to fix)")
    if remote in remotes(repo):
        have = g.try_run(["config", "--get-all", f"remote.{remote}.fetch"], repo.root)[1]
        if fetch_specs(remote)[0] in have:
            ok("fetch refspec present")
        else:
            warn(f"fetch refspec missing: run `logbook join` (plain `git fetch` will skip logbook refs)")
    else:
        warn(f"no remote named {remote!r}: entries stay local until you add one")
    hp = g.try_run(["config", "--get", "core.hooksPath"], repo.root)[1].strip()
    hooks_dir = g.run(["rev-parse", "--path-format=absolute", "--git-path", "hooks"], repo.root).strip()
    hf = Path(hooks_dir) / "post-commit"
    if hf.exists() and "logbook" in hf.read_text(encoding="utf-8", errors="ignore"):
        ok(f"post-commit hook installed ({hooks_dir})")
    else:
        warn("post-commit floor not installed: `logbook install-hook` (commits will not be recorded automatically)")
    if hp:
        warn(f"core.hooksPath is set ({hp}); hooks are read from there")
    err = repo.cdir / "errors.log"
    if err.exists() and err.stat().st_size:
        warn(f"hook errors logged: {err}")
    pend = len(list((repo.cdir / "spool").glob("*.json"))) if (repo.cdir / "spool").exists() else 0
    if pend:
        warn(f"{pend} spooled hook events not yet processed (run `logbook reconcile`)")
    return r
