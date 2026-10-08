@echo off
setlocal
chcp 65001 >nul
cd /d %~dp0
conda run --no-capture-output -n agentdev python scripts\eval_security.py
if errorlevel 1 (echo SECURITY EVAL FAILED. & pause & exit /b 1)
echo SECURITY EVAL PASSED. Report: reports\security_eval.json
pause
