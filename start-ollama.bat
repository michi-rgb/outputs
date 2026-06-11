@echo off
echo OLLAMA_ORIGINS の確認...
echo 現在の値: %OLLAMA_ORIGINS%

echo.
echo OLLAMA_ORIGINS=* を設定中...
setx OLLAMA_ORIGINS "*" >nul 2>&1
set OLLAMA_ORIGINS=*

echo.
echo Ollama を起動します...
start "" ollama serve

echo.
echo 起動しました。このウィンドウは閉じても構いません。
echo ブラウザに戻って再度「生成」を試してください。
pause
