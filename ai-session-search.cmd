@echo off
REM 더블클릭하면 대화 뷰어가 켜지고 브라우저가 열립니다. (Windows)
REM 기본 폴더: %USERPROFILE%\.claude\projects — 앱 안에서 다른 폴더로 전환/추가 가능.
REM 종료: 이 창을 닫거나 Ctrl-C.  포트 지정: ai-session-search.cmd 9000
setlocal
set PORT=%1
if "%PORT%"=="" set PORT=8777

REM 1) pip/pipx로 설치돼 있으면 콘솔 명령을 그대로 사용
where ai-session-search >nul 2>nul
if %errorlevel%==0 (
  ai-session-search --port=%PORT% --open
  goto :end
)

REM 2) 아니면 체크아웃의 shim을 python으로 실행 (python → py 순으로 시도)
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0ai-session-search.py" --port=%PORT% --open
  goto :end
)
where py >nul 2>nul
if %errorlevel%==0 (
  py "%~dp0ai-session-search.py" --port=%PORT% --open
  goto :end
)

echo.
echo Python 3.9+ 가 필요합니다. https://python.org 에서 설치한 뒤 다시 실행하세요.
echo 설치돼 있다면:  pip install ai-session-search  후  ai-session-search --open
pause

:end
endlocal
