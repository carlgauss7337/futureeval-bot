# Metaculus FutureEval bot (headless Claude Code)

One file, `bot.py`, Python 3.12, standard library only. Every 20 minutes GitHub Actions lists the open
questions of the FutureEval tournament and MiniBench, skips those this bot already forecast, researches the
rest with `claude -p` (web search and fetch only), posts the forecast and a reasoning comment. No LLM API key:
`claude` authenticates with your Claude subscription token. Fall 2026 FutureEval is id `33121`; change it
in `.github/workflows/forecast.yml` each season.

## One-time setup (human steps)

1. Create the bot account and token at https://www.metaculus.com/futureeval/participate/ (the "Getting Started"
   part of the AI benchmark resources page explains it). This is your `METACULUS_TOKEN`.
2. On a machine with Claude Code logged in, run `claude setup-token` and copy the token it prints.
3. Push this folder to a public GitHub repo, then add two repository secrets (Settings, Secrets and variables,
   Actions): `METACULUS_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN`.
4. Enable Actions for the repo, then run the workflow once by hand (Actions, Forecast..., Run workflow).
5. Fill in the participation form linked on the participate page before the bot submits forecasts.

## Run locally

```
python3 -m unittest test_bot -v                       # tests
python3 bot.py bot-testing-area --dry-run --limit 1   # forecasts one question, prints, posts nothing
```

Knobs (env): `FORECAST_RUNS` (3), `FORECAST_RESEARCH_MODEL` (sonnet), `FORECAST_FINAL_MODEL` (opus; the workflow
sets fable). Cost: one question = R research runs plus one final call, counted against your subscription's limits.

## Money and upkeep

- Pool: USD 50k per season, three seasons a year, paid to the top bots (Q4 2024: the top five took 82%). A reasoning
  comment on every forecast and the end-of-season survey are required for prizes; one prize-eligible bot per person.
- Fall 2026 (id 33121) stops opening questions in mid-December. Change the id in the workflow when Spring 2027 opens
  (about January).
- GitHub switches off the schedule of a public repo after 60 days without a commit: push something monthly.
- MIT licence. The tournament asks makers to share their code; this repository is that.
- Checked against the live API on the bot testing area (all four question types post and are then skipped).

The child `claude` never sees `METACULUS_TOKEN`, runs with `--safe-mode` (no hooks, plugins, MCP, settings) and
only the web search and fetch tools. Its prompt tells it web content is untrusted data.
