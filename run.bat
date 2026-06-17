@echo off
echo ========================================
echo   QuizLive - Demarrage du serveur
echo ========================================
echo.

cd /d "%~dp0"

echo Installation des dependances...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERREUR : pip install echoue. Verifiez votre installation Python.
    pause
    exit /b 1
)

echo.
echo Demarrage du serveur sur http://localhost:5000
echo.
echo  Professeur : http://localhost:5000/prof
echo  Etudiants  : http://localhost:5000/student
echo.
echo Appuyez sur Ctrl+C pour arreter.
echo.

cd backend
python app.py
pause
