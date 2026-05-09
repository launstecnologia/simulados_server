#!/usr/bin/env python3
import hashlib
import json
import os
from datetime import datetime, timezone

import pymysql


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTOES_FILE = os.path.join(BASE_DIR, "questoes_extraidas.json")


def env(name, default=None, required=False):
    val = os.getenv(name, default)
    if required and not val:
        raise ValueError(f"Variável obrigatória ausente: {name}")
    return val


def load_questions():
    with open(QUESTOES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get("questoes", [])


def as_json(value):
    return json.dumps(value or [], ensure_ascii=False)


def origin_key(origem):
    raw = f"{origem.get('titulo','')}|{origem.get('ano','')}|{origem.get('numero','')}|{origem.get('raw','')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def q_hash(q):
    payload = {
        "tipo": q.get("tipo"),
        "materia": q.get("materia"),
        "dificuldade": q.get("dificuldade"),
        "origem": q.get("origem"),
        "gabarito": q.get("gabarito"),
        "enunciado_html": q.get("enunciado_html"),
        "resolucao_html": q.get("resolucao_html"),
        "alternativas": q.get("alternativas"),
        "textos_html": q.get("textos_html"),
        "bncc": q.get("bncc"),
        "topicos": q.get("topicos"),
        "tags": q.get("tags"),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class DictCache:
    def __init__(self):
        self.materias = {}
        self.tipos = {}
        self.dificuldades = {}
        self.topicos = {}
        self.tags = {}
        self.origens = {}


def get_or_create(cur, table, value, cache):
    v = (value or "").strip()
    if not v:
        return None
    if v in cache:
        return cache[v]
    cur.execute(f"INSERT INTO {table} (nome) VALUES (%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)", (v,))
    cache[v] = cur.lastrowid
    return cache[v]


def get_or_create_origem(cur, origem, cache):
    origem = origem or {}
    key = origin_key(origem)
    if key in cache:
        return cache[key]
    cur.execute(
        """
        INSERT INTO origens (titulo, ano, numero, raw_text, extras_json, unique_key)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
        """,
        (
            (origem.get("titulo") or "").strip(),
            (origem.get("ano") or "").strip(),
            (origem.get("numero") or "").strip(),
            (origem.get("raw") or "").strip(),
            as_json(origem.get("extras") or []),
            key,
        ),
    )
    cache[key] = cur.lastrowid
    return cache[key]


def sync():
    cfg = {
        "host": env("MYSQL_HOST", required=True),
        "port": int(env("MYSQL_PORT", "3306")),
        "user": env("MYSQL_USER", required=True),
        "password": env("MYSQL_PASSWORD", required=True),
        "database": env("MYSQL_DATABASE", "simulados"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.Cursor,
        "autocommit": False,
    }

    questoes = load_questions()
    cache = DictCache()
    inserted = 0
    updated = 0

    conn = pymysql.connect(**cfg)
    try:
        with conn.cursor() as cur:
            for q in questoes:
                qid = str(q.get("id", "")).strip()
                if not qid:
                    continue

                materia_id = get_or_create(cur, "materias", q.get("materia"), cache.materias)
                tipo_id = get_or_create(cur, "tipos", q.get("tipo"), cache.tipos)
                dificuldade_id = get_or_create(cur, "dificuldades", q.get("dificuldade"), cache.dificuldades)
                origem_id = get_or_create_origem(cur, q.get("origem") or {}, cache.origens)
                source_hash = q_hash(q)

                cur.execute("SELECT source_hash FROM questoes WHERE id=%s", (qid,))
                row = cur.fetchone()
                exists = row is not None
                changed = (not exists) or (row[0] != source_hash)

                if changed:
                    cur.execute(
                        """
                        INSERT INTO questoes
                          (id, materia_id, tipo_id, dificuldade_id, origem_id, gabarito,
                           enunciado_html, resolucao_html, alternativas_json, textos_html_json, bncc_json,
                           topicos_json, tags_json, source_hash)
                        VALUES
                          (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                          materia_id=VALUES(materia_id),
                          tipo_id=VALUES(tipo_id),
                          dificuldade_id=VALUES(dificuldade_id),
                          origem_id=VALUES(origem_id),
                          gabarito=VALUES(gabarito),
                          enunciado_html=VALUES(enunciado_html),
                          resolucao_html=VALUES(resolucao_html),
                          alternativas_json=VALUES(alternativas_json),
                          textos_html_json=VALUES(textos_html_json),
                          bncc_json=VALUES(bncc_json),
                          topicos_json=VALUES(topicos_json),
                          tags_json=VALUES(tags_json),
                          source_hash=VALUES(source_hash)
                        """,
                        (
                            qid,
                            materia_id,
                            tipo_id,
                            dificuldade_id,
                            origem_id,
                            (q.get("gabarito") or "").strip() or None,
                            q.get("enunciado_html"),
                            q.get("resolucao_html"),
                            as_json(q.get("alternativas") or {}),
                            as_json(q.get("textos_html") or []),
                            as_json(q.get("bncc") or []),
                            as_json(q.get("topicos") or []),
                            as_json(q.get("tags") or []),
                            source_hash,
                        ),
                    )
                    if exists:
                        updated += 1
                    else:
                        inserted += 1

                    cur.execute("DELETE FROM questao_topicos WHERE questao_id=%s", (qid,))
                    cur.execute("DELETE FROM questao_tags WHERE questao_id=%s", (qid,))

                    for topico in (q.get("topicos") or []):
                        topico_id = get_or_create(cur, "topicos", str(topico), cache.topicos)
                        if topico_id:
                            cur.execute(
                                "INSERT IGNORE INTO questao_topicos (questao_id, topico_id) VALUES (%s, %s)",
                                (qid, topico_id),
                            )

                    for tag in (q.get("tags") or []):
                        tag_id = get_or_create(cur, "tags", str(tag), cache.tags)
                        if tag_id:
                            cur.execute(
                                "INSERT IGNORE INTO questao_tags (questao_id, tag_id) VALUES (%s, %s)",
                                (qid, tag_id),
                            )

            cur.execute(
                """
                UPDATE sync_status
                SET last_run_at=%s, total_questoes=%s, inserted_count=%s, updated_count=%s
                WHERE id=1
                """,
                (datetime.now(timezone.utc), len(questoes), inserted, updated),
            )

        conn.commit()
    finally:
        conn.close()

    print(f"Total lidas: {len(questoes)}")
    print(f"Inseridas: {inserted}")
    print(f"Atualizadas: {updated}")


if __name__ == "__main__":
    sync()
