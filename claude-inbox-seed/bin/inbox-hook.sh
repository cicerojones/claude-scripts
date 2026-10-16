#!/usr/bin/env bash
# Claude Code SessionStart hook: sync ~/claude-inbox and print open notes
# for the current project. Its stdout is added to the session's context.
#
# Usage: inbox-hook.sh [project-name]
#   project-name defaults to the basename of the git root of
#   $CLAUDE_PROJECT_DIR (or the current directory).
#
# Set CLAUDE_INBOX to use a clone somewhere other than ~/claude-inbox.
# Written for macOS's bash 3.2, so no mapfile or globstar.

INBOX="${CLAUDE_INBOX:-$HOME/claude-inbox}"
[ -d "$INBOX/.git" ] || exit 0

dir="${CLAUDE_PROJECT_DIR:-$PWD}"
project="${1:-$(basename "$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || echo "$dir")")}"

# Mobile/cloud sessions can only push to claude/* branches, so fold those
# into main here. Each note is its own file, so these merges don't conflict.
sync_inbox() {
  cd "$INBOX" || return 1
  git checkout --quiet main || return 1
  git fetch --quiet --prune origin || return 1
  git merge --quiet --ff-only origin/main 2>/dev/null \
    || git merge --quiet --no-edit origin/main || return 1

  merged=""
  for b in $(git for-each-ref --format='%(refname:short)' 'refs/remotes/origin/claude/*'); do
    if git merge --quiet --no-edit "$b"; then
      merged="$merged ${b#origin/}"
    else
      git merge --abort 2>/dev/null
    fi
  done

  # Delete the merged branches only after main is safely pushed.
  if [ -n "$merged" ] && git push --quiet origin main; then
    for b in $merged; do
      git push --quiet origin --delete "$b"
    done
  fi
}
sync_inbox >/dev/null 2>&1 || echo "(claude-inbox: sync failed; showing local copy)"

shopt -s nullglob
notes=("$INBOX/notes/$project"/*.org "$INBOX/notes/$project"/*.md "$INBOX/notes/all"/*.org "$INBOX/notes/all"/*.md)
[ ${#notes[@]} -eq 0 ] && exit 0

echo "## Inbox: ${#notes[@]} open note(s) for '$project' from $INBOX"
echo
for f in "${notes[@]}"; do
  echo "### ${f#$INBOX/}"
  cat "$f"
  echo
done
cat <<EOF
These notes were left from a mobile Claude Code session. At the start of this
session, briefly list them for the user and ask which to act on; don't act on
them unprompted. Once a note is handled, move it out of the inbox:
  cd $INBOX && mkdir -p done/$project && git mv <note> done/$project/ \\
    && git commit -m "Done: <note>" && git push
EOF
