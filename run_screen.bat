@echo off
REM Nightly screener for Analytical Alpha. Scheduled via Windows Task Scheduler (23:00).
REM Runs the full universe and writes data\screen_results.json, logging to data\screen_log.txt.
cd /d "C:\Users\Dell\OneDrive\Desktop\Projects\03.Claude Code\AnalyticalAlpha2026"
echo. >> "data\screen_log.txt"
echo ===== run started %DATE% %TIME% ===== >> "data\screen_log.txt"
python run_screen.py 1>> "data\screen_log.txt" 2>&1
