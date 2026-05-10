#!/usr/bin/env bash
set -euo pipefail

cd /opt/robo-simulados
mkdir -p logs

# Atualiza codigo antes da rodada (sem quebrar se nao houver remote momentaneo)
git pull --ff-only || true

export PYTHON_BIN="/opt/robo-simulados/.venv/bin/python"
export HEADLESS="${HEADLESS:-1}"
export EXTRAIR_BNCC="${EXTRAIR_BNCC:-1}"
export RELOAD_ENTRE_IDS="${RELOAD_ENTRE_IDS:-1}"
export UNICO_POR_ID_MATERIA="${UNICO_POR_ID_MATERIA:-1}"
export LOTE_POR_MATERIA="${LOTE_POR_MATERIA:-1000}"
export ROBO_MAX_PULOS_CONSEC="${ROBO_MAX_PULOS_CONSEC:-600}"

/bin/bash /opt/robo-simulados/run_lotes_por_materia.sh

# Atualiza MySQL ao final de cada rodada
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}" \
MYSQL_PORT="${MYSQL_PORT:-3306}" \
MYSQL_USER="${MYSQL_USER:-simulados_app}" \
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}" \
MYSQL_DATABASE="${MYSQL_DATABASE:-simulados}" \
/opt/robo-simulados/.venv/bin/python /opt/robo-simulados/sync_mysql.py \
  >> /opt/robo-simulados/logs/cron_sync_mysql.log 2>&1 || true
