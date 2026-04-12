@echo off
REM Fait par Gillesto
REM run_tests.bat — Lance les tests Python depuis la racine SafeRoute/
REM
REM Usage : scripts\run_tests.bat

echo ============================================
echo  SafeRoute — Tests Phase 1
echo ============================================
echo.

REM python -m pytest fonctionne meme si pytest n'est pas dans le PATH
python -m pytest tests/python/test_phase1.py -v --tb=short 2>&1

echo.
echo Pour lancer tous les tests :
echo   python -m pytest tests/python/ -v
pause
