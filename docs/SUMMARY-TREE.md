# The summary tree

A repo's history is a very long conversation. An agent should not read all of it. It should read the top, see where things are, and go
down only as far as the question needs. Logbook gives it a tree to walk, with summaries on the upper levels and the original text
(the commit, the note, `git show`) one step below.

## The nodes

| Address | What it is | Where its text comes from |
|---|---|---|
| `repo` | the whole repo | a repo summary, written by an agent, if there is one |
| `branch:<name>` | a line of work | a branch summary, written by an agent, if there is one; notes written before the branch had a commit hang here |
| `commit:<sha>` | one commit on the main line, or one a merge brought in | its subject; the notes anchored to it. The original is `git show <sha>` |
| `note:<id>` | one note | the note itself |

`logbook ask <address>` opens a node: the path from the root, the summary if the node has one, and the nodes directly below it.
Each injected note names its node (`note:<id>`, `commit:<sha>`), so an agent can go down from any hit and up to the root.

## What is deterministic and what is not

- **The shape** comes from git and from where notes are anchored. Same history and notes give the same tree, with no model call.
- **The summaries** on `repo` and `branch` nodes are written by the user's own agent (`logbook summarize` briefs it) and saved as ordinary
  notes with `"kind": "summary"`. The engine never calls a model. A summary lists the notes it was built from; it is out of date as soon
  as a note under that node is added or removed, and an out-of-date summary is never injected.
- **Rewriting history costs nothing.** A summary depends on note ids, not commit ids. Rebase, amend or squash 100 commits and no summary
  goes stale and no token is spent; only the re-anchoring below runs, and that is plain git.

## Where a note belongs

Long research, a trail of dead ends, a summary of a whole piece of work: on the branch (`"level": "branch"`). A commit's own note stays
short, about what that commit changed and why. The branch holds the story and each commit holds its part.

## Notes with no commit

A note written before its branch has a commit stays on the `branch:` node. When the branch lands, it moves to the commit that
absorbed it. Each step is recorded on the note as the rung that matched, so a heuristic is never presented as fact:

| How the branch landed | Rung |
|---|---|
| merge commit named for the branch | `merged branch` |
| rebase | `patch-id` |
| squash, written at the branch tip | `squashed branch` (patch-id of the whole branch's diff) |
| squash with a PR number | `PR number` |
| squash, branch deleted, note written before any commit | `squash (same files, branch gone)`: the first single-parent, PR-numbered commit after the branch point that touches one of the note's files. A heuristic: it needs the note to name its files, and it waits until no local or remote-tracking branch of that name is left. |

## The reading view

`logbook log` is the cleaned version: commits that are drafts (`wip`, `fixup!`, `squash!`) or need no note (chore, style, docs,
whitespace or rename only) are folded out unless asked for with `-v`. Git itself is never changed and nothing is deleted; the notes
keep what happened, and the view shows what a reader wants.

## Not done, and not measured

- Nobody has measured whether agents descend the tree better than they search. The only evidence is the small benchmark in `bench/`.
- A person cannot yet mark a note as crossed out or highlighted in the log. A newer note can supersede an older one by the same author.
- Squashes where the note names no files, and branches still present as remote-tracking refs, stay on the branch node.
