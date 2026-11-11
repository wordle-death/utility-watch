#!/usr/bin/env bash
# Commit anything new under data/ and push it to main. Usage: commit_data.sh "<label>"
set -u
git config user.name "utility-watch-bot"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add data
if git diff --cached --quiet; then
  echo "No changes."
  exit 0
fi
git commit -q -m "data: $1 $(date -u +%Y-%m-%dT%H:%MZ)"
for attempt in 1 2 3; do
  if git pull --rebase --quiet origin main && git push --quiet; then exit 0; fi
  git rebase --abort 2>/dev/null || true
  sleep 5
done
echo "Push failed after 3 attempts."
exit 1
