#!/usr/bin/env bash
# Starts the next run of the forecast workflow, so the bot runs about every 20 minutes without GitHub's scheduler
# (which starts only a few scheduled runs a day in most repositories, see the README). The job that calls this
# first waits 20 minutes on the wait timer of the "every-20-minutes" environment; no runner is used while it waits.
# A scheduled or manual run restarts the chain when it has stopped. Needs GH_TOKEN with the actions:write permission.
set -u
wf=forecast.yml
api() { gh api "repos/$GITHUB_REPOSITORY/actions/$1" --jq "$2"; }

# 0: done, whether a run was started or deliberately not; 1: GitHub could not be read or the run did not start
next() {
  local ended waited state newer
  # the pause is the time since the last finished job of this run, the forecast, ended
  ended=$(api "runs/$GITHUB_RUN_ID/jobs" '[.jobs[] | select(.status == "completed") | .completed_at] | max') || return 1
  # a strict check, because `date -d ""` is today's midnight and would pass for a long pause
  [[ $ended =~ ^20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9:]+Z$ ]] || return 1
  waited=$(($(date +%s) - $(date -d "$ended" +%s)))
  if [ "$waited" -lt 900 ]; then
    # without the wait timer the runs would follow each other without a pause: stop, and show red
    echo "::error::This job started $waited seconds after the forecast ended. Give the 'every-20-minutes' environment a 20-minute wait timer (see the README). No new run was started."
    exit 1
  fi
  state=$(api "workflows/$wf" .state) && [ -n "$state" ] || return 1
  if [ "$state" != active ]; then
    [ "$state" = disabled_manually ] || echo "::warning::GitHub set this workflow to $state. Enable it again and start a run by hand."
    echo "The workflow is $state: the chain ends here."
    return 0
  fi
  # the newest unfinished run carries the chain, so a scheduled or manual run in between does not start a second one
  newer=$(api "workflows/$wf/runs?per_page=30" "[.workflow_runs[] | select(.status != \"completed\" and .id > $GITHUB_RUN_ID)] | length") || return 1
  [[ $newer =~ ^[0-9]+$ ]] || return 1
  if [ "$newer" -gt 0 ]; then
    echo "A newer run carries the chain."
    return 0
  fi
  # always on the default branch, so a manual run on another branch hands the chain back
  gh workflow run "$wf" --repo "$GITHUB_REPOSITORY" --ref "${DEFAULT_BRANCH:-$GITHUB_REF_NAME}"
}

for _ in 1 2 3 4 5; do
  next && exit 0
  sleep "${RETRY_WAIT:-30}"
done
echo "::error::Could not start the next run. The chain restarts with the next scheduled or manual run."
exit 1
