#!/usr/bin/env python3
import csv
import json
import os
from collections import Counter, defaultdict


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "questoes_extraidas.json")
OUT_DIR = os.path.join(BASE_DIR, "exports")
OUT_FLAT = os.path.join(OUT_DIR, "select_exercicios_flat.csv")
OUT_TOPICOS = os.path.join(OUT_DIR, "select_exercicios_topicos.csv")
OUT_RESUMO = os.path.join(OUT_DIR, "select_exercicios_resumo.json")


def load_questions():
    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("questoes", [])


def normalize_list(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def main():
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"Arquivo não encontrado: {INPUT_FILE}")

    os.makedirs(OUT_DIR, exist_ok=True)
    questoes = load_questions()

    cnt_materia = Counter()
    cnt_ano = Counter()
    cnt_topico = Counter()
    cnt_tag = Counter()
    mapa_materia_ano = defaultdict(Counter)
    mapa_materia_topico = defaultdict(Counter)

    with open(OUT_FLAT, "w", newline="", encoding="utf-8") as f_flat, open(
        OUT_TOPICOS, "w", newline="", encoding="utf-8"
    ) as f_top:
        w_flat = csv.writer(f_flat)
        w_top = csv.writer(f_top)

        w_flat.writerow(
            [
                "id",
                "materia",
                "tipo",
                "dificuldade",
                "ano",
                "origem_titulo",
                "origem_numero",
                "gabarito",
                "qtd_alternativas",
                "topicos",
                "tags",
            ]
        )
        w_top.writerow(
            [
                "id",
                "materia",
                "ano",
                "topico",
                "dificuldade",
                "tipo",
                "origem_titulo",
            ]
        )

        for q in questoes:
            qid = str(q.get("id", "")).strip()
            materia = str(q.get("materia", "")).strip()
            tipo = str(q.get("tipo", "")).strip()
            dificuldade = str(q.get("dificuldade", "")).strip()
            origem = q.get("origem") or {}
            ano = str(origem.get("ano", "")).strip()
            origem_titulo = str(origem.get("titulo", "")).strip()
            origem_numero = str(origem.get("numero", "")).strip()
            gabarito = str(q.get("gabarito", "")).strip()
            alternativas = q.get("alternativas") or {}
            qtd_alternativas = len(alternativas) if isinstance(alternativas, dict) else 0
            topicos = normalize_list(q.get("topicos"))
            tags = normalize_list(q.get("tags"))

            cnt_materia[materia] += 1
            if ano:
                cnt_ano[ano] += 1

            for t in topicos:
                cnt_topico[t] += 1
                if materia:
                    mapa_materia_topico[materia][t] += 1
            for tg in tags:
                cnt_tag[tg] += 1
            if materia and ano:
                mapa_materia_ano[materia][ano] += 1

            w_flat.writerow(
                [
                    qid,
                    materia,
                    tipo,
                    dificuldade,
                    ano,
                    origem_titulo,
                    origem_numero,
                    gabarito,
                    qtd_alternativas,
                    " | ".join(topicos),
                    " | ".join(tags),
                ]
            )

            if topicos:
                for topico in topicos:
                    w_top.writerow([qid, materia, ano, topico, dificuldade, tipo, origem_titulo])
            else:
                w_top.writerow([qid, materia, ano, "", dificuldade, tipo, origem_titulo])

    resumo = {
        "total_questoes": len(questoes),
        "materias": dict(cnt_materia.most_common()),
        "anos": dict(cnt_ano.most_common()),
        "topicos_top_100": dict(cnt_topico.most_common(100)),
        "tags_top_100": dict(cnt_tag.most_common(100)),
        "materia_x_ano": {k: dict(v.most_common()) for k, v in mapa_materia_ano.items()},
        "materia_x_topico_top_30": {
            k: dict(v.most_common(30)) for k, v in mapa_materia_topico.items()
        },
    }

    with open(OUT_RESUMO, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)

    print(f"Total questões: {len(questoes)}")
    print(f"Gerado: {OUT_FLAT}")
    print(f"Gerado: {OUT_TOPICOS}")
    print(f"Gerado: {OUT_RESUMO}")


if __name__ == "__main__":
    main()
