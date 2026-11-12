#!/usr/bin/env bash
# То же, что scripts/check_all.bat, для Linux и macOS
cd "$(dirname "$0")/.."
[ -d .venv ] || scripts/setup.sh
. .venv/bin/activate
CHECK=$(mktemp -d)
FAIL=0
echo "[1/6] Окружение"; python -m oko doctor
echo "[2/6] Автотесты"; python -m pytest -q || FAIL=1
echo "[3/6] Маленький набор"; python -m oko generate --out "$CHECK/data" --vehicles 3 --licenses 3 || FAIL=1
echo "[4/6] Распознавание Tesseract"; python -m oko eval --engine tesseract --data "$CHECK/data" --split all --variants clean --results "$CHECK/results" || FAIL=1
echo "[5/6] Водительское удостоверение"; python -m oko extract --engine tesseract "$CHECK/data/images/d0000_driver_license.jpg" || FAIL=1
echo "[6/6] База и поиск"; python -m oko db-fill --data "$CHECK/data" --db "$CHECK/oko.db" && python -m oko search "машины новее 2010 года" --db "$CHECK/oko.db" || FAIL=1
[ $FAIL = 0 ] && echo "ГОТОВО: все проверки прошли" || { echo "ЕСТЬ ОШИБКИ: смотри сообщения выше"; exit 1; }
