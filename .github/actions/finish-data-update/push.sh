#!/usr/bin/env bash
# Commit the paths this job owns and push them to the default branch, without ever overwriting another job's work.
#
#   bash push.sh "<commit message>" <branch> <path>...
#
# Writes deploy=true|false to $GITHUB_OUTPUT (true when site data, not just the status files, was pushed).
# When the push is refused because another job (or the owner) pushed first, the commit is rebased on the new tip:
#   - the status files (data/_status/updates.json, log.jsonl) are merged entry by entry and line by line
#     (pipeline/common/status.py merge-driver, declared in .gitattributes), so no status entry is ever lost;
#   - the digest built from them (data/_status/changes.json, web/public/changes.atom) is taken from the new tip and
#     rebuilt on top of it with pipeline/common/changes.py;
#   - any other conflict stops: the rebase is aborted, nothing is forced, and the next run does the update again.
# Exits 0 in every case (the job must stay green); a push that did not happen is a warning in the run log.
set -u
msg=$1
branch=$2
shift 2
out=${GITHUB_OUTPUT:-/dev/null}
pause=${PUSH_RETRY_PAUSE:-5}
py=${PYTHON:-python}
echo "deploy=false" >> "$out"

git config merge.status-union.name "union of the data update status files"
git config merge.status-union.driver "$py pipeline/common/status.py merge-driver %O %A %B %P"

paths=()
for p in "$@"; do
  if [ -e "$p" ] || git ls-files --error-unmatch -- "$p" > /dev/null 2>&1; then paths+=("$p"); fi
done
[ ${#paths[@]} -gt 0 ] && git add -A -- "${paths[@]}"
if git diff --cached --quiet; then
  echo "Nothing changed."
  exit 0
fi
deploy=false
if git diff --cached --name-only | grep -qv '^data/_status/'; then deploy=true; fi
git commit -q -m "$msg"

tmp=$(mktemp -d)
# Settle the conflicts of a stopped rebase that this job can rebuild; return 1 on any other conflict.
settle() {
  local rerun=false f
  for f in $(git diff --name-only --diff-filter=U); do
    case "$f" in
      data/_status/updates.json | data/_status/log.jsonl)
        # only reached where the merge driver is not configured: the same union by hand
        git show ":2:$f" > "$tmp/ours" 2> /dev/null || : > "$tmp/ours"
        git show ":3:$f" > "$tmp/theirs" 2> /dev/null || : > "$tmp/theirs"
        "$py" pipeline/common/status.py merge-driver /dev/null "$tmp/ours" "$tmp/theirs" "$f" || return 1
        cp "$tmp/ours" "$f"
        ;;
      data/_status/changes.json | web/public/changes.atom)
        # in a rebase "ours" is the tip being rebased onto: keep it and rebuild the digest on top of it
        git checkout --ours -- "$f" || return 1
        rerun=true
        ;;
      *)
        echo "Conflict in $f with a newer commit: not settled automatically."
        return 1
        ;;
    esac
    git add -- "$f"
  done
  if [ "$rerun" = true ]; then
    "$py" pipeline/common/changes.py || true
    git add -A -- data/_status web/public/changes.atom
  fi
  GIT_EDITOR=true git rebase --continue > /dev/null
}

rebase_on_tip() {
  git fetch -q origin "$branch" || return 1
  # --autostash: files outside the owned paths that the job left modified do not block the rebase
  git rebase -q --autostash FETCH_HEAD && return 0
  local n=0
  while [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; do
    n=$((n + 1))
    if [ $n -gt 5 ] || ! settle; then
      git rebase --abort 2> /dev/null || true
      return 1
    fi
  done
  return 0
}

pushed=false
for attempt in 1 2 3 4 5; do
  if git push -q origin "HEAD:${branch}"; then
    pushed=true
    break
  fi
  echo "Push refused (attempt $attempt): rebasing on the latest ${branch}."
  sleep $((attempt * pause))
  if ! rebase_on_tip; then
    echo "::warning::The data update conflicts with a newer commit on ${branch} outside the status files; nothing was forced. The next run does the update again."
    break
  fi
done
rm -rf "$tmp"
if [ "$pushed" = true ]; then
  echo "deploy=$deploy" >> "$out"
else
  echo "::warning::The data update was not pushed; it will be redone at the next run."
fi
exit 0
