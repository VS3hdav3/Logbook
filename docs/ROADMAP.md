# Roadmap

Logbook is a general tool for AI-assisted git repos: it keeps what the agent and the team learned (findings, the reasons behind changes) in git,
anchored to commits, so the next agent starts from it instead of rediscovering it. Not tied to data warehouses or dbt; anything warehouse-specific
belongs in the separate tool (Almanac, repo folder `lodestone`).

Read this first in a fresh session, then `CLAUDE.md` (how we work) and `docs/TIDY-AND-MEMTREE.md` (the design of what comes next).
Last updated 2026-11-04, at the release of 0.0.4.

## Where we are

On PyPI as `getlogbook`: 0.0.1, 0.0.2, 0.0.3, **0.0.4 (current)**. **0.0.2 and 0.0.3 have a security hole** (fixed in 0.0.4): a shared note's commit id went
into `git` arguments unchecked, and `--output=<path>` made `git show` overwrite a file on the reader's machine. They should be yanked on PyPI (the owner's click).

What 0.0.4 has: one shared shelf per person (`refs/logbook/log/<user>/000000`) merged on sync; `git push` only reminds and `logbook sync` pushes;
`publish` moves a note and skips an already-shared id; seven listed commands (`setup note publish sync ask log status`) with the older names hidden but working;
the walkable tree (`ask repo | branch:<x> | commit:<sha> | note:<id>`); numbered citations (`¹ ²`) with `logbook cites [--where N]`; four publish modes
(`logbook config publish never|ask|claude|auto`); honest provenance (`agent-written` only when Claude wrote it: Claude Code's session id is in the command's
environment; `LOGBOOK_WRITER=agent|user` overrides); grounding checks (`logbook note --check`, a finding that points at nothing is refused); notes as
`key: value` lines (`logbook note --fields`) because Claude Code refuses a shell command with `{"` in it; a note in plain words for people
(`logbook note "what you found" file...`); an optional Claude Code plugin in this repo (`.claude-plugin/`, `hooks/band/`): the bibliography band above the prompt
(publish-mode dot and selector, citations, peek-and-jump to the answer that cited a number).

## Done and verified (do not redo)

- Real-session test (`claude -p` in a clean clone with a planted bug): Claude found the true cause, fixed it, and saved a grounded `agent-written` note whose claims all checked out
  (n = 1). It also found two bugs the unit tests missed (below).
- 0.0.4 from real PyPI: 43 end-to-end checks pass (`bench/e2e.py <logbook executable>`).

## 0.0.5: built, in a stack of open PRs (#14 docs, then #15 to #19; merge in that order, each retargets to main)

All five of the owner's items are built and pass the suite (CI green on #15 to #18 when this was written). Not released: no version bump or tag yet.

1. **Evidence and 3 to 9 lines (#15).** An agent's finding or change note needs an `evidence:` line and 3 to 9 non-empty lines; a file or commit no longer counts as evidence;
   `--allow-ungrounded` bypasses only the evidence rule. A person's note and summary notes are exempt. Evidence is only checked to be non-empty.
2. **The commit's whole message (#16).** `ask commit:<sha>` and an injected note show subject and body read from git (injected: cleaned, capped at 400 characters); nothing is copied into the note.
3. **Nudge counts (#17).** Fixed: a checkpoint overwrote the turn's counts (now they add up, and the next prompt starts a new turn). `bench/real_session.py` runs real `claude -p` tasks.
   **Measured so far: one trivial and two debug runs.** The trivial run had no reminder and no note; both debug runs wrote a grounded agent-written note that names the cause, and no reminder
   fired because Claude wrote the note on its own. That is n = 1 each, not a result. Still to do with the owner: agree targets and N, run explain and refactor, run enough debug runs to say how often the reminder is needed at all.
4. **Permissions from a hook (#18).** One `PreToolUse` hook on Bash decides from the publish mode and the subcommand (table in `permissions.py` and the README, kept equal by a test); setup writes no allow rules and removes the 0.0.4 ones.
   Verified in real `claude -p`: a hook `allow` runs a command that is otherwise refused, `ask` and `deny` do not. **Not verified:** an interactive session skipping the prompt on `allow`; how a hook `allow` or `ask` interacts with the person's own allow and deny rules.
5. **`logbook-scribe` (#19).** A haiku subagent installed by setup; the nudge tells the agent to hand over the facts when it is installed; the permission hook confines it (the hook payload carries `agent_type`).
   Verified: prompt and stop hooks do not fire inside a subagent (so no recursion guard was needed), and given facts it wrote a grounded 6-line note for about 0.11 USD. **Not verified:** the nudge-to-scribe path end to end,
   the confinement in a real session (unit-tested only), and whether the scribe is cheaper or better than the main agent's own note (`bench/real_session.py --no-scribe` is there for that comparison; n = 1 each showed no difference).

Left for 0.0.5 before release: the measurements above, `claude plugin validate .` and `claude plugin test .` (the band is untouched but was not re-run), the version bump, an rc tag and `bench/e2e.py` against the build installed from TestPyPI (it was updated for the hook and the scribe and passes against a local build of the branch, but not yet against an uploaded one), then the release PR.

## Then: statuses, `logbook tidy`, file tracking (design in `docs/TIDY-AND-MEMTREE.md`)

- Every note tracks files (`checks.files` exists): a note with a commit tracks the commit's files; a note without one tracks the files it names, the files Claude read or edited since the last note
  and paths mentioned in its text that exist. A deterministic query lists notes whose tracked files changed in a later commit.
- Statuses: open, in-progress (later commits changed the finding in part: shown with those commits, ranked lower), resolved (fixed or gone: never injected, never cited), superseded-by.
  A resolved note is never used as context or cited. Weigh in-progress and resolved differently in ranking.
- `logbook tidy`: Python lists candidates with reasons; a Claude agent (the scribe) judges whether two notes mean the same thing or contradict, and whether a later commit outdates a note
  (word overlap is only a way to find candidates, not the judgment); proposals always cite the commit or newer note; **the user approves** before anything changes; a superseded note records
  who superseded it (name) and `agent-written` when Claude did the work. Only the author's own notes are changed; for a teammate's note, a status from a trusted writer with the same evidence hides it, never deletes it.
- Garbage collection through tidy: old auto-copied drafts (they hold the session's final message and wrong paths like `.claude/` and `CLAUDE.md`), change notes that only restate the diff,
  resolved notes long past use, orphaned notes whose files are gone. Hide first; delete only the owner's own notes, after confirmation; fold into a summary before dropping.
- Approvals are asked once, in chat, with the whole list; never per note.

## Then: the full summary tree

Summaries at repo, branch, area (directory or topic) and commit; each lists its notes and is refreshed only when one of them changes (the rule that already exists for repo and branch);
injection descends the tree instead of ranking flat notes; ranking moves onto the tree; tidy folds old leaves into their parent summary. The owner wants this complete, since it makes
superseding and tidy simpler to plan. Write the design in `docs/TIDY-AND-MEMTREE.md` into code in the order: area summaries, injection by descent, ranking, then GC folding.

## Verification debt (nothing here is tested yet)

A real GitHub or GitLab remote (custom ref push/fetch, the PR links, CI fetching `refs/logbook`); a big repo (the owner wants to test there); agents other than Claude Code (Codex etc.:
only the paste-in rules path exists, they need `LOGBOOK_WRITER=agent`); macOS and Linux outside CI; the plugin installed from the marketplace (`/plugin install logbook --marketplace vssehdave/Logbook`),
not the in-session dev copy; the band at narrow widths, click-to-open of the commit header on the owner's OS, and jump-to-answer for a very old message; whether notes change what a fresh agent does
(2 or 3 teammates for a couple of weeks; the only number so far is a toy benchmark: median tool calls about 7 down to 1).

## Housekeeping

Yank 0.0.3 and 0.0.2 on PyPI (owner). Delete stale branches (local `viewer-v2-merge-cards`, remote `chore/release-0.0.4rc3`; keep `viewer`, which holds the removed browser viewer). Refresh `docs/DESIGN.md`
(it still describes per-device refs and an unverified Claude hook). One commit message in history has a stray `¹` (it cannot be fixed without a force-push, which is blocked). Almanac (folder `lodestone`) is untouched and separate.

## Decided (do not reopen without a reason)

- The viewer (browser) is removed from `main`, kept on the `viewer` branch; the terminal (`log`, `ask`) and the band are the surfaces.
- One shelf per person, merged on sync (union of trees; a purge's tombstone wins and makes a parentless commit pushed with a lease). The ref path keeps a fixed hex part so 0.0.2 readers still match.
- `git push` never sends notes; `logbook sync` is the only command that does. `publish` moves the note (private copy removed unless `--keep`).
- Publish modes: never (refuses), ask (a redacted preview each time; default), claude (the agent may publish what it judges worth sharing), auto (every note as written, redacted; refused notes stay private).
  Pushing is always a separate `sync`. A repo policy turning publishing off wins over any mode. Redaction is a lint and can miss secrets.
- Note ids are `<11 hex digits of ms time>-<8 random hex digits>`: sortable, unique, never reused; skipping an already-shared id only happens when re-publishing the same note.
- "agent-written" only when Claude wrote the note; old notes show `origin unknown`. A person's own note needs no why and no evidence; an agent's does.
- Judgment (same meaning? outdated?) is Claude's, bounded and cached, then validated by Python; exact questions (does it exist, what changed) are Python.
- Citations are bare superscripts (`¹`), numbered per chat in injection order and not renumbered.
- No reference tools are named in repo text, commits or comments.

## How we work, and the traps (also in CLAUDE.md)

Tests must run with `CLAUDE_CODE_SESSION_ID` unset, as CI does (`env -u CLAUDE_CODE_SESSION_ID python -m unittest discover -s tests`); in a Claude Code shell it is set, and notes then
count as agent-written, which hid two CI failures. The full suite takes about 2.5 minutes: run it in the background. Do not write code through a bash heredoc: backslash sequences are mangled and a nested `EOF` ends it;
use the Edit/Write tools or a script file. `gh pr merge`, force-pushes and release tags need the owner's explicit permission and the auto-mode classifier can block compound commands: issue them one at a time.
GitHub sometimes answers a push with an Internal Server Error: retry. A new PyPI version can take a minute or two to be installable. The band is verified with `claude plugin validate .` and `claude plugin test .`
(that validator does not catch what the engine refuses at run time: a text field with no submit handler broke the whole band; a state write while drawing is refused).
