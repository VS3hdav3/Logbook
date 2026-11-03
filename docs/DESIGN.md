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

## Failure modes

| Case | Behaviour | Status |
|---|---|---|
| Shallow clone / CI | refs fetched at depth 1 (tip tree holds all entries); missing anchor commit renders "unverified" | tested |
| Host refuses `refs/logbook/*` | push falls back to `refs/heads/logbook/log/...`, remembered in config; readers handle both | tested with a pre-receive hook. **Fallback branches show in branch lists and may trigger CI on push: add a CI filter such as `branches-ignore: logbook/**`** |
| Two clones, same device id | push is rejected as diverged and reported; fix = re-`init` on one clone | message tested indirectly only |
| Squash merge / cherry-pick / rebase | ladder rungs; unresolved entries stay under their branch node | rungs tested; real GitHub squash messages not tested |
| Renamed file | `git log -M` over the first-parent line, both names resolve | tested for a simple rename; heavy edits + rename will be missed |
| Hostile entry | untrusted: searchable, never injected; trusted: sanitised; viewer: `textContent` + CSP | tested with fixtures |
| Leaked secret | `purge --push`; forks/mirrors may keep copies; rotate | tested locally |
| Agent without hooks | `logbook snippet` + `note`; git floor records commits as `auto-copied` | floor tested; snippet not tested with a real agent |
| Concurrent sessions | per-session lock file, unique entry ids, atomic replace with retry | lock logic tested lightly |
| Hook budget | spool + detached spawn; `SessionEnd` default budget is 1.5 s | measured on this Windows machine (median of 7, `python -m getlogbook capture` from a clean venv): `Stop` 355 ms, `SessionEnd` 352 ms, `UserPromptSubmit` 560 ms (was 540 / 563 / 1,252 ms before lean imports, batched git calls and a per-HEAD cache). **Not measured inside a real Claude Code session or on macOS/Linux.** About 80 ms is bare interpreter start and each `git` call costs ~45 ms |
| Push permissions | Any writer with push access can write any `refs/logbook/log/<anyone>/...` path. Clients cannot prevent it; the trust list limits the damage; only the host can enforce one-writer-per-ref | documented limit |

## Not verified

- Claude Code's real transcript JSONL schema (the parser is tolerant and only tested on a hand-made fixture) and real hook payloads.
- GitHub / GitLab / Bitbucket / Azure behaviour with custom refs; Copilot, Codex, Cursor, Gemini hook formats.
- Anything on macOS/Linux. `os.replace` retry and detached-process flags are written for Windows quirks but only run on Windows.
- Whether agents actually use injected notes (no hit-rate measurement exists).
- `retention_days`, signed commits, GDPR-grade erasure, legal hold: not built.

## Next steps (not started)

1. Run `logbook install --agent claude-code --write` in a throwaway repo with a real Claude Code session; capture real payloads and transcripts as golden fixtures.
2. Push to a private GitHub repo and test: custom ref push, squash-merge PR number re-anchoring, CI fetch step.
3. Stack-specific meaning (for example warehouse layers or lineage) stays out of this tool; another tool can attach tags to an anchor.

## Does a note save the investigation? (smoke test)

`bench/run_ab.py` builds a 12-file shop repo with a bug whose cause takes several reads to find, installs Logbook, and asks the
same question through `claude -p` with no notes (A) and with one note that records the cause (B). Both arms have the hooks.

| 4 rounds each | A: no notes | B: one note |
|---|---|---|
| Median tool calls | 5.5 | 3 |
| Median turns | 6.5 | 4 |
| Median input tokens (cache included) | 98,000 | 66,000 |
| Median cost | $0.048 | $0.043 |
| Correct answers | 4 of 4 | 4 of 4 |

Read it as a smoke test: one author-written task and note, a toy repo, four rounds, one model. B still reads about three times
because the note says to verify against the code. Real repos, real notes and teams are untested.

## Will the agent write the note itself? (smoke test)

`bench/run_ab.py --write-rate` runs the same bug question with no notes recorded and `Bash(logbook:*)` allowed, and counts runs in
which the agent ran `logbook note` without being asked. Four runs per setting, same toy repo:

| Setting | Wrote a note |
|---|---|
| Rules block and skill installed, no nudge | 0 of 4 |
| Stronger rules wording ("part of finishing a task") | 1 of 4 |
| Plus a once-per-turn block before finishing (`stop_hook_active` stops it looping) | 4 of 4 |

So instructions alone were not enough, and the Stop-hook block is now the default (`logbook config nudge context|off` to soften or
disable). A sample note it produced named the cause, what was read, what was ruled out, and what it had not verified. Four runs on a
toy task say little about real work; the cost is one extra turn on turns that read or searched three or more times.

