@echo off
chcp 65001 > nul
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-Package.ps1"
set EXIT_CODE=%ERRORLEVEL%
echo.
if not "%EXIT_CODE%"=="0" (
  echo [실패] 패키지를 만들지 못했습니다. 위 오류 내용을 확인해 주세요.
) else (
  echo [완료] 창을 닫으려면 아무 키나 누르세요.
)
pause > nul
exit /b %EXIT_CODE%
