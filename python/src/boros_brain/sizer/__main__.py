"""Enables ``python -m boros_brain.sizer``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
