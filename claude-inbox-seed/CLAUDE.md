# claude-inbox

This repo is a mailbox between mobile Claude Code sessions and desktop projects.
If you're in a mobile or cloud session and the user asks you to leave a note for
a project, file it here.

## Filing a note

- One note per file: `notes/<project>/<YYYY-MM-DD-HHMM>-<slug>.org`
  - `<project>` is the project repo's directory name, e.g. `claude-scripts`.
  - Use `notes/all/` for notes meant for every project.
  - Never edit or append to someone else's note file. Separate files keep
    merges conflict-free.
- Format:

  ```org
  #+title: Short imperative summary
  #+date: 2026-10-06 22:40
  #+source: <session link, if any>

  * TODO The thing to do
  Context, links, snippets. Enough for a fresh session with no memory of
  this conversation to act on it.
  ```

- Commit and push. A cloud session may only be allowed to push to its
  `claude/*` branch, and that's fine: the desktop hook merges `claude/*`
  branches into `main` and then deletes them.

## Desktop side

`bin/inbox-hook.sh` runs as a Claude Code SessionStart hook. It pulls this
repo, merges any `claude/*` branches, and prints the open notes for the current
project. Once a note is handled, `git mv` it to `done/<project>/`, then commit
and push.
