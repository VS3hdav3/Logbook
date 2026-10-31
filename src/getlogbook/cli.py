"""logbook CLI. Exit codes for scripts: 0 found, 3 ambiguous (candidates listed), 4 nothing matched."""
from __future__ import annotations


from . import sync, tree
from .entry import BODY_FIELDS
from .safety import sanitize as safety_sanitize
from .store import Repo

SHARE_FIELDS = ("summary", "what", "why", "wrong", "fix")  # allowlist: evidence is opt-in


def out(s=""):
    print(s)


def txt(v, s, cap=600):
    """Text written by another writer is untrusted: an agent reading this output would be reading their words."""
    return s if v["mine"] else safety_sanitize(s, cap)


def line(v):
    where = {"exact": "anchor ok", "rewritten": f"re-anchored by {v['rung']}", "orphaned": "anchor commit gone",
             "unknown": "anchor unverified (shallow)", "unanchored": "no commit"}[v["state"]]
    behind = f", {v['behind']} behind HEAD" if v["behind"] is not None else ""
    return (f"{v['id']}  {v['kind']:<7} {v['scope']:<7} by {v['author']:<10} {v['provenance']:<13} "
            f"{where}{behind}\n    {txt(v, v['topic'], 200)}")


def detail(v):
    rows = [line(v), f"    branch {txt(v, v['branch'], 100)}  commit {v['sha'][:8]} {txt(v, v['subject'], 150)}",
            f"    models {txt(v, ', '.join(v['models']), 200) or '-'}  layers {', '.join(v['layers']) or '-'}  captured via {txt(v, v['captured_via'], 40)}"]
    for k in BODY_FIELDS:
        if v["body"].get(k):
            rows.append(f"    {k}: {txt(v, v['body'][k])}")
    if not v["mine"]:
        rows.append("    (text from another writer is shown sanitised: links, code and instruction-like lines are removed)")
    return "\n".join(rows)


def need_repo():
    try:
        r = Repo(".")
    except Exception:
        raise SystemExit("logbook: not inside a git repository")
    if not r.cfg().get("user"):
        raise SystemExit("logbook: run `logbook init` (or `logbook join`) first")
    return r


def views(repo):
    return tree.all_views(repo)


# ---- commands --------------------------------------------------------------------------------------------------
def cmd_init(a):
    r = Repo(".")
    c = r.init()
    if a.attribution:
        c["attribution"] = a.attribution
        r.save_cfg(c)
    out(f"initialised. you are {c['user']} (device {c['device']}); attribution: {r.attribution()}")
    out("next: `logbook install-hook` (git floor) and `logbook install --agent claude-code --write`")


def cmd_join(a):
    r = Repo(".")
    r.init()
    added = sync.ensure_fetch_config(r, a.remote) if a.remote in sync.remotes(r) else 0
    res = sync.fetch(r, a.remote) if a.remote in sync.remotes(r) else {"ok": False, "error": "no such remote"}
    shared, _ = r.load_shared()
    writers = {(l.user, l.device) for l in shared}
    out(f"joined. fetch refspecs added: {added}; fetch {'ok' if res['ok'] else 'failed: ' + res['error']}")
    out(f"found {len({u for u, _ in writers})} writers on {len(writers)} devices, {len(shared)} entries")
    for u in sorted({u for u, _ in writers}):
        out(f"  writer {u}{'  (you)' if u == r.user else '  [not trusted: searchable, never auto-injected; `logbook trust ' + u + '`]' if u not in r.trusted() else '  [trusted]'}")
