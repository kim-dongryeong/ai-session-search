#!/bin/bash
# 더블클릭하면 대화 뷰어가 켜지고 브라우저가 열립니다.
# 앱 안에서 ~/.claude/projects 와 ~/Downloads/.claude/projects 를 전환할 수 있습니다.
# 종료: 이 터미널 창을 닫거나 Ctrl-C.
cd "$(dirname "$0")"
PORT="${1:-8777}"
URL="http://127.0.0.1:$PORT"

if curl -s -o /dev/null "$URL" 2>/dev/null; then
  echo "이미 실행 중입니다 → $URL"
  open "$URL"; exit 0
fi

echo "Claude 대화 뷰어를 시작합니다 → $URL"
echo "(이 창을 닫으면 종료됩니다)"
( sleep 1.2; open "$URL" ) &
exec python3 "$(dirname "$0")/claude-viewer.py" --port="$PORT"
