#!/bin/bash
set -euo pipefail
cd "/Users/macbookair/boros"
export DOTENV_PRIVATE_KEY="$(security find-generic-password -s 'boros-bot-dotenvx-key' -a "$USER" -w)"
exec dotenvx run -- python/.venv/bin/python -m boros_brain.main --mode=live
