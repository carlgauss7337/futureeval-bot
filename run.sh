#!/usr/bin/env bash
# One run on this season's tournaments. The scheduled job and any backup trigger call this, so the ids live in one place.
# Extra arguments go to bot.py: --selfcheck, --missed, --dry-run.
cd "$(dirname "$0")" || exit 1
# Prizes go to the top few bots; if this model is refused the bot falls back to the median of the research runs.
export FORECAST_FINAL_MODEL="${FORECAST_FINAL_MODEL:-fable}"
exec python3 -B bot.py 33121 minibench --limit 6 "$@"
