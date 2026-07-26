"""Convenience entrypoint: `python main.py ...` == the `twikit-mcp` console script.

The packaged CLI is `twitter_mcp.server:main`. This shim exists only so that
running the repo checkout directly does the expected thing instead of printing
a leftover scaffold greeting.
"""

import sys

from twitter_mcp.server import main

if __name__ == "__main__":
    sys.exit(main())
