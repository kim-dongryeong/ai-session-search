#!/bin/bash
# Build a lightweight "Claude Viewer.app" (and optional .dmg) for macOS.
#
# It does NOT bundle Python — it launches the pipx/pip-installed `claude-viewer`
# (falling back to `python3 -m claude_viewer` from this checkout). The target
# machine just needs Python 3.10+, which any Claude Code machine already has.
#
#   ./scripts/make-macos-app.sh          → build dist/Claude Viewer.app
#   ./scripts/make-macos-app.sh --dmg    → also build dist/claude-viewer.dmg
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
APP="dist/Claude Viewer.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp assets/icon.icns "$APP/Contents/Resources/icon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Claude Viewer</string>
  <key>CFBundleDisplayName</key><string>Claude Viewer</string>
  <key>CFBundleIdentifier</key><string>com.kdr.claude-viewer</string>
  <key>CFBundleVersion</key><string>1.2.0</string>
  <key>CFBundleShortVersionString</key><string>1.2.0</string>
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
if curl -s -o /dev/null "$URL" 2>/dev/null; then open "$URL"; exit 0; fi
if command -v claude-viewer >/dev/null 2>&1; then
  ( sleep 1; open "$URL" ) & exec claude-viewer --port "$PORT"
fi
REPO="__REPO__"
if [ -f "$REPO/claude-viewer.py" ]; then
  ( sleep 1; open "$URL" ) & exec /usr/bin/env python3 "$REPO/claude-viewer.py" --port "$PORT"
fi
osascript -e 'display alert "Claude Viewer" message "claude-viewer 명령을 찾을 수 없습니다.\n먼저 설치하세요:\n\npipx install git+ssh://git@github.com/kim-dongryeong/claude-viewer.git"'
LAUNCH
# bake the checkout path in as a fallback
/usr/bin/sed -i '' "s#__REPO__#$REPO#" "$APP/Contents/MacOS/launch"
chmod +x "$APP/Contents/MacOS/launch"

# refresh icon cache
touch "$APP"
echo "built: $APP"

if [ "${1:-}" = "--dmg" ]; then
  DMG="dist/claude-viewer.dmg"; rm -f "$DMG"
  STAGE="$(mktemp -d)"
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  hdiutil create -volname "Claude Viewer" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
  rm -rf "$STAGE"
  echo "built: $DMG  (drag the app onto Applications)"
fi
