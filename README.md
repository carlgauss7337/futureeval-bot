# Metaculus FutureEval bot (headless Claude Code)

One file, `bot.py`, Python 3.12, standard library only. About every 20 minutes GitHub Actions lists the open
questions of the FutureEval tournament and MiniBench, skips those this bot already forecast, researches the
rest with `claude -p` (web search and fetch only), posts the forecast and a reasoning comment. No LLM API key:
`claude` authenticates with your Claude subscription token. Fall 2026 FutureEval is id `33121`; change it
in `run.sh` each season.

## One-time setup (human steps)

1. Create the bot account and token at https://www.metaculus.com/futureeval/participate/ (the "Getting Started"
   part of the AI benchmark resources page explains it). This is your `METACULUS_TOKEN`.
2. On a machine with Claude Code logged in, run `claude setup-token` and copy the token it prints.
3. Push this folder to a public GitHub repo, then add two repository secrets (Settings, Secrets and variables,
   Actions): `METACULUS_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN`.
4. Create the `every-20-minutes` environment with its wait timer (one command, in the next section).
5. Enable Actions for the repo, then run the workflow once by hand with "selfcheck" ticked (Actions, Forecast...,
   Run workflow). It makes one small call to each model and fails if the Claude login does not work there. From
   then on every run starts the next one.
6. Fill in the participation form linked on the participate page before the bot submits forecasts.

## Every 20 minutes, without GitHub's scheduler

Questions open at any hour and stay open for only three hours, so the bot has to run about every 20 minutes.
GitHub's `schedule` trigger does not do that. Measured on 2026-11-13 over 33 forks of Metaculus's bot template
that ask for at least one run an hour (most ask for 72 a day): one got 71 runs in 24 hours, most got 4 or fewer.
Runs started by hand or through the API start within seconds.

So every run starts the next one. Its last job, `next`, waits 20 minutes on the wait timer of the
`every-20-minutes` environment (no runner is used while it waits), then `next.sh` starts the workflow again.
A scheduled or manual run restarts the chain when it has stopped. Create the environment once:

```
gh api -X PUT repos/OWNER/REPO/environments/every-20-minutes -F wait_timer=20
```

- Without the wait timer there is no chain: `next.sh` starts nothing when its job began less than 15 minutes
  after the forecast ended, and the run shows red. So runs never follow each other without a pause.
- Only one chain survives: one run at a time (`concurrency`), and a run leaves the chain to any newer run.
- To stop it, run `gh workflow disable forecast.yml`: the waiting run finishes its wait and then ends the chain.
  To start it again, run `gh workflow enable forecast.yml` and then `gh workflow run forecast.yml`.
  Cancelling the waiting run also stops the chain.
- A stopped chain restarts only with the next scheduled or manual run, which can be hours away. Check the
  result with `bash run.sh --missed` (below).
- A manual run queues behind the waiting run for up to 20 minutes.
- Every run adds a record to the repository's deployments list, because the environment serves as the timer.

A scheduler of your own is a second trigger, for example cron:

```
17,37,57 * * * * METACULUS_TOKEN=... /path/to/run.sh >> /path/to/forecast.log 2>&1
```

Whichever side runs first posts; the other finds the forecast and skips the question. Check the result, not the
trigger: `bash run.sh --missed` lists the questions that closed in the last three days without a forecast from
this bot and exits 1 if there are any. A run that fails to list a tournament or to forecast a question also
exits 1, so it shows red in Actions.

## Run locally

```
python3 -m unittest test_bot -v                       # tests (those of next.sh need jq)
python3 bot.py bot-testing-area --dry-run --limit 1   # forecasts one question, prints, posts nothing
bash run.sh --selfcheck                               # one small call per model
bash run.sh --missed                                  # needs METACULUS_TOKEN; read only
```

Knobs (env): `FORECAST_RUNS` (3), `FORECAST_RESEARCH_MODEL` (sonnet), `FORECAST_FINAL_MODEL` (opus; `run.sh`
sets fable). Cost: one question = R research runs plus one final call, counted against your subscription's limits.

## Money and upkeep

- Pool: USD 50k per season, three seasons a year, paid to the top bots (Q4 2024: the top five took 82%). A reasoning
  comment on every forecast and the end-of-season survey are required for prizes; one prize-eligible bot per person.
- Fall 2026 (id 33121) takes forecasts until 2027-01-06 and closes on 2027-03-05 (dates from the API). Change the
  id in `run.sh` when Spring 2027 opens
  (about January).
- GitHub disables the workflow of a public repo after 60 days without a commit, which also ends the chain:
  push something monthly.
- MIT licence. The tournament asks makers to share their code; this repository is that.
- Checked against the live API on the bot testing area (all four question types post and are then skipped).

The child `claude` never sees `METACULUS_TOKEN`, runs with `--safe-mode` (no hooks, plugins, MCP, settings) and
only the web search and fetch tools. Its prompt tells it web content is untrusted data.
