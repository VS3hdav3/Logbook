# Roadmap: 0.0.2

Logbook is a general tool for AI-assisted git repos. It is not tied to data warehouses or dbt; anything
warehouse-specific belongs in a separate tool that can annotate entries through tags.

Goal of 0.0.2: an agent writes real notes (findings with or without a commit, and a note per commit that
summarises the discussion behind it), and agents on the same repo read them first. Success is measured, not assumed:
fewer repeated file reads and fewer tokens on the same task with the notes than without.

## Decisions

| # | Question | Decision |
|---|---|---|
| D1 | What triggers a finding? | The agent decides, guided by the skill. A narrow nudge fires only after a turn with N or more read/search calls and no `logbook note`. Never after every tool call. |
| D2 | Nudge default? | On, context-only, never blocks. At most once per turn and three per session, with a config opt-out. `logbook stats` reports nudges, notes written and tokens injected so the default can be changed on data. |
| D3 | Where do summaries live? | Ordinary entries of kind `summary` with source hashes, so they sync, redact and trust like any entry. Treated as derived, untrusted text. A summary whose sources changed is stale and is never injected. |
| D4 | Sharing default? | Manual per note. A push-time queue with a redaction preview is a later addition. Never auto-share. |
| D5 | Do chores need a note? | No. Deterministic rules (about 20 lines) mark chore/style/docs commits and whitespace-, comment- or rename-only diffs as trivial. They count as covered and show as "trivial", not "missing". The agent and the user can override. |
| D6 | Order of work | Agent layer first, with a benchmark gate, then the rest. See milestones. |
| D7 | Field for "how much was wrong" | `scale`. |
| D8 | Naming | `inferred` becomes `auto-copied`; old files still load. |

## Milestones

Each milestone is one branch and one PR with CI, and publishes a release candidate to TestPyPI (`0.0.2rc1`, `rc2`, ...).

**M1: foundation (small)**
- Remove the dbt/warehouse coupling: layers, model names and `stg_`/`fct_` rules. Scopes become file path, directory and topic. Entries written by 0.0.1 that carry `models` or `layers` still load; those fields are ignored.
- Richer note fields: `context`, `decided`, `open`, `scale`, `scope`, `sources`. Longer `summary` (3 to 5 sentences).
- Record the branch name and merge-base when a note is written.
- `logbook note --commit <sha>` so a note can target an earlier commit.
- Rewrite the demo and tests for an ordinary repo, and write the demo notes at full quality.

**M2: the agent layer, and the proof**
- A compact skill and an always-on rules block that say when to record a finding, what a good note contains, and to consult the notes before searching code or answering questions about history.
- Hooks: a session-start digest that is an index, not full notes; prompt-time matching on free text and not only on known names; a path-scoped note before Read, Grep and Edit; the narrow nudge from D1 and D2.
- One-command `logbook install`: runs `init` if needed, installs the git hook, detects the agent, writes the skill, the rules block and the hooks. Dry run by default, backups of every file it edits, atomic writes with the skill written last, symlink-safe edits, interpreter path resolved once, `logbook uninstall` that mirrors it, and `doctor` showing install status. Claude Code first, then instruction-file installers for other hosts.
- A reproducible benchmark: the same task run with and without notes, counting tokens and repeated file reads.
- Gate: a real Claude Code session test (hook payloads, transcript format, whether the nudge can loop), saved as golden fixtures.

**M3: depends on M2 showing the notes pay off**
- Observations: many small findings per session, with `commit-context` listing the unlinked ones since the last commit, filtered by path overlap, for the agent to cite as `sources`.
- Commit tiers from D5.
- Viewer: "no reason recorded", coverage counts ("N of M commits have a reason", trivial commits excluded), branch nodes, richer note rendering, and a headless-browser regression script.
- Branch resolution after merge: merge commit, squash commit (PR number or branch name), rebased range (patch-id), else kept under the branch. Fix the case where an existing but off-line sha blocks the patch-id match.

**M4: stretch, go or no-go after the benchmark**
- Lazy summaries at branch and repo level.
- `logbook backfill <sha>` for commits with no session behind them.
- Push-time sharing queue.
If the benchmark shows no gain, M3 and M4 stop and move to 0.0.3.

## Risks and guards

- Notes are text from other people entering an agent's context. Keep sanitising, inject only from trusted writers, label every note "verify first" with age and distance from HEAD, and never inject stale summaries.
- The installer edits settings and rules files, which is the highest-trust action in the tool: dry run first, backups, reversible.
- A nudge can loop or cost more than it saves: once per turn, context only, counted in the benchmark.
- Wrong notes cost more than rediscovery: add supersede and expiry handling.
- Redaction is a lint, not a guarantee; published text can persist in forks and mirrors.
- Unverified: real Claude Code hook payloads, custom-ref behaviour on GitHub and GitLab, any host other than Claude Code.
