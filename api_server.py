#!/usr/bin/env python3
import json
import os
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POR_MATERIA_DIR = os.path.join(BASE_DIR, "por_materia")
QUESTOES_FILE = os.path.join(BASE_DIR, "questoes_extraidas.json")
DEFAULT_PORT = int(os.getenv("API_PORT", "8080"))


def has_text(value):
    return value is not None and str(value).strip() != ""


def is_multipla(tipo):
    t = (tipo or "").lower()
    return "multipla" in t or "múltipla" in t or "escolha" in t or "objetiva" in t


def classify_question(q):
    alternativas = q.get("alternativas") or {}
    has_alternativas = isinstance(alternativas, dict) and len(alternativas) > 0
    tipo = q.get("tipo") or ""
    has_enunciado = has_text(q.get("enunciado_html")) or has_text(q.get("enunciado"))
    has_resolucao = has_text(q.get("resolucao_html"))

    if has_alternativas:
        return "alternativas"
    if ("aberta" in tipo.lower() or "dissert" in tipo.lower()) and (has_enunciado or has_resolucao):
        return "aberta"
    if (not is_multipla(tipo)) and (has_enunciado or has_resolucao):
        return "aberta"
    return "erro"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("questoes", [])


def contains_text(value, needle):
    if value is None:
        return False
    return needle in str(value).lower()


def question_matches(q, filters):
    qid = (filters.get("id") or "").strip().lower()
    if qid and str(q.get("id", "")).strip().lower() != qid:
        return False

    materia = (filters.get("materia") or "").strip().lower()
    if materia and str(q.get("materia", "")).strip().lower() != materia:
        return False

    dificuldade = (filters.get("dificuldade") or "").strip().lower()
    if dificuldade and str(q.get("dificuldade", "")).strip().lower() != dificuldade:
        return False

    ano = (filters.get("ano") or "").strip().lower()
    if ano and str((q.get("origem") or {}).get("ano", "")).strip().lower() != ano:
        return False

    origem_titulo = (filters.get("origem_titulo") or "").strip().lower()
    if origem_titulo and not contains_text((q.get("origem") or {}).get("titulo", ""), origem_titulo):
        return False

    tag = (filters.get("tag") or "").strip().lower()
    if tag:
        tags = [str(t).lower() for t in (q.get("tags") or [])]
        if not any(tag in t for t in tags):
            return False

    topico = (filters.get("topico") or "").strip().lower()
    if topico:
        topicos = [str(t).lower() for t in (q.get("topicos") or [])]
        if not any(topico in t for t in topicos):
            return False

    q_text = (filters.get("q") or "").strip().lower()
    if q_text:
        searchable = [
            q.get("id"),
            q.get("tipo"),
            q.get("materia"),
            q.get("dificuldade"),
            q.get("enunciado_html"),
            q.get("resolucao_html"),
            q.get("gabarito"),
            (q.get("origem") or {}).get("raw"),
            (q.get("origem") or {}).get("titulo"),
            (q.get("origem") or {}).get("numero"),
            " ".join([str(t) for t in (q.get("tags") or [])]),
            " ".join([str(t) for t in (q.get("topicos") or [])]),
        ]
        if not any(contains_text(v, q_text) for v in searchable):
            return False

    return True


def apply_filters(items, query):
    materia = unquote((query.get("materia") or [""])[0]).strip()
    tipo = (query.get("tipo") or [""])[0].strip().lower()
    search_q = unquote((query.get("q") or [""])[0]).strip()
    filtro_id = unquote((query.get("id") or [""])[0]).strip()
    dificuldade = unquote((query.get("dificuldade") or [""])[0]).strip()
    tag = unquote((query.get("tag") or [""])[0]).strip()
    topico = unquote((query.get("topico") or [""])[0]).strip()
    ano = unquote((query.get("ano") or [""])[0]).strip()
    origem_titulo = unquote((query.get("origem_titulo") or [""])[0]).strip()

    if tipo in {"alternativas", "aberta", "erro"}:
        items = [q for q in items if classify_question(q) == tipo]

    filters = {
        "q": search_q,
        "id": filtro_id,
        "materia": materia,
        "dificuldade": dificuldade,
        "tag": tag,
        "topico": topico,
        "ano": ano,
        "origem_titulo": origem_titulo,
    }
    if any(v for v in filters.values()):
        items = [q for q in items if question_matches(q, filters)]
    return items


def build_facets(items):
    materias = Counter()
    anos = Counter()
    origens = Counter()
    dificuldades = Counter()
    tipos = Counter()
    topicos = Counter()
    tags = Counter()

    for q in items:
        materia = str(q.get("materia", "")).strip()
        if materia:
            materias[materia] += 1
        origem = q.get("origem") or {}
        ano = str(origem.get("ano", "")).strip()
        if ano:
            anos[ano] += 1
        titulo = str(origem.get("titulo", "")).strip()
        if titulo:
            origens[titulo] += 1
        dificuldade = str(q.get("dificuldade", "")).strip()
        if dificuldade:
            dificuldades[dificuldade] += 1
        tipo = str(q.get("tipo", "")).strip()
        if tipo:
            tipos[tipo] += 1
        for t in (q.get("topicos") or []):
            tt = str(t).strip()
            if tt:
                topicos[tt] += 1
        for tg in (q.get("tags") or []):
            tg = str(tg).strip()
            if tg:
                tags[tg] += 1

    def to_list(counter):
        return [{"valor": k, "total": v} for k, v in counter.most_common()]

    return {
        "materias": to_list(materias),
        "anos": to_list(anos),
        "origens_titulo": to_list(origens),
        "dificuldades": to_list(dificuldades),
        "tipos": to_list(tipos),
        "topicos": to_list(topicos),
        "tags": to_list(tags),
    }


def stats_for_list(items):
    stats = {"total": len(items), "alternativas": 0, "abertas": 0, "erro": 0}
    for q in items:
        cls = classify_question(q)
        if cls == "alternativas":
            stats["alternativas"] += 1
        elif cls == "aberta":
            stats["abertas"] += 1
        else:
            stats["erro"] += 1
    return stats


def build_materia_filename(materia):
    return os.path.join(POR_MATERIA_DIR, f"questoes_{materia}.json")


def list_materias():
    if not os.path.isdir(POR_MATERIA_DIR):
        return []
    out = []
    for name in os.listdir(POR_MATERIA_DIR):
        if name.startswith("questoes_") and name.endswith(".json"):
            out.append(name[len("questoes_") : -len(".json")])
    return sorted(out)


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
                return json_response(self, {"ok": True})

            if path == "/api/materias":
                return json_response(self, {"materias": list_materias()})

            if path == "/api/stats/geral":
                if not os.path.exists(QUESTOES_FILE):
                    return json_response(self, {"error": "questoes_extraidas.json não encontrado"}, 404)
                all_q = load_json(QUESTOES_FILE)
                return json_response(self, {"arquivo": QUESTOES_FILE, "stats": stats_for_list(all_q)})

            if path == "/api/stats/materias":
                materias = list_materias()
                rows = []
                totals = {"total": 0, "alternativas": 0, "abertas": 0, "erro": 0}
                for m in materias:
                    fp = build_materia_filename(m)
                    items = load_json(fp)
                    stats = stats_for_list(items)
                    rows.append({"materia": m, **stats})
                    for k in totals:
                        totals[k] += stats[k]
                return json_response(self, {"totais": totals, "materias": rows})

            if path == "/api/facets":
                items = load_json(QUESTOES_FILE)
                filtered = apply_filters(items, query)
                return json_response(
                    self,
                    {
                        "total_filtrado": len(filtered),
                        "facets": build_facets(filtered),
                    },
                )

            if path == "/api/questoes":
                materia = unquote((query.get("materia") or [""])[0]).strip()
                limit = int((query.get("limit") or ["50"])[0])
                offset = int((query.get("offset") or ["0"])[0])
                if limit < 1:
                    limit = 1
                if limit > 500:
                    limit = 500
                if offset < 0:
                    offset = 0

                if materia:
                    fp = build_materia_filename(materia)
                    if not os.path.exists(fp):
                        return json_response(self, {"error": f"matéria não encontrada: {materia}"}, 404)
                    items = load_json(fp)
                else:
                    items = load_json(QUESTOES_FILE)

                items = apply_filters(items, query)

                total = len(items)
                page = items[offset : offset + limit]
                return json_response(
                    self,
                    {
                        "total": total,
                        "offset": offset,
                        "limit": limit,
                        "count": len(page),
                        "questoes": page,
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
    print(f"API online em http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
