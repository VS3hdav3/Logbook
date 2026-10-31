# Logbook

Commit-anchored shared memory for AI-assisted repos. It records **why** code and warehouse models changed
(what was wrong, how wrong, the fix) next to the git history, so a teammate or an AI agent can pick up where the
last person left off. Works for any repo; dbt-style repos get layer awareness (`stg_`, `int_`, `fct_`, `dim_`).

- Python 3.10+, **standard library only**, git 2.31+. Windows, macOS, Linux. No server to host, no model calls (`backend none`).
- Two logs: a **private** one under `.git/logbook/` (never tracked), and a **shared** one on git refs
  (`refs/logbook/log/<user>/<device>`, one writer per ref, so no merge conflicts). Sharing is opt-in per entry.
- A live local viewer (`logbook serve`) shows the shared tree with your private entries overlaid.

## Try it (no credentials, about 30 seconds)

    pip install getlogbook   # from a clone: pip install .   (or: PYTHONPATH=src python -m getlogbook ...)
                             # the command is `logbook`; the package name is getlogbook because `logbook` on PyPI is taken
    logbook demo           # Alice, Bob and a hostile Mallory on a scratch repo; every claim is checked
    logbook demo --serve   # same, then open the viewer on Bob's clone

## Daily use

    logbook init                              # once per clone (git config user.email must be set)
    logbook install-hook                      # git floor: records your commits even without an agent
    logbook install --agent claude-code --write   # merges hooks into .claude/settings.local.json (dry run without --write)
    logbook note --kind finding --topic "late payments" --summary "revenue dip" --why "export stalled" --wrong "1 day under"
    logbook note --kind change --before-commit --summary "..." --why "..." --wrong "..." --fix "..."   # then commit as usual
    logbook publish <id>                      # preview + redaction, you confirm; evidence is opt-in
    logbook sync                              # fetch teammates' entries, push yours
    logbook query "refunds" | explain fct_revenue | path <rev> <rev>   # exit 0 found, 3 ambiguous, 4 no match
    logbook serve --open
    logbook doctor                            # setup + what is NOT captured

New teammate: clone, then `logbook join`. A plain `git clone`/`git fetch` does not download logbook refs.
CI: `git fetch --depth=1 origin '+refs/logbook/log/*:refs/logbook-remote/origin/log/*'` (opt in; off by default).

