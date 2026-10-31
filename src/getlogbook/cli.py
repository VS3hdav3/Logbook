"""logbook CLI. Exit codes for scripts: 0 found, 3 ambiguous (candidates listed), 4 nothing matched."""
from __future__ import annotations

import json
import sys

from . import capture, sync, tree
from .entry import BODY_FIELDS
from .safety import digest_hash, looks_tabular, redact
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


def cmd_note(a):
    r = need_repo()
    body = {k: getattr(a, k) for k in BODY_FIELDS if getattr(a, k, None)}
    if a.from_stdin:
        body["summary"] = sys.stdin.read().strip()[:600]
    if not body.get("summary"):
        raise SystemExit("logbook: --summary is required (what happened, in a sentence)")
    if a.kind == "finding" and not (body.get("why") or body.get("wrong")):
        out("note: no --why/--wrong given; this entry will be searchable but never injected into agent context")
    paths = a.paths.split(",") if a.paths else None
    e = capture.make_entry(r, a.kind, a.topic or body["summary"][:80], body, paths=paths, via="cli",
                           pending=(a.kind == "change" and a.before_commit))
    out(f"recorded {e.id} ({'pending: attaches to your next commit' if a.before_commit and a.kind == 'change' else 'private'})")


def share_copy(r, e, include_evidence, allow_table):
    """Build the exact object that would be published: allowlisted, redacted, size-capped. Returns (entry, findings)."""
    deny = r.cfg().get("deny", [])
    found = []
    fields = SHARE_FIELDS + (("evidence",) if include_evidence else ())
    body = {}
    for k in fields:
        if e.body.get(k):
            body[k], f = redact(e.body[k], deny)
            found += f
    if not allow_table and any(looks_tabular(v) for v in body.values()):
        raise SystemExit("logbook: a field looks like pasted table rows; refusing. Remove it, or pass --allow-table after checking it.")
    c = e.copy(body=body, redacted=True, display=r.cfg().get("display", "") if r.attribution() == "named" else "")
    c.topic, f = redact(e.topic, deny)
    found += f
    a = dict(e.anchor)
    for k in ("subject", "branch"):
        a[k], f = redact(a.get(k, ""), deny)
        found += f
    c.anchor = a
    return c, found


def cmd_publish(a):
    r = need_repo()
    if not r.policy().get("publish", True):
        raise SystemExit("logbook: this repo's policy has publishing turned off (.logbook/policy.json)")
    ready = []
    for eid in a.ids:
        e = r.get_private(eid)
        if not e:
            raise SystemExit(f"logbook: no private entry {eid}")
        c, found = share_copy(r, e, a.include_evidence, a.allow_table)
        text = c.to_json()
        out(f"--- would publish {eid} (redaction: {len(found)} item(s) masked{': ' + ', '.join(sorted(set(found))) if found else ''})")
        out(text)
        ready.append((c, digest_hash(text)))
    out("Published entries cannot be fully recalled: forks and mirrors may keep copies. Rotate any secret that appears above.")
    if not a.yes and input("Publish exactly the text above? [y/N] ").strip().lower() != "y":
        raise SystemExit("aborted; nothing published")
    for c, h in ready:
        if digest_hash(c.to_json()) != h:
            raise SystemExit("logbook: entry changed after preview; aborting")
    ref = r.publish([c for c, _ in ready])
    out(f"published {len(ready)} entr{'y' if len(ready) == 1 else 'ies'} to {ref} (local). `logbook sync` pushes it.")
    if a.push:
        out(json.dumps(sync.push(r)))
