#!/bin/bash
# 더블클릭하면 대화 뷰어가 켜지고 브라우저가 열립니다. (macOS)
# 기본 폴더: ~/.claude/projects — 앱 안에서 다른 폴더로 전환/추가 가능.
# 종료: 이 터미널 창을 닫거나 Ctrl-C.
cd "$(dirname "$0")"
PORT="${1:-8777}"
URL="http://127.0.0.1:$PORT"

if curl -s -o /dev/null "$URL" 2>/dev/null; then
  echo "이미 실행 중입니다 → $URL"
  open "$URL"; exit 0
fi

exec python3 "$(dirname "$0")/claude-viewer.py" --port="$PORT" --open
