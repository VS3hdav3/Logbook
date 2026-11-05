# Rescope: a branch-scoped memory with savepoints

Status: design, agreed with the owner on 2026-11-05 (the decisions below are theirs; the mapping to the reference tool and the open items at the end are mine). It replaces the
"a note for every commit" goal, which the owner withdrew: "it should be the opposite or not even that".

## The idea

A memory in the style of that tool, scoped per **branch** (and commits) instead of per project. A background observer collects what happens in a session into a **running log**
for the branch you are on. `logbook log` is a **savepoint**: it summarizes the running log since the last savepoint and stores it, with the branch (and a commit if there is one),
in the **private** logbook. A stored log is shared with `logbook publish`. A note always has a branch; a commit is optional.

## How the reference memory tool works (read from its installed code and database on 2026-11-05)

- **Capture is a queue, with no model call.** A `PostToolUse` hook (and `PostToolUseFailure`) on every tool pushes the tool name, input, output and working directory into a
  `pending_messages` queue in SQLite. A `UserPromptSubmit` hook starts the session record. `Stop` asks for a summary; `SessionEnd` closes the session.
- **An observer reads the queue in batches** (`OBSERVATION_BATCH_SIZE`, default 1, up to 32; at most 2 agents at once; 4,096 output tokens; 400,000 characters of conversation). It is a silent,
  tool-less Claude whose prompt says: record what was learned, built, fixed or configured, not what you are doing; skip routine operations; never record the same fact twice.
  It sees its own earlier answers in one long conversation, which is how it avoids repeats.
- **An observation** is XML: `type` (bugfix, feature, refactor, change, discovery, decision, and security_alert / security_note / sensitive), `title`, `subtitle`, `facts[]`, `narrative`,
  `concepts[]` (how-it-works, why-it-exists, what-changed, problem-solution, gotcha, pattern, trade-off), `files_read[]`, `files_modified[]`. Noise is answered with `<skip_summary reason="noise" />`.
- **A summary checkpoint** is another XML answer from the observer: `request`, `investigated`, `learned`, `completed`, `next_steps`, `notes`. It is stored in `session_summaries`.
- **Storage** is SQLite (`observations`, `session_summaries`, `user_prompts`, a content hash for dedup) plus a vector index; **retrieval** is an injected recent-context block at session start, a hook that shows
  observations for files being read, and search / timeline / get-observations tools. Everything is keyed by *project*.
- **Cost handling:** `haiku`, your subscription (no key), the caps above, dedup, and a recorded `quota_exhausted` state.

## Where Logbook deliberately differs

- **Branch and commit scope.** Every record carries the branch it was made on; savepoints may carry commits. This is the point of the rewrite.
- **Git is the store, not SQLite.** Private records live under `.git/logbook/`, shared ones on `refs/logbook/...`, so they travel with a clone and need no service. No daemon: a detached process per batch.
- **Stateless observer calls.** Measured on 6 identical events with `haiku`: stateless with the last observations pasted in as "already recorded" cost 0.0052 USD and stayed flat (about 0.0009 per call);
  a persistent `--resume` conversation cost 0.0121 USD and rose with every call (0.0010 to 0.0031) as the history grew. The XML shape, the skip rule and the batching follow the reference tool; the prompt text is written fresh for Logbook, not copied.
- **A headless call is cheap only with the right flags:** `--model haiku --strict-mcp-config --disable-slash-commands --setting-sources ""` from an empty directory, 0.0006 USD fixed instead of 0.032 (`--bare` fails with a subscription login).

## Data

- **Observation (a note).** The reference tool's fields, plus: `id` (time-sortable), `branch` (**required**), `head` (HEAD when it was observed, informational), `commit` (optional: set at a savepoint when a commit in range
  touched the files it modified), `session`, `prompt_number`, `created`. Stored as an ordinary entry with an optional `obs` object (older versions ignore the field and show a plain finding: title, narrative).
- **Running log.** Per branch, append-only, private, never shared: `.git/logbook/running/<branch>.jsonl`, fed by `.git/logbook/queue/`. A branch with no running log forks from the parent branch's
  (main's) at first use; after that they diverge.
- **Stored log (a savepoint).** An entry written by `logbook log`: the summary fields (`request`, `investigated`, `learned`, `completed`, `next_steps`, `notes`), the ids of the observations it covers,
  the branch, and the commits in range (possibly none). After a savepoint the running log starts again from the savepoint.
- **Modes:** `manual`, `ask`, `auto` (one setting, replacing never / ask / claude / auto). A repo policy that turns sharing off still wins.

## Flows

| | manual | ask | auto |
|---|---|---|---|
| collect into the running log | always (a kill switch `worker off` exists) | same | same |
| savepoint (`logbook log`) | you run it | after a commit or at session end the main model asks, then runs it | by itself (proposed: after a commit with enough new observations, and at session end) |
| publish stored logs | `logbook publish` | the main model asks, shows the redacted preview, then runs it | when a branch you worked on is merged, the main model publishes that branch's logs |
| bring shared logs in | `logbook sync`, and on `git pull` in every mode | same | same |

- **Publish moves records, not text:** each record has its id and branch, so publishing a branch's stored logs is a plain move. Redaction, the size limits and the repo policy run first; a record that fails stays private.
- **"The branch was merged"** is detected on `git pull` (the post-merge hook) from a merge commit's subject; a squash merge has no ancestry, so the agent with the **GitHub MCP** resolves it (PR number to head branch to merged).
  The main model, not the observer, runs `logbook publish`.
- **`git pull` runs a pull-only sync** (post-merge and post-rewrite hooks): fetch shared refs and merge them into the view. It never pushes.
- **`logbook tidy`** first runs that same sync, then reconciles the private logs: dedupe observations, drop stale ones, merge stored logs, apply statuses. It has its **own background worker** on a separate cheap model
  setting (`tidy_model`). Approval rules stay: nothing leaves the machine or is deleted without a yes; archive instead of delete.
- **GitHub MCP:** used in the dev workflow in place of `gh`, and registered by the plugin so the agent can read PR, issue and merge state when it saves a log or publishes. It needs a token the owner adds; the repo never stores one.

## Removed

The per-commit machinery: `backfill`, the "N of M commits say why" count, `change` notes with `before_commit`, the "needs a note" check in `context`, the agent reminder (nudge) and the `logbook-scribe` agent.
`note` stays for "remember this". The existing view `logbook log` becomes the savepoint command; reading stays in `ask` and `status`.

## Phases (one PR each, merged in order)

1. Observer: the tool-use queue hooks, the batch observer with an observer prompt written for Logbook, the branch-scoped running log with forking, observation entries. (Replaces the per-turn worker of 0.0.5rc5.)
2. `logbook log`: the savepoint and stored logs; the three modes; auto savepoint.
3. Remove the per-commit machinery, the nudge and the scribe.
4. Publish by branch; publish on merge; pull-only sync on `git pull`; tidy-then-sync and the tidy worker.
5. Context injection from stored logs and the running log (like the reference tool's start-of-session block); the plugin's GitHub MCP registration.

## Open items (my defaults, say if wrong)

- When auto mode saves a log: after a commit that follows at least N new observations, and at session end.
- Who sees teammates' running logs: nobody. Only stored logs are ever published.
- After a branch merges: its stored logs stay filed under that branch; main's context reads them.
- Retention of a running log: it is replaced by the savepoint summary and the covered observations are archived, not deleted.
- Quota: the same caps and pause as 0.0.5rc5's worker; this design has not measured a day of real use.
