# logbook: design and decision log

Status: working prototype, stdlib only. Verified by `tests/` (unit, 17) and `logbook demo` (integration, ~35 checks) on
Windows with Python 3.13 and git 2.51 only. Nothing here has been run on macOS/Linux, on a real GitHub/GitLab remote,
or against a real Claude Code session.

## Shape

    private log   .git/logbook/private/<id>.json        everything, unredacted, never tracked, shared by worktrees
    shared log    refs/logbook/log/<user>/<device>       one writer per ref; tip tree = every entry as entries/<id>.json
    fetched       refs/logbook-remote/<remote>/log/...   other people's refs, in their own namespace (a fetch can never
                                                           overwrite your unpushed ref); fallback layout under .../branchlog/...
    read time     merge by entry id, hide purged (tombstone) and same-author-superseded, overlay private
    tree          branch -> first-parent commits -> entries; each entry carries an anchor state and the rung that matched

Authorship = the ref path (`<user>/<device>`), never a field in the file. `<user>` = sha256(git user.email)[:10] (stable across
machines, pseudonymous), `<device>` = random per clone.

## What the review panels changed (5 roles x 5 issue clusters = 25 agents, reports are model output, not facts)

| Cluster | Adopted | Declined / deferred |
|---|---|---|
| Storage & sync | Others' refs fetched into `refs/logbook-remote` (the panel caught that `+refs/logbook/*:refs/logbook/*` would clobber your own unpushed ref); gists dropped; `gc` = parentless squash behind `--yes`; reactive fallback to orphan branches (no junk probe refs); `join` onboarding; kill switch in `.logbook/policy.json`; non-PII user id | Pre-squash archive refs; fork-PR support (v1 limit: maintainers add the fork remote by hand); alias map committed to the ref; server-side one-writer enforcement (only the host can, documented below) |
| Anchoring | Re-anchor ladder (sha -> patch-id -> PR number -> tree hash -> unresolved) with the rung and an anchor state shown on every entry; commits-behind measured from the matched commit; anchors denormalised so a shallow clone still renders; entries never rewritten | Hybrid logical clock; persisted rename map (renames are a derived, heuristic view-time lookup); manual `relink`; ref-tip reflog (`seen/` dir exists, unused) |
| Trust & privacy | Injection from you, anyone with a commit on this history, and writers you `trust` (the panels asked for self-only; changed because it made every teammate run a manual step); allowlisted fields; evidence opt-in; row-shaped text refused; preview hash check; one `sanitize` path used by inject, CLI output and viewer; id-only tombstones; audit log; policy ceiling for attribution | Signed-commit verification; maintainer-initiated purge, legal hold, retention enforcement (`retention_days` is read but **not enforced**), `export --since` |
| Capture & agents | One `capture` command, spool-first, never fails the agent, detached worker with job-object breakaway fallback, absolute interpreter, transcript slices copied at the hook under a lock, one `reconcile()` sweep, chained git hook, idempotent merge/uninstall of Claude settings | Copilot / Codex / Cursor / Gemini adapters, golden-file transcript tests, web-UI commit inference in CI, `doctor --team` |
| Cost & retrieval | `backend none` only; digest <= 1,500 chars, finding-first, trusted-only, needs a why/wrong, silent when nothing matches, once per session; in-memory scan instead of SQLite/FTS5; live server kept (requirement) but hardened | LLM summarising backend, MCP tool, cost ledger beyond `stats`, hit-rate measurement, static `view` export |

Problems found by running code, not by the panels: a non-fast-forward push was mis-read as "host refuses custom refs";
`--force-with-lease` without an explicit expected value fails for custom refs; `logbook explain` printed hostile text raw
even though `inject` sanitised it; `logbook serve` did not flush its URL, so a caller reading it through a pipe hung forever;
and hooks took 0.5-1.25 s because of ~190 ms of imports and 9-10 `git` subprocesses. All are fixed; the first three have tests.
One panel suggestion I rejected: "default to orphan branches" (a senior-advisor view). You chose refs, and branches show in
branch lists and can trigger CI, so branches are only the reactive fallback.

