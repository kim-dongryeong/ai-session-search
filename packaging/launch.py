"""Frozen-app entry point (PyInstaller).

A double-clicked .app/.exe/binary has no CLI args, so default to `--open`: start the
local server and open the browser. Extra args still pass through (e.g. a port).

On macOS the .app process must exit right away: LaunchServices keeps tracking the
process it launched, and a long-running faceless server can't answer app-activation,
so re-opening the app while it runs fails with error -600 ("is not open anymore").
So the .app relaunches itself detached (AISS_SERVER=1) to run the real server and
exits; app.main() then reuses an already-running server instead of starting twice.
"""
import os
import subprocess
import sys

from ai_session_search.app import main

def _in_mac_app_bundle():
    return sys.platform == "darwin" and "/Contents/MacOS/" in sys.executable

if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--open" not in argv:
        argv = ["--open", *argv]
    # Detach only for the bare double-click launch; with CLI args (--version,
    # --get, an explicit port...) stay in the foreground like a normal command.
    if _in_mac_app_bundle() and not sys.argv[1:] and os.environ.get("AISS_SERVER") != "1":
        env = dict(os.environ, AISS_SERVER="1")
        subprocess.Popen([sys.executable, *argv], env=env, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raise SystemExit(0)
    raise SystemExit(main(argv))
