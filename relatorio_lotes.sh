#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${1:-/opt/robo-simulados/logs/robo-simulados-lotes.out.log}"

if [[ ! -f "$LOG_FILE" ]]; then
  echo "Log não encontrado: $LOG_FILE"
  exit 1
fi

awk '
BEGIN {
  materia="(sem_materia)";
  rodada=0;
  total_novos=0;
}

/^[[:space:]]*MATÉRIA:/ {
  materia=$0;
  sub(/^[[:space:]]*MATÉRIA:[[:space:]]*/, "", materia);
  passagens[materia]++;
  rodada++;
  rodada_materia[rodada]=materia;
  novos_rodada[rodada]=0;
  limite_rodada[rodada]=0;
  proxima_linha_novo=0;
}

/\[[0-9]+\][[:space:]]*#[0-9]+\.\.\./ {
  # linha de extração real (não é "já salva")
  # exemplo: [1] #476150...
  novos_materia[materia]++;
  novos_rodada[rodada]++;
  total_novos++;
  ultima_nova_linha=materia;
}

/ Limite de pulos consecutivos atingido / {
  limite_materia[materia]++;
  limite_rodada[rodada]++;
}

/ CONCLUÍDO! [0-9]+ questões em / {
  concluidos++;
}

END {
  printf("===============================================\n");
  printf("RELATÓRIO DE RODADAS (lotes por matéria)\n");
  printf("===============================================\n");
  printf("Arquivo de log: %s\n", ARGV[1]);
  printf("Rodadas detectadas: %d\n", rodada);
  printf("Concluídos detectados: %d\n", concluidos+0);
  printf("Novas extraídas (linhas de extração): %d\n", total_novos+0);
  printf("\n");

  printf("--- Resumo por matéria ---\n");
  printf("%-15s | %8s | %8s | %8s\n", "Matéria", "Passagens", "Limite600", "Novas");
  printf("-------------------------------------------------------------\n");
  for (m in passagens) {
    printf("%-15s | %8d | %8d | %8d\n", m, passagens[m]+0, limite_materia[m]+0, novos_materia[m]+0);
  }

  printf("\n--- Últimas 20 rodadas ---\n");
  ini = rodada - 19;
  if (ini < 1) ini = 1;
  for (i=ini; i<=rodada; i++) {
    m = rodada_materia[i];
    printf("#%d %-15s | novas=%d | limite600=%d\n", i, m, novos_rodada[i]+0, limite_rodada[i]+0);
  }
}
' "$LOG_FILE"
