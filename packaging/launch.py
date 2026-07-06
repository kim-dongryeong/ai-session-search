"""Frozen-app entry point (PyInstaller).

A double-clicked .app/.exe/binary has no CLI args, so default to `--open`: start the
local server and open the browser. Extra args still pass through (e.g. a port).
"""
import sys

from ai_session_search.app import main

if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--open" not in argv:
        argv = ["--open", *argv]
    raise SystemExit(main(argv))
