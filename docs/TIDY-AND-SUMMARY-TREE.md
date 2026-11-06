# Keeping notes true: tidy, status and the full summary tree

Status: plan, agreed in conversation. Built so far: provenance labels, grounding checks on new notes, the walkable tree (`ask repo | branch: | commit: | note:`),
supersede for your own notes, a permission hook instead of allow rules, the `logbook-scribe` agent, `logbook tidy` (candidates with reasons), `tidy --brief`
(the notes' words for an agent to judge) and `tidy --apply` (statuses open / in-progress / resolved, stored as separate records by the note's author, checked
against git, one approval for the whole list). Not built: everything below the line "Not built".

How a status is stored: not by editing the note (a shared note is read first-copy-wins and publishing skips an id that is already shared). A status is an
ordinary note with an extra `status` field `{of: <note id>, state, commits}` and the reason in its summary; older versions show it as a plain note and ignore the
field. It counts only when its author is the author of the note it points at, the latest record wins, and `apply` stores it only when the commits it cites exist
and touched the note's tracked files after the note was written. Tracked files: a change note is about its commit's files; a finding about the files it names
(a finding is anchored to whatever HEAD was, which says nothing about its subject), or its commit's files when it names none.

## Who does what

| Job | Python (exact, free, same for every agent) | Claude (judgment, bounded, cached) |
|---|---|---|
| Does a file, name or commit a note mentions exist? | yes (`ground.check`) | no |
| Which notes track which files, and which later commits touched them? | yes (git) | no |
| Do two notes mean the same thing, or contradict? | finds candidates (same files, same area) | decides |
| Is this note now outdated, partly or fully? | lists notes whose files changed since, with the diffs | decides and writes the reason, citing the commit |
| Is the note true? | cannot | checks it against the code, once, and records what it ran |
| Apply a status, hide, delete | yes, after you approve | proposes |

Python hands Claude a brief (the same pattern as `summarize` and `backfill`); Claude answers in a fixed shape; Python checks the answer
(the commit it cites exists and touches the tracked files, the note is yours, the reason is not empty) before anything is stored.
A rule alone would be forgotten or argued with; Python alone cannot read meaning.

## Note ids

`<11 hex digits of the time in milliseconds>-<8 random hex digits>`: sortable by creation time, unique without coordination. A new note always
gets a fresh id, so an id already on the shared log can only be the same note again (a kept private copy). Skipping it never blocks a new note.

## `logbook tidy`

1. Python lists candidates, each with its reason and evidence: a note whose tracked files changed in a later commit; two notes on the same files
   that may be about the same thing; an old auto-copied draft; a change note that only restates its diff; a resolved note long past use.
2. Claude, in a separate agent, judges each candidate and proposes: keep, supersede (by which note), mark in-progress, mark resolved, fold into a
   summary and drop. Every proposal cites the commit or newer note that justifies it.
3. You see the proposals, with the old and new text side by side, and approve all, some or none. Nothing changes before that.
4. Python applies the approved ones. A superseded note records who superseded it (their name) and, if Claude did the work, `agent-written`.

Statuses: **open**; **in-progress** (later commits touched its files and changed the finding in part: shown with those commits, ranked lower);
**resolved** (truly fixed or gone: never injected, never cited); **superseded by** a newer note. Only the author's own notes are changed;
a teammate's note can be hidden for you by a status change from a trusted writer, with the same evidence, never deleted for them.

## Tracking files

A note with a commit tracks that commit's files. A note without one tracks the files it names, plus the files Claude read or edited since the last
note, plus paths mentioned in its text that exist. Stored on the note (`checks.files`) so `tidy` can ask git, for each note, what changed since.

## Approvals: only where it matters

Prompt for what leaves the machine or cannot be undone: `publish`, `sync`, applying a tidy, deleting. Never for reading, checking, or writing a
private note: `logbook setup` allows those commands in `.claude/settings.local.json`. Claude asks you in chat once, with the proposals, not once per note.

## A separate agent for the background work

Writing and reviewing notes costs the main conversation context and attention. A `logbook-scribe` subagent (its own context window, a cheaper
model, tools limited to Read, Grep, Glob and `logbook`) does the judging: the nudge hands a turn's findings to it, and `tidy` hands it the brief.
The main conversation gets a two-line result. Needs a guard so the scribe's own session does not trigger the hooks again.

## The full summary tree

Summaries at every level: repo, branch, area (a directory or topic), commit. Each lists the notes under it and is refreshed only when one of them
changes (the rule that exists today for the repo and branch levels). Injection descends: the repo summary, the branches that matter now, the
subtree for the files in play, and only then single notes. Ranking moves onto the tree; resolved and superseded notes drop out of it, and a note
folded into a summary by `tidy` stays reachable through `git show` and the archive.

## Not built

The scribe doing the tidy judging (today the main agent reads `tidy --brief`); a trusted writer's status hiding a teammate's note; recording who superseded a note
(name, and `agent-written` when Claude did it) beyond what `supersedes` already shows; summaries below the branch level and injection by descent; the
garbage-collection rules above (hide, fold into a summary, delete the owner's own notes after confirmation).
