#!/bin/bash
# Build a lightweight "AI Session Search.app" (and optional .dmg) for macOS.
#
# This is the lightweight, NON-PyInstaller local build option. It does NOT bundle
# Python — it launches the pipx/pip-installed `ai-session-search` / `aiss` command
# (falling back to `python3 -m ai_session_search` from this checkout). The target
# machine just needs Python 3.10+, which any AI-coding machine already has. For the
# self-contained, signed+notarized bundle, use the GitHub `release` workflow instead.
#
#   ./scripts/make-macos-app.sh          -> build dist/AI Session Search.app
#   ./scripts/make-macos-app.sh --dmg    -> also build dist/ai-session-search.dmg
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
APP="dist/AI Session Search.app"

# Read the version straight from the package so it never goes stale.
VERSION="$(python3 -c "import sys;sys.path.insert(0,'src');import ai_session_search.app as a;print(a.__version__)")"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp assets/icon.icns "$APP/Contents/Resources/icon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>AI Session Search</string>
  <key>CFBundleDisplayName</key><string>AI Session Search</string>
  <key>CFBundleIdentifier</key><string>com.kimdongryeong.ai-session-search</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/launch" <<'LAUNCH'
#!/bin/bash
# Prefer an installed console script; fall back to running from the dev checkout.
PORT=8777
URL="http://127.0.0.1:$PORT"
# Already running? Just focus the browser and exit.
if curl -s -o /dev/null "$URL" 2>/dev/null; then open "$URL"; exit 0; fi
# Start the server detached and exit 0. Never exec into python here: /usr/bin/python3
# resolves to the Python.app binary inside Python3.framework, so exec swaps this
# process's bundle identity and LaunchServices reports the app "is not open anymore".
for CMD in ai-session-search aiss ass; do
  if command -v "$CMD" >/dev/null 2>&1; then
    nohup "$CMD" --open --port "$PORT" >/dev/null 2>&1 &
    exit 0
  fi
done
REPO="__REPO__"
if [ -d "$REPO/src/ai_session_search" ]; then
  nohup /usr/bin/env PYTHONPATH="$REPO/src" python3 -m ai_session_search --open --port "$PORT" >/dev/null 2>&1 &
  exit 0
fi
osascript -e 'display alert "AI Session Search" message "The ai-session-search command was not found.\nInstall it first:\n\npipx install ai-session-search"'
LAUNCH
# bake the checkout path in as a fallback
/usr/bin/sed -i '' "s#__REPO__#$REPO#" "$APP/Contents/MacOS/launch"
chmod +x "$APP/Contents/MacOS/launch"

# refresh icon cache
touch "$APP"
echo "built: $APP  (v$VERSION)"

if [ "${1:-}" = "--dmg" ]; then
  DMG="dist/ai-session-search.dmg"; rm -f "$DMG"
  STAGE="$(mktemp -d)"
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  hdiutil create -volname "AI Session Search" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
  rm -rf "$STAGE"
  echo "built: $DMG  (drag the app onto Applications)"
fi
