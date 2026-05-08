#!/bin/bash
# Auto-restarta o scraper sempre que parar, até ser interrompido (Ctrl+C)
cd "$(dirname "$0")"

attempt=0
while true; do
    attempt=$((attempt + 1))
    echo ""
    echo "========================================"
    echo "  TENTATIVA $attempt — $(date '+%H:%M:%S')"
    echo "========================================"

    python3 scraper.py >> /tmp/scraper_prod.log 2>&1

    code=$?
    count=$(python3 -c "import json; q=json.load(open('questoes_extraidas.json')); print(len(q))" 2>/dev/null || echo "?")
    echo "[loop] scraper saiu (código $code). Questões salvas: $count. Aguardando 5s para reiniciar..."
    sleep 5
done
