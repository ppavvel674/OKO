@echo off
chcp 65001 >nul
rem Проверка всего проекта одной кнопкой: окружение, автотесты, набор с ВУ,
rem распознавание, база и поиск. Ничего не меняет в папке data\ и в результатах.
cd /d "%~dp0\.."
if not exist .venv (call scripts\setup.bat)
call .venv\Scripts\activate.bat
set CHECK=%TEMP%\oko-check
set FAIL=0
if exist "%CHECK%" rmdir /s /q "%CHECK%"

echo.
echo [1/6] Окружение
python -m oko doctor

echo.
echo [2/6] Автотесты
python -m pytest -q || set FAIL=1

echo.
echo [3/6] Маленький набор: 3 машины и 3 водительских удостоверения
python -m oko generate --out "%CHECK%\data" --vehicles 3 --licenses 3 || set FAIL=1

echo.
echo [4/6] Распознавание Tesseract на этом наборе
python -m oko eval --engine tesseract --data "%CHECK%\data" --split all --variants clean --results "%CHECK%\results" || set FAIL=1

echo.
echo [5/6] Водительское удостоверение: распознать и проверить
python -m oko extract --engine tesseract "%CHECK%\data\images\d0000_driver_license.jpg" || set FAIL=1

echo.
echo [6/6] База и поиск
python -m oko db-fill --data "%CHECK%\data" --db "%CHECK%\oko.db" || set FAIL=1
python -m oko search "машины новее 2010 года" --db "%CHECK%\oko.db" || set FAIL=1

echo.
if %FAIL%==0 (echo ГОТОВО: все проверки прошли) else (echo ЕСТЬ ОШИБКИ: смотри сообщения выше)
pause
