#!/usr/bin/env python3
"""Compatibility shim — runs the package from a plain checkout.

`python3 ~/dev/claude-viewer/claude-viewer.py [args]` keeps working exactly like
the old single-file script; the real code lives in src/claude_viewer/app.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from claude_viewer.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
