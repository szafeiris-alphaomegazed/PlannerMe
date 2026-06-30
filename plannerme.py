#!/usr/bin/env python3
"""Compatibility wrapper for running PlannerMe from a source checkout.

After installation, prefer:

    plannerme <command> [options]
"""

from plannerme.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
