#!/bin/bash
set -euo pipefail
cd "$HOME/Documents/project/test/rerun7/boros"
export DOTENV_PRIVATE_KEY_PRODUCTION="$(security find-generic-password -s 'boros-bot-dotenvx-key' -a "$USER" -w)"
exec dotenvx run -- pnpm -C ts start:hands
