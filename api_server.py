#!/usr/bin/env python3
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import pymysql


DEFAULT_PORT = int(os.getenv("API_PORT", "8080"))

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "simulados_app"),
    "password": os.getenv("MYSQL_PASSWORD", "Campi_117910"),
    "database": os.getenv("MYSQL_DATABASE", "simulados"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": True,
}


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def json_load(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def has_text(value):
    return value is not None and str(value).strip() != ""


def is_multipla(tipo):
    t = (tipo or "").lower()
    return "multipla" in t or "múltipla" in t or "escolha" in t or "objetiva" in t


def classify_row(row):
    alternativas = json_load(row.get("alternativas_json"), {})
    has_alternativas = isinstance(alternativas, dict) and len(alternativas) > 0
    tipo = row.get("tipo") or ""
    has_enunciado = has_text(row.get("enunciado_html"))
    has_resolucao = has_text(row.get("resolucao_html"))

    if has_alternativas:
        return "alternativas"
    if ("aberta" in tipo.lower() or "dissert" in tipo.lower()) and (has_enunciado or has_resolucao):
        return "aberta"
    if (not is_multipla(tipo)) and (has_enunciado or has_resolucao):
        return "aberta"
    return "erro"


def parse_filters(query):
    return {
        "q": unquote((query.get("q") or [""])[0]).strip(),
        "id": unquote((query.get("id") or [""])[0]).strip(),
        "materia": unquote((query.get("materia") or [""])[0]).strip(),
        "dificuldade": unquote((query.get("dificuldade") or [""])[0]).strip(),
        "tag": unquote((query.get("tag") or [""])[0]).strip(),
        "topico": unquote((query.get("topico") or [""])[0]).strip(),
        "ano": unquote((query.get("ano") or [""])[0]).strip(),
        "origem_titulo": unquote((query.get("origem_titulo") or [""])[0]).strip(),
        "tipo": unquote((query.get("tipo") or [""])[0]).strip().lower(),
    }


def build_where(filters):
    where = []
    args = []

    if filters["id"]:
        where.append("q.id = %s")
        args.append(filters["id"])
    if filters["materia"]:
        where.append("m.nome = %s")
        args.append(filters["materia"])
    if filters["dificuldade"]:
        where.append("d.nome = %s")
        args.append(filters["dificuldade"])
    if filters["ano"]:
        where.append("o.ano = %s")
        args.append(filters["ano"])
    if filters["origem_titulo"]:
        where.append("o.titulo LIKE %s")
        args.append(f"%{filters['origem_titulo']}%")
    if filters["topico"]:
        where.append(
            "EXISTS (SELECT 1 FROM questao_topicos qt JOIN topicos tp ON tp.id=qt.topico_id WHERE qt.questao_id=q.id AND tp.nome LIKE %s)"
        )
        args.append(f"%{filters['topico']}%")
    if filters["tag"]:
        where.append(
            "EXISTS (SELECT 1 FROM questao_tags qtg JOIN tags tg ON tg.id=qtg.tag_id WHERE qtg.questao_id=q.id AND tg.nome LIKE %s)"
        )
        args.append(f"%{filters['tag']}%")

    if filters["tipo"] in {"alternativas", "aberta", "erro"}:
        if filters["tipo"] == "alternativas":
            where.append("JSON_LENGTH(COALESCE(q.alternativas_json, JSON_OBJECT())) > 0")
        elif filters["tipo"] == "aberta":
            where.append(
                "(" 
                "((LOWER(COALESCE(t.nome,'')) LIKE '%aberta%' OR LOWER(COALESCE(t.nome,'')) LIKE '%dissert%') "
                "AND (NULLIF(TRIM(COALESCE(q.enunciado_html,'')), '') IS NOT NULL OR NULLIF(TRIM(COALESCE(q.resolucao_html,'')), '') IS NOT NULL)) "
                "OR "
                "(NOT (LOWER(COALESCE(t.nome,'')) LIKE '%multipla%' OR LOWER(COALESCE(t.nome,'')) LIKE '%múltipla%' OR LOWER(COALESCE(t.nome,'')) LIKE '%escolha%' OR LOWER(COALESCE(t.nome,'')) LIKE '%objetiva%') "
                "AND (NULLIF(TRIM(COALESCE(q.enunciado_html,'')), '') IS NOT NULL OR NULLIF(TRIM(COALESCE(q.resolucao_html,'')), '') IS NOT NULL))"
                ")"
            )
        else:
            where.append(
                "JSON_LENGTH(COALESCE(q.alternativas_json, JSON_OBJECT())) = 0 "
                "AND NOT ("
                "((LOWER(COALESCE(t.nome,'')) LIKE '%aberta%' OR LOWER(COALESCE(t.nome,'')) LIKE '%dissert%') "
                "AND (NULLIF(TRIM(COALESCE(q.enunciado_html,'')), '') IS NOT NULL OR NULLIF(TRIM(COALESCE(q.resolucao_html,'')), '') IS NOT NULL)) "
                "OR "
                "(NOT (LOWER(COALESCE(t.nome,'')) LIKE '%multipla%' OR LOWER(COALESCE(t.nome,'')) LIKE '%múltipla%' OR LOWER(COALESCE(t.nome,'')) LIKE '%escolha%' OR LOWER(COALESCE(t.nome,'')) LIKE '%objetiva%') "
                "AND (NULLIF(TRIM(COALESCE(q.enunciado_html,'')), '') IS NOT NULL OR NULLIF(TRIM(COALESCE(q.resolucao_html,'')), '') IS NOT NULL))"
                ")"
            )

    if filters["q"]:
        like_q = f"%{filters['q']}%"
        where.append(
            "(" 
            "q.id LIKE %s OR m.nome LIKE %s OR d.nome LIKE %s OR t.nome LIKE %s OR o.raw_text LIKE %s OR o.titulo LIKE %s OR o.numero LIKE %s "
            "OR q.enunciado_html LIKE %s OR q.resolucao_html LIKE %s OR q.gabarito LIKE %s "
            "OR EXISTS (SELECT 1 FROM questao_topicos qt JOIN topicos tp ON tp.id=qt.topico_id WHERE qt.questao_id=q.id AND tp.nome LIKE %s) "
            "OR EXISTS (SELECT 1 FROM questao_tags qtg JOIN tags tg ON tg.id=qtg.tag_id WHERE qtg.questao_id=q.id AND tg.nome LIKE %s)"
            ")"
        )
        args.extend([like_q] * 12)

    clause = " AND ".join(where)
    return (f"WHERE {clause}" if clause else ""), args


def base_from():
    return (
        " FROM questoes q "
        " LEFT JOIN materias m ON m.id=q.materia_id "
        " LEFT JOIN tipos t ON t.id=q.tipo_id "
        " LEFT JOIN dificuldades d ON d.id=q.dificuldade_id "
        " LEFT JOIN origens o ON o.id=q.origem_id "
    )


def fetch_question_tags_topicos(conn, ids):
    if not ids:
        return {}, {}
    ph = ",".join(["%s"] * len(ids))
    by_topicos = {i: [] for i in ids}
    by_tags = {i: [] for i in ids}
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT qt.questao_id, tp.nome FROM questao_topicos qt JOIN topicos tp ON tp.id=qt.topico_id WHERE qt.questao_id IN ({ph}) ORDER BY tp.nome",
            ids,
        )
        for r in cur.fetchall():
            by_topicos[r["questao_id"]].append(r["nome"])
        cur.execute(
            f"SELECT qtg.questao_id, tg.nome FROM questao_tags qtg JOIN tags tg ON tg.id=qtg.tag_id WHERE qtg.questao_id IN ({ph}) ORDER BY tg.nome",
            ids,
        )
        for r in cur.fetchall():
            by_tags[r["questao_id"]].append(r["nome"])
    return by_topicos, by_tags


def row_to_question(row, topicos, tags):
    origem = {
        "titulo": row.get("origem_titulo") or "",
        "ano": row.get("origem_ano") or "",
        "numero": row.get("origem_numero") or "",
        "extras": json_load(row.get("origem_extras_json"), []),
        "raw": row.get("origem_raw_text") or "",
    }
    return {
        "id": str(row.get("id") or ""),
        "tipo": row.get("tipo") or "",
        "origem": origem,
        "dificuldade": row.get("dificuldade") or "",
        "materia": row.get("materia") or "",
        "topicos": topicos,
        "tags": tags,
        "gabarito": row.get("gabarito") or "",
        "enunciado_html": row.get("enunciado_html") or "",
        "resolucao_html": row.get("resolucao_html") or "",
        "alternativas": json_load(row.get("alternativas_json"), {}),
        "textos_html": json_load(row.get("textos_html_json"), []),
        "bncc": json_load(row.get("bncc_json"), []),
    }


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class ApiHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == "/api/health":
                try:
                    conn = get_conn()
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                    conn.close()
                    return json_response(self, {"ok": True, "db": True})
                except Exception as exc:
                    return json_response(self, {"ok": False, "db": False, "error": str(exc)}, 500)

            if path == "/api/materias":
                conn = get_conn()
                with conn.cursor() as cur:
                    cur.execute("SELECT nome FROM materias ORDER BY nome")
                    materias = [r["nome"] for r in cur.fetchall()]
                conn.close()
                return json_response(self, {"materias": materias})

            if path == "/api/stats/geral":
                conn = get_conn()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                          COUNT(*) total,
                          SUM(CASE WHEN JSON_LENGTH(COALESCE(alternativas_json, JSON_OBJECT())) > 0 THEN 1 ELSE 0 END) alternativas
                        FROM questoes
                        """
                    )
                    r = cur.fetchone()
                conn.close()
                total = int(r["total"] or 0)
                alternativas = int(r["alternativas"] or 0)

                conn = get_conn()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT q.id, t.nome tipo, q.enunciado_html, q.resolucao_html, q.alternativas_json
                        FROM questoes q
                        LEFT JOIN tipos t ON t.id=q.tipo_id
                        """
                    )
                    rows = cur.fetchall()
                conn.close()

                abertas = 0
                erro = 0
                for row in rows:
                    cls = classify_row(row)
                    if cls == "aberta":
                        abertas += 1
                    elif cls == "erro":
                        erro += 1

                return json_response(
                    self,
                    {"arquivo": "mysql://simulados/questoes", "stats": {"total": total, "alternativas": alternativas, "abertas": abertas, "erro": erro}},
                )

            if path == "/api/stats/materias":
                conn = get_conn()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT q.id, m.nome materia, t.nome tipo, q.enunciado_html, q.resolucao_html, q.alternativas_json
                        FROM questoes q
                        LEFT JOIN materias m ON m.id=q.materia_id
                        LEFT JOIN tipos t ON t.id=q.tipo_id
                        """
                    )
                    rows = cur.fetchall()
                conn.close()

                by_materia = {}
                totais = {"total": 0, "alternativas": 0, "abertas": 0, "erro": 0}
                for row in rows:
                    m = row.get("materia") or ""
                    if m not in by_materia:
                        by_materia[m] = {"materia": m, "total": 0, "alternativas": 0, "abertas": 0, "erro": 0}
                    by_materia[m]["total"] += 1
                    totais["total"] += 1
                    cls = classify_row(row)
                    by_materia[m][cls] += 1
                    totais[cls] += 1

                materias = sorted(by_materia.values(), key=lambda x: x["materia"])
                return json_response(self, {"totais": totais, "materias": materias})

            if path == "/api/facets":
                filters = parse_filters(query)
                where, args = build_where(filters)
                conn = get_conn()
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) c {base_from()} {where}", args)
                    total_filtrado = int(cur.fetchone()["c"] or 0)

                    facets = {}
                    for key, col_expr, table_sql in [
                        ("materias", "m.nome", ""),
                        ("anos", "o.ano", ""),
                        ("origens_titulo", "o.titulo", ""),
                        ("dificuldades", "d.nome", ""),
                        ("tipos", "t.nome", ""),
                    ]:
                        cur.execute(
                            f"SELECT {col_expr} valor, COUNT(*) total {base_from()} {where} AND {col_expr} IS NOT NULL AND {col_expr} <> '' GROUP BY {col_expr} ORDER BY total DESC, {col_expr} ASC"
                            if where
                            else f"SELECT {col_expr} valor, COUNT(*) total {base_from()} WHERE {col_expr} IS NOT NULL AND {col_expr} <> '' GROUP BY {col_expr} ORDER BY total DESC, {col_expr} ASC",
                            args,
                        )
                        facets[key] = cur.fetchall()

                    cur.execute(
                        f"SELECT tp.nome valor, COUNT(*) total {base_from()} JOIN questao_topicos qt ON qt.questao_id=q.id JOIN topicos tp ON tp.id=qt.topico_id {where} GROUP BY tp.nome ORDER BY total DESC, tp.nome ASC",
                        args,
                    )
                    facets["topicos"] = cur.fetchall()

                    cur.execute(
                        f"SELECT tg.nome valor, COUNT(*) total {base_from()} JOIN questao_tags qtg ON qtg.questao_id=q.id JOIN tags tg ON tg.id=qtg.tag_id {where} GROUP BY tg.nome ORDER BY total DESC, tg.nome ASC",
                        args,
                    )
                    facets["tags"] = cur.fetchall()

                conn.close()
                return json_response(self, {"total_filtrado": total_filtrado, "facets": facets})

            if path == "/api/questoes":
                filters = parse_filters(query)
                limit = int((query.get("limit") or ["50"])[0])
                offset = int((query.get("offset") or ["0"])[0])
                if limit < 1:
                    limit = 1
                if limit > 500:
                    limit = 500
                if offset < 0:
                    offset = 0

                where, args = build_where(filters)
                conn = get_conn()
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) c {base_from()} {where}", args)
                    total = int(cur.fetchone()["c"] or 0)

                    cur.execute(
                        f"""
                        SELECT
                          q.id,
                          m.nome materia,
                          t.nome tipo,
                          d.nome dificuldade,
                          o.titulo origem_titulo,
                          o.ano origem_ano,
                          o.numero origem_numero,
                          o.raw_text origem_raw_text,
                          o.extras_json origem_extras_json,
                          q.gabarito,
                          q.enunciado_html,
                          q.resolucao_html,
                          q.alternativas_json,
                          q.textos_html_json,
                          q.bncc_json
                        {base_from()} {where}
                        ORDER BY q.id DESC
                        LIMIT %s OFFSET %s
                        """,
                        args + [limit, offset],
                    )
                    rows = cur.fetchall()

                ids = [r["id"] for r in rows]
                by_topicos, by_tags = fetch_question_tags_topicos(conn, ids)
                conn.close()

                questoes = [row_to_question(r, by_topicos.get(r["id"], []), by_tags.get(r["id"], [])) for r in rows]

                return json_response(
                    self,
                    {
                        "total": total,
                        "offset": offset,
                        "limit": limit,
                        "count": len(questoes),
                        "questoes": questoes,
                    },
                )

            return json_response(self, {"error": "rota não encontrada"}, 404)
        except Exception as exc:
            return json_response(self, {"error": str(exc)}, 500)

    def log_message(self, format, *args):
        return


def main():
    host = os.getenv("API_HOST", "0.0.0.0")
    port = DEFAULT_PORT
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f"API (MySQL) online em http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
