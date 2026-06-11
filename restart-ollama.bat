@echo off
echo Ollama を停止中...
taskkill /IM ollama.exe /F >nul 2>&1
timeout /t 2 /nobreak >nul

echo OLLAMA_ORIGINS を設定中...
setx OLLAMA_ORIGINS "*" >nul 2>&1
set OLLAMA_ORIGINS=*

echo Ollama を再起動中...
start "" "C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe"

echo.
echo 完了！Ollamaが再起動しました。
echo ブラウザでHTMLファイルを開き直して「生成」を試してください。
pause
