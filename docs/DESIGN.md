# logbook: design and decision log

> **Partly out of date (kept as the record of the first design).** Since then: one shelf per person (`<user>/000000`) replaced per-device refs; `git push` no longer sends notes (`logbook sync` does);
> the browser viewer was removed; Claude Code hook payloads are now verified in a real session; provenance, grounding checks, publish modes and notes as `key: value` lines were added.
> Current state and plan: `docs/ROADMAP.md`; next design: `docs/TIDY-AND-SUMMARY-TREE.md`.

Status: working package, standard library only. The unit tests (`tests/`) run in CI on Windows, macOS and Linux (Python 3.10 and 3.13); `logbook demo` and `bench/e2e.py` (against an installed build)
pass; real `claude -p` sessions have been run for the hooks, the permission hook, the scribe and tidy. Not run: against a real GitHub or GitLab remote with custom refs, on a big repo, or with
an agent other than Claude Code (see the "Verify" list in `docs/ROADMAP.md`).

## Shape

    private log   .git/logbook/private/<id>.json        everything, unredacted, never tracked, shared by worktrees
    shared log    refs/logbook/log/<user>/000000         one shelf per person; tip tree = every entry as entries/<id>.json
    fetched       refs/logbook-remote/<remote>/log/...   other people's refs, in their own namespace (a fetch can never
                                                           overwrite your unpushed ref); fallback layout under .../branchlog/...
    read time     merge by entry id, hide purged (tombstone) and same-author-superseded, overlay private
    tree          branch -> first-parent commits -> entries; each entry carries an anchor state and the rung that matched

Authorship = the ref path (`<user>/000000`), never a field in the file. (0.0.2 used a random per-clone device id as the second part; those refs are still read and are folded into the shelf on the next publish or sync.) `<user>` = sha256(git user.email)[:10] (stable across
machines, pseudonymous), the second part is a fixed hex constant, kept in that shape so 0.0.2 readers still match it.

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
even though `inject` sanitised it; and hooks took 0.5-1.25 s because of ~190 ms of imports and 9-10 `git` subprocesses. All are fixed; the first three have tests.
One panel suggestion I rejected: "default to orphan branches" (a senior-advisor view). You chose refs, and branches show in
branch lists and can trigger CI, so branches are only the reactive fallback.

## Failure modes

| Case | Behaviour | Status |
|---|---|---|
| Shallow clone / CI | refs fetched at depth 1 (tip tree holds all entries); missing anchor commit renders "unverified" | tested |
| Host refuses `refs/logbook/*` | push falls back to `refs/heads/logbook/log/...`, remembered in config; readers handle both | tested with a pre-receive hook. **Fallback branches show in branch lists and may trigger CI on push: add a CI filter such as `branches-ignore: logbook/**`** |
| Same person, two machines | push is rejected as non-fast-forward, so sync fetches the remote shelf, merges the union of both trees (a purge's tombstone wins, and then the result is force-pushed with a lease) and pushes again | tested |
| Squash merge / cherry-pick / rebase | ladder rungs; unresolved entries stay under their branch node | rungs tested; real GitHub squash messages not tested |
| Renamed file | `git log -M` over the first-parent line, both names resolve | tested for a simple rename; heavy edits + rename will be missed |
| Hostile entry | untrusted: searchable, never injected; trusted: sanitised | tested with fixtures |
| Leaked secret | `purge --push`; forks/mirrors may keep copies; rotate | tested locally |
| Agent without hooks | `logbook snippet` + `note`; git floor records commits as `auto-copied` | floor tested; snippet not tested with a real agent |
| Concurrent sessions | per-session lock file, unique entry ids, atomic replace with retry | lock logic tested lightly |
| Hook budget | spool + detached spawn; `SessionEnd` default budget is 1.5 s | measured on this Windows machine (median of 7, `python -m getlogbook capture` from a clean venv): `Stop` 355 ms, `SessionEnd` 352 ms, `UserPromptSubmit` 560 ms (was 540 / 563 / 1,252 ms before lean imports, batched git calls and a per-HEAD cache). **Not measured inside a real Claude Code session or on macOS/Linux.** About 80 ms is bare interpreter start and each `git` call costs ~45 ms |
| Push permissions | Any writer with push access can write any `refs/logbook/log/<anyone>/...` path. Clients cannot prevent it; the trust list limits the damage; only the host can enforce one-writer-per-ref | documented limit |

## Not verified

- Claude Code's hook payloads and transcript were checked in real sessions (prompt, tool-use including inside a subagent, stop, subagent stop, session end) on one Claude Code version; other versions are untested.
  Copilot, Codex, Cursor and Gemini hook formats were not checked (only the paste-in rules block exists for them).
- GitHub / GitLab / Bitbucket / Azure behaviour with custom refs (push, fetch, PR links, CI fetching `refs/logbook`).
- macOS and Linux beyond what the unit tests exercise in CI.
- Whether agents actually use injected notes in real work (the only number is the toy benchmark below), and how often the reminder to record a note is needed (see `docs/ROADMAP.md`, "Measure").
- `retention_days`, signed commits, GDPR-grade erasure, legal hold: not built.

## Next steps

The first design listed three steps; the first and third are done (real Claude Code sessions, golden fixtures, stack-specific meaning kept out of the tool). The second, a push to a real host with a
squash-merge PR and a CI fetch step, is still open. What comes next is in `docs/ROADMAP.md`; the design of statuses, tidy and the full summary tree is in `docs/TIDY-AND-SUMMARY-TREE.md`.

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

Rerun on the final 0.0.2 code, three rounds each: A used a median of 7 tool calls, 10 turns, 160,000 input tokens and $0.073; B used
1 tool call, 2 turns, 44,000 input tokens and $0.039; all six answers were correct. A moved between runs (5.5 tool calls earlier,
7 now), so compare the two arms within a run, not across them.

Read it as a smoke test: one author-written task and note, a toy repo, a handful of rounds, one model. B still reads about three times
because the note says to verify against the code. Real repos, real notes and teams are untested.

## Will the agent write the note itself? (smoke test)

`bench/run_ab.py --write-rate` runs the same bug question with no notes recorded and `Bash(logbook:*)` allowed, and counts runs in
which the agent ran `logbook note` without being asked. Four runs per setting, same toy repo:

| Setting | Wrote a note |
|---|---|
| Rules block and skill installed, no nudge | 0 of 4 |
| Stronger rules wording ("part of finishing a task") | 1 of 4 |
| Plus a once-per-turn block before finishing (`stop_hook_active` stops it looping) | 4 of 4 |

A rerun on the final code, with block as the default, again wrote a note in 4 of 4 runs.

(Later real-session runs did not reproduce this as a need for the block: Claude often wrote its own note before any reminder fired. Treat the table as a 2026 smoke test, not a rate; the benchmark that replaces it is `bench/real_session.py`.)

So instructions alone were not enough in that test, and the Stop-hook block is now the default (`logbook config nudge context|off` to soften or
disable). A sample note it produced named the cause, what was read, what was ruled out, and what it had not verified. Four runs on a
toy task say little about real work; the cost is one extra turn on turns that read or searched three or more times.

