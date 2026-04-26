"""Enables ``python -m boros_brain.reward_model``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
