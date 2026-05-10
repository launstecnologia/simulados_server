#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
SAIDA_BASE="${SAIDA_BASE:-questoes_extraidas.json}"
CHECKPOINT_BASE="${CHECKPOINT_BASE:-scraper_checkpoint.json}"
LOTE_POR_MATERIA="${LOTE_POR_MATERIA:-1000}"
HEADLESS="${HEADLESS:-1}"
EXTRAIR_BNCC="${EXTRAIR_BNCC:-1}"
RELOAD_ENTRE_IDS="${RELOAD_ENTRE_IDS:-1}"
UNICO_POR_ID_MATERIA="${UNICO_POR_ID_MATERIA:-1}"

# Ordem sugerida (pode editar)
MATERIAS=(
  "Biologia"
  "Português"
  "Matemática"
  "Química"
  "Física"
  "História"
  "Geografia"
  "Sociologia"
  "Filosofia"
  "Eletivas"
  "Arte"
  "Inglês"
)

echo "Iniciando lotes por matéria..."
echo "Lote por matéria: ${LOTE_POR_MATERIA}"
echo "Headless: ${HEADLESS} | BNCC: ${EXTRAIR_BNCC}"
echo

for materia in "${MATERIAS[@]}"; do
  echo "=================================================="
  echo "MATÉRIA: ${materia}"
  echo "=================================================="

  ROBO_SAIDA="${SAIDA_BASE}" \
  ROBO_CHECKPOINT="${CHECKPOINT_BASE}" \
  ROBO_MATERIA="${materia}" \
  ROBO_MAX_NOVAS="${LOTE_POR_MATERIA}" \
  ROBO_EXTRAIR_BNCC="${EXTRAIR_BNCC}" \
  ROBO_UNICO_POR_ID_MATERIA="${UNICO_POR_ID_MATERIA}" \
  ROBO_RELOAD_ENTRE_IDS="${RELOAD_ENTRE_IDS}" \
  ROBO_HEADLESS="${HEADLESS}" \
  "${PYTHON_BIN}" scraper.py

  echo
done

echo "=================================================="
echo "Todos os lotes por matéria concluídos."
echo "=================================================="
