"""Allow ``python -m boros_brain.screener`` invocation."""

import sys

from .cli import main

sys.exit(main())
