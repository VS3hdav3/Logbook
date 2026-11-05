# Roadmap

Logbook is a general tool for AI-assisted git repos: it keeps what the agent and the team learned (findings, the reasons behind changes) in git,
anchored to commits, so the next agent starts from it instead of rediscovering it. Not tied to data warehouses or dbt; anything warehouse-specific
belongs in the separate tool (Almanac, repo folder `lodestone`).

Read this first in a fresh session, then `CLAUDE.md` (how we work) and `docs/TIDY-AND-MEMTREE.md` (the design of what comes next).
Last updated 2026-11-04: 0.0.4 is on PyPI; 0.0.5rc1 is on TestPyPI (tag `v0.0.5rc1`, from `chore/release-0.0.5rc1`, which is `feat/note-status` plus the version bump).

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

## 0.0.5: built and merged to `main` (#14 to #21); statuses are PR #22 (open); `0.0.5rc1` is on TestPyPI

All five of the owner's items are built, merged and pass the suite. Not on PyPI: only `0.0.5rc1` on TestPyPI, installed in a clean venv, where `bench/e2e.py` passes (including the hook, the scribe and `tidy`) and `claude plugin validate .` and `claude plugin test .` pass.

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

Left before 0.0.5 can be released (the owner's calls are marked): review and merge PR #22 (statuses); cut `0.0.5rc2` from `main` once it is in; decide what the nudge numbers must be
(see "Measure" below); then the release PR, tag `v0.0.5` and the owner's click on the `pypi` environment. Yank 0.0.3 and 0.0.2 (owner).

## Statuses and `logbook tidy` (design in `docs/TIDY-AND-MEMTREE.md`): first half built, on `feat/note-status`

Built: `logbook tidy` lists candidates with reasons (files changed in later commits, notes that may repeat each other, old auto-copied drafts); `tidy --brief` is the brief for an agent;
`tidy --apply` stores approved statuses (open, in-progress, resolved) as separate records written by the note's author, validated against git (the commits cited exist and touched the
note's tracked files after it was written; a reason; all or nothing) and is the one tidy command the permission hook always asks about. Resolved is never injected or cited; in-progress is
shown with its commits and ranked lower. A record from another writer is ignored. Old versions show a record as an ordinary note.
Verified: unit tests and `bench/e2e.py`; in a real `claude -p` session the agent read the brief, proposed `resolved` and stopped to wait for the person's yes (the approval prompt itself cannot be seen under `-p`).
**Not verified:** the interactive approval prompt on `tidy --apply`; any run on a real repo with many notes (only fixtures); a record shared to a teammate and read by a version that predates it.

Not built: the scribe doing the tidy judging; a trusted writer's status hiding a teammate's note; recording who superseded a note by name beyond what `supersedes` shows; garbage collection through tidy
(hide, fold into a summary, delete the owner's own notes after confirmation); approvals asked once in chat is a skill instruction, not enforced beyond the permission prompt.

## Then: the full summary tree

Summaries at repo, branch, area (directory or topic) and commit; each lists its notes and is refreshed only when one of them changes (the rule that already exists for repo and branch);
injection descends the tree instead of ranking flat notes; ranking moves onto the tree; tidy folds old leaves into their parent summary. The owner wants this complete, since it makes
superseding and tidy simpler to plan. Write the design in `docs/TIDY-AND-MEMTREE.md` into code in the order: area summaries, injection by descent, ranking, then GC folding.

## Verification debt (nothing here is tested yet)

A real GitHub or GitLab remote (custom ref push/fetch, the PR links, CI fetching `refs/logbook`); a big repo (the owner wants to test there); agents other than Claude Code (Codex etc.:
only the paste-in rules path exists, they need `LOGBOOK_WRITER=agent`); macOS and Linux outside CI; the plugin installed from the marketplace (`/plugin install logbook --marketplace vssehdave/Logbook`),
not the in-session dev copy; the band at narrow widths, click-to-open of the commit header on the owner's OS, and jump-to-answer for a very old message; whether notes change what a fresh agent does
(2 or 3 teammates for a couple of weeks; the only number so far is a toy benchmark: median tool calls about 7 down to 1).

## Left to do besides the unbuilt items above

**Measure (nothing here has a real number yet)**
- The nudge, measured on 0.0.5rc2-era code with `bench/real_session.py` (real `claude -p`, one fresh fixture repo per run, n = 2 per task, so a first look and not a rate):
  trivial: no reminder, no note (2 of 2). Debug with a planted bug: Claude wrote its own grounded note with an evidence line that names the refund cause in 2 of 2 runs with the scribe installed and 2 of 2 without,
  and no reminder fired (it had already noted). Explain: the reminder fired in 2 of 2 and Claude chose not to write a note. Refactor: the reminder fired in 1 of 2, no note in either.
  The scribe was never used in these runs, so the hand-off path is still untested end to end. Cost per run: trivial 0.084 USD, explain 0.12, refactor 0.10 to 0.12, debug 0.155 with the scribe installed against
  0.140 without: **installing the scribe made unused debug runs about 10% dearer** (its description sits in every session's context). Targets are still not agreed with the owner; against the two stated here (every
  root-cause run ends with a grounded note; no prompt on trivial turns) the numbers hold at n = 2. Still open: a larger N, tasks where Claude does not note on its own, and whether to keep the scribe installed by default given its cost.
- Whether the evidence rule produces better notes or just longer ones: it only checks that `evidence:` is non-empty and that a note has 3 to 9 lines; read real notes.
- Whether notes change what a fresh agent does (2 or 3 teammates, a couple of weeks).

**Verify (done only in `claude -p` or on fixtures)**
- Interactive Claude Code: a hook `allow` skipping the prompt, `ask` showing it (and `tidy --apply` as the approval step), and how the hook's answers interact with the person's own allow and deny rules.
- The scribe's Bash confinement in a real session (unit-tested only; the scribe declined to try), and the nudge-to-scribe path.
- The permission hook next to other PreToolUse hooks that rewrite a command (the owner's own setup rewrites some commands before they run).
- A status record shared to a teammate who runs an older version; `tidy` on a real repo with many notes (cost: one `git log` per note, newest 200).
- Windows: a command line with backslashes (`C:\path\logbook.exe note ...`) gets no opinion from the hook, so it prompts as usual; a bare `logbook` is what an agent normally runs.

**Product gaps found while building**
- (Fixed in rc2: a status record no longer appears as its own note in `log`; the note it is about shows `[resolved]` or `[in-progress]` and a `status:` line in `ask note:<id>`.)
- `tidy` is hidden from `logbook -h` (the listed seven are `setup note publish sync ask log status`): decide whether it is an eighth listed command once statuses are in use.
- The 3 to 9 line rule counts lines of fields, not sentences. (Fixed in rc2: for a decision the user made, the skill now says the evidence is what they said or chose, quoted briefly; `--allow-ungrounded` stays for the truly evidence-less case.)
- A status record shows in `ask`/`log` as its own note ("resolved: ..."); hide records from the tree if that clutters.
- The permission hook is conservative: a quoted argument containing `;`, `(`, `$` or a backslash gets no opinion (a prompt), even when harmless.
- Line endings: the repo mixes CRLF and LF (Git warns on commit); a `.gitattributes` would stop that.
- The CHANGELOG has an `Unreleased` section; rename it to `0.0.5` at release.

## Housekeeping

Yank 0.0.3 and 0.0.2 on PyPI (owner). Delete merged branches, local and remote (the feature branches of 0.0.3 to 0.0.5, `chore/release-0.0.3`, `chore/release-0.0.4`, `chore/release-0.0.4rc3`, `chore/release-setup`, `release/0.0.1`,
`viewer-v2-merge-cards`, `docs/*`; keep `viewer`, which holds the removed browser viewer, and keep release tags). (`docs/DESIGN.md` was refreshed in rc2: status, not-verified and next-steps sections; the rest stays as the record of the first design.)
One commit message in history has a stray `¹` (it cannot be fixed without a force-push, which is blocked). Almanac (folder `lodestone`) is untouched and separate.

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
