from playwright.sync_api import sync_playwright
import time, json, os, re
from html import unescape
from datetime import datetime

# ── CONFIGURAÇÕES ────────────────────────────────────────
EMAIL = os.getenv("ROBO_EMAIL", "matheustozzo@yahoo.com.br")
SENHA = os.getenv("ROBO_SENHA", "Mat09074170#")
SAIDA = "questoes_extraidas.json"
CHECKPOINT = "scraper_checkpoint.json"  # página, índice e horário da última pausa
ATIVIDADE_URL = "https://avaliafacil.grupoetapa.com.br/avaliafacil/listas/atividade/182353"  # banco geral (30k+ páginas)
PAGINAS_LIMITE = None     # None = todas as páginas
MAX_QUESTOES = None       # None = sem limite (extrai todas as questões)

# ── Desempenho ───────────────────────────────────────────
# MODO_RAPIDO: pausas ~40% do normal + paginação espera pelo DOM em vez de sleep fixo longo.
MODO_RAPIDO = True
HEADLESS = os.getenv("ROBO_HEADLESS", "1").strip().lower() in {"1", "true", "yes", "y", "on"}
# BNCC e textos vinculados são modais extras por questão — desligue se não precisar no JSON (maior ganho).
EXTRAIR_TEXTOS_VINCULADOS = False
EXTRAIR_BNCC = os.getenv("ROBO_EXTRAIR_BNCC", "1").strip().lower() in {"1", "true", "yes", "y", "on"}
MATERIA_ALVO = os.getenv("ROBO_MATERIA", "").strip()
# Quando ativo, trata a mesma questão em matérias diferentes como registros distintos.
UNICO_POR_ID_E_MATERIA = os.getenv("ROBO_UNICO_POR_ID_MATERIA", "1").strip().lower() in {"1", "true", "yes", "y", "on"}


def espera(segundos):
    """Pausa fixa ou reduzida conforme MODO_RAPIDO (mínimo ~60 ms)."""
    if not MODO_RAPIDO:
        return float(segundos)
    return max(0.06, float(segundos) * 0.42)


def _tipo_multipla(tipo):
    t = (tipo or "").strip().lower()
    return "multipla" in t or "múltipla" in t or "escolha" in t or t in {"objetiva", "multipla_escolha"}


def _texto_limpo_html(html):
    if not html:
        return ""
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def extrair_alternativas_html_local(html):
    """
    Recupera alternativas/gabarito a partir de um HTML já salvo (sem depender do DOM da página).
    Útil para reaproveitar resolucao_html quando o botão "Alternativas" não abriu.
    """
    if not html:
        return {}, None

    alts = {}
    gabarito = None

    # Estrutura comum: blocos flex com círculo (A-E) e texto da alternativa.
    rows = re.findall(r"<div[^>]*class=[\"'][^\"']*flex[^\"']*[\"'][^>]*>(.*?)</div>", html, flags=re.I | re.S)
    for row in rows:
        m = re.search(r"<span[^>]*class=[\"']([^\"']*)[\"'][^>]*>\s*([A-E])\s*</span>", row, flags=re.I | re.S)
        if not m:
            continue
        cls = (m.group(1) or "").lower()
        letra = m.group(2).upper()
        resto = row[m.end():]
        texto = _texto_limpo_html(resto)
        if texto and not alts.get(letra):
            alts[letra] = texto
        if "emerald" in cls or "green" in cls or "success" in cls:
            gabarito = letra

    # Fallback textual: "A) texto"
    if not alts:
        texto_modal = _texto_limpo_html(html)
        for letra, texto in re.findall(r"\b([A-E])\)\s*([^\n\r]+?)(?=\s+[A-E]\)\s+|$)", texto_modal):
            letra = letra.upper()
            if not alts.get(letra):
                alts[letra] = texto.strip()

    return alts, gabarito


def questao_completa(q):
    """
    Uma questão é considerada completa quando foi processada e não há mais nada a tentar.
    - Múltipla escolha: tem alternativas+gabarito  OU  já foi tentada sem conteúdo
    - Dissertativa:     tem resolucao_html          OU  já foi tentada sem conteúdo
    O flag 'extracao_tentada' é marcado quando o clique funciona mas o modal fica vazio.
    """
    if q.get("extracao_tentada"):
        return True
    if _tipo_multipla(q.get("tipo")):
        return bool(q.get("alternativas")) and bool(q.get("gabarito"))
    return bool(q.get("alternativas")) or bool(q.get("resolucao_html"))


# Filtros disponíveis na plataforma.
# True  → clica em "Selecionar todos"
# []    → não aplica este filtro (deixa em branco)
# [...] → seleciona itens específicos, ex: ["Biologia", "Química"]
FILTROS = {
    # ── Matérias / Assuntos / Tópicos / Subtópicos ──────
    "Matérias":          True,   # seleciona todas as matérias
    "Assuntos":          [],
    "Tópicos":           [],
    "Subtópicos":        [],

    # ── Dados da Questão ─────────────────────────────────
    "Origens":           [],     # ex: ["FPS", "ENEM"]
    "Fases":             [],
    "Dias":              [],
    "Semestres":         [],
    "Anos":              [],
    "Dificuldades":      [],     # ex: ["Fácil", "Médio", "Difícil"]
    "Tipo de Questão":   [],

    # ── Apostilas ─────────────────────────────────────────
    "Tipo de Material":  [],
    "Cadernos":          [],
    "Nomes de Apostilas":[],
    "Segmentos":         [],
    "Series":            [],
    "Volumes":           [],
}
# ─────────────────────────────────────────────────────────
if MATERIA_ALVO:
    FILTROS["Matérias"] = [MATERIA_ALVO]


def _chave_questao(q):
    qid = (q.get("id") or "").strip()
    if not qid:
        return ""
    if not UNICO_POR_ID_E_MATERIA:
        return qid
    materia = (q.get("materia") or "").strip().upper()
    return f"{qid}__{materia}"


def salvar(questoes):
    # Escrita atômica: grava em .tmp e renomeia — evita JSON corrompido se o processo for
    # interrompido no meio da escrita.
    tmp = SAIDA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(questoes, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SAIDA)  # rename atômico (POSIX) — substitui o arquivo de uma vez

    # Salva também por matéria na pasta por_materia/
    try:
        os.makedirs("por_materia", exist_ok=True)
        por_materia = {}
        for q in questoes:
            mat = q.get("materia") or "Sem_Materia"
            por_materia.setdefault(mat, []).append(q)
        for mat, lista in por_materia.items():
            nome = re.sub(r'[^\w\s-]', '', mat).strip().replace(' ', '_')
            tmp_mat = f"por_materia/questoes_{nome}.json.tmp"
            with open(tmp_mat, "w", encoding="utf-8") as f:
                json.dump(lista, f, ensure_ascii=False, indent=2)
            os.replace(tmp_mat, f"por_materia/questoes_{nome}.json")
    except Exception:
        pass


def carregar():
    if os.path.exists(SAIDA):
        with open(SAIDA, encoding="utf-8") as f:
            dados = json.load(f)

        # Reaproveita o que já foi salvo: se múltipla está sem alternativas,
        # tenta recuperar a partir do HTML de resolução já existente.
        recuperadas = 0
        for q in dados:
            if _tipo_multipla(q.get("tipo")) and not q.get("alternativas") and q.get("resolucao_html"):
                alts, gab = extrair_alternativas_html_local(q.get("resolucao_html"))
                if alts:
                    q["alternativas"] = alts
                    if gab:
                        q["gabarito"] = gab
                    recuperadas += 1

        completas = sum(1 for q in dados if questao_completa(q))
        incompletas = len(dados) - completas
        print(f"[RETOMADA] {len(dados)} questões: {completas} completas, {incompletas} incompletas.")
        if recuperadas:
            print(f"[RETOMADA] {recuperadas} questões recuperadas via resolucao_html.")
        if recuperadas:
            salvar(dados)
        return dados  # retorna TODAS — incompletas serão refeitas quando encontradas novamente
    return []


def _agora_iso():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def salvar_checkpoint(pagina, indice_proximo, ultimo_id=None):
    """Grava onde continuar (próxima questão = indice_proximo na página `pagina`)."""
    payload = {
        "pausado_em": _agora_iso(),
        "pagina": int(pagina),
        "indice_proximo": int(indice_proximo),
        "ultimo_id": ultimo_id or "",
    }
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def carregar_checkpoint():
    if not os.path.exists(CHECKPOINT):
        return None
    try:
        with open(CHECKPOINT, encoding="utf-8") as f:
            d = json.load(f)
        return {
            "pausado_em": d.get("pausado_em", ""),
            "pagina": max(1, int(d.get("pagina", 1))),
            "indice_proximo": max(0, int(d.get("indice_proximo", 0))),
            "ultimo_id": d.get("ultimo_id") or "",
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def apagar_checkpoint():
    if os.path.exists(CHECKPOINT):
        os.remove(CHECKPOINT)


def clicar_proxima_pagina(ap):
    """Clica no controle de próxima página. Mesma lógica do loop principal."""
    return ap.evaluate("""
        () => {
            for (const label of ['Próxima página', 'Next page', 'next', 'próxima', 'Go to next page']) {
                const btn = document.querySelector(`[aria-label="${label}"]`);
                if (btn && !btn.disabled) { btn.click(); return true; }
            }
            // Fallback para Material UI NavigateNextIcon
            const nextIcon = document.querySelector('[data-testid="NavigateNextIcon"]');
            if (nextIcon) {
                const btn = nextIcon.closest('button');
                if (btn && !btn.disabled) { btn.click(); return true; }
            }
            const navBtns = [...document.querySelectorAll('nav button, [class*="pagination"] button')];
            const proxBtn = navBtns.find(b => {
                const t = b.innerText.trim();
                return (t === '>' || t === '›') && !b.disabled;
            });
            if (proxBtn) { proxBtn.click(); return true; }
            if (navBtns.length >= 2) {
                const btn = navBtns[navBtns.length - 2];
                if (!btn.disabled) { btn.click(); return true; }
            }
            return false;
        }
    """)


# ── CONVERTER IMAGENS PARA BASE64 ────────────────────────
def imagens_para_base64(page, html):
    """
    Recebe o HTML do enunciado e converte todas as <img src="...">
    para data URIs base64, evitando salvar arquivos no disco.
    Roda fetch() dentro do contexto do browser, que já tem as imagens em cache.
    """
    if "<img" not in html:
        return html

    resultado = page.evaluate("""
        async (html) => {
            const div = document.createElement('div');
            div.innerHTML = html;
            const imgs = div.querySelectorAll('img');

            for (const img of imgs) {
                const src = img.getAttribute('src');
                if (!src || src.startsWith('data:')) continue;

                try {
                    // Usa a URL absoluta caso o src seja relativo
                    const url = new URL(src, location.href).href;
                    const resp = await fetch(url);
                    if (!resp.ok) continue;
                    const blob = await resp.blob();
                    const base64 = await new Promise((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onload  = () => resolve(reader.result);
                        reader.onerror = reject;
                        reader.readAsDataURL(blob);
                    });
                    img.src = base64;
                    img.removeAttribute('srcset'); // remove alternativas de resolução
                } catch (e) {
                    // mantém src original se falhar
                }
            }
            return div.innerHTML;
        }
    """, html)

    return resultado if resultado else html


# ── FECHAR MODAL ─────────────────────────────────────────
def fechar_modal(page):
    page.evaluate("""
        () => {
            // SweetAlert2 (alternativas)
            const swalBtn = document.querySelector('.swal2-confirm');
            if (swalBtn) { swalBtn.click(); }
            // MUI Dialog (BNCC / resolução)
            for (const btn of document.querySelectorAll('button')) {
                if (btn.innerText.trim() === 'Fechar') { btn.click(); break; }
            }
            // fallback Escape
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        }
    """)
    time.sleep(espera(0.5))
    try:
        page.wait_for_selector('.swal2-popup', state="hidden", timeout=2000)
    except Exception:
        pass
    try:
        page.wait_for_selector('[class*="MuiDialog-root"]', state="hidden", timeout=2000)
    except Exception:
        pass
    # Limpa resíduos do SweetAlert2 no body que bloqueiam MUI dialogs
    page.evaluate("""
        () => {
            document.body.classList.remove(
                'swal2-shown', 'swal2-height-auto', 'swal2-no-backdrop',
                'swal2-iosfix', 'swal2-toast-shown'
            );
            document.querySelectorAll('.swal2-container').forEach(el => el.remove());
        }
    """)
    time.sleep(espera(0.3))


# ── EXTRAIR ALTERNATIVAS ──────────────────────────────────
def extrair_alternativas(page):
    """
    Modal SweetAlert2 / MUI aberto.
    Salva o innerHTML de cada alternativa (preserva MathJax, imagens, texto).
    """
    try:
        page.wait_for_selector('.swal2-html-container, [class*="MuiDialogContent"]', timeout=5000)
    except:
        return {}, None

    # Aguarda o "Carregando..." sumir e o conteúdo real aparecer
    try:
        page.wait_for_function("""
            () => {
                const containers = [...document.querySelectorAll('.swal2-html-container, [class*="MuiDialogContent"]')];
                const container = containers.find(c => c.offsetParent !== null) || containers.pop();
                if (!container) return false;
                const text = (container.innerText || '').trim();
                // Aguarda enquanto estiver carregando ou vazio
                return text.length > 5 && !text.toLowerCase().includes('carregando');
            }
        """, timeout=8000)
    except Exception:
        pass  # conteúdo pode não carregar — tenta extrair mesmo assim

    resultado = page.evaluate("""
        () => {
            const containers = [...document.querySelectorAll('.swal2-html-container, [class*="MuiDialogContent"]')];
            const container = containers.find(c => c.offsetParent !== null) || containers.pop();
            if (!container) return { alts: {}, gabarito: null };

            const alts = {};
            let gabarito = null;
            const LETRAS = new Set(['A','B','C','D','E']);

            // Letra limpa de um elemento (só texto direto, ignora descendentes MathJax)
            function letraEl(el) {
                if (!el) return '';
                // Texto direto do nó (não de filhos) — evita pegar conteúdo MathJax
                const direto = Array.from(el.childNodes)
                    .filter(n => n.nodeType === 3)
                    .map(n => n.textContent.trim())
                    .join('');
                if (direto) return direto;
                return (el.innerText || '').trim().replace(/\\s+/g, ' ');
            }

            function isVerde(el) {
                if (!el) return false;
                const cls = el.className || '';
                if (cls.includes('emerald') || cls.includes('green') || cls.includes('success')) return true;
                const bg = window.getComputedStyle(el).backgroundColor;
                const nums = bg.match(/\\d+/g);
                if (!nums) return false;
                const [r, g, b] = nums.map(Number);
                return g > 140 && g > r * 1.15 && g > b * 1.15;
            }

            // ── Estratégia 1: div.flex > span(letra) + span(conteúdo) ──────
            // Conteúdo salvo como innerHTML (preserva MathJax / imagens / texto)
            const rows = container.querySelectorAll('div.flex, div[class*="flex"]');
            for (const row of rows) {
                const spans = row.querySelectorAll(':scope > span');
                if (spans.length < 2) continue;
                const letra = letraEl(spans[0]);
                if (!LETRAS.has(letra) || alts[letra]) continue;
                const html = spans[1].innerHTML.trim();
                if (!html) continue;
                alts[letra] = html;
                if (isVerde(spans[0])) gabarito = letra;
            }

            // ── Estratégia 2: qualquer span/div cujo texto direto seja A-E ──
            if (Object.keys(alts).length === 0) {
                for (const el of container.querySelectorAll('span, div')) {
                    const letra = letraEl(el);
                    if (!LETRAS.has(letra) || alts[letra]) continue;
                    const next = el.nextElementSibling;
                    if (!next) continue;
                    const html = next.innerHTML.trim();
                    if (!html) continue;
                    alts[letra] = html;
                    if (isVerde(el)) gabarito = letra;
                }
            }

            // ── Estratégia 3: fallback texto puro "A) ..." ──────────────────
            if (Object.keys(alts).length === 0) {
                const texto = container.innerText || '';
                const re = /\\b([A-E])\\)\\s*([^\\n]+)/g;
                let m;
                while ((m = re.exec(texto)) !== null) {
                    if (!alts[m[1]]) alts[m[1]] = m[2].trim();
                }
            }

            // ── Gabarito fallback: busca span verde com letra ────────────────
            if (!gabarito) {
                for (const el of container.querySelectorAll('span, div')) {
                    const letra = letraEl(el);
                    if (LETRAS.has(letra) && alts[letra] && isVerde(el)) {
                        gabarito = letra;
                        break;
                    }
                }
            }

            return { alts, gabarito };
        }
    """)

    return resultado.get('alts', {}), resultado.get('gabarito')


def extrair_alternativas_de_html(page, html):
    """
    Faz parse de alternativas/gabarito a partir de um HTML já capturado (ex.: resolucao_html).
    Usa innerHTML para preservar MathJax, imagens e formatação.
    """
    if not html:
        return {}, None

    resultado = page.evaluate("""
        (htmlStr) => {
            const host = document.createElement('div');
            host.innerHTML = htmlStr || '';
            const container = host;
            if (!container) return { alts: {}, gabarito: null };

            const alts = {};
            let gabarito = null;
            const LETRAS = new Set(['A','B','C','D','E']);

            function isVerde(el) {
                if (!el) return false;
                const cls = (el.className || '').toLowerCase();
                if (cls.includes('emerald') || cls.includes('green') || cls.includes('success')) return true;
                const style = (el.getAttribute('style') || '').toLowerCase();
                return style.includes('rgb(16') || style.includes('rgb(34') || style.includes('green');
            }

            // Letra limpa: lê texto direto do nó, ignora filhos MathJax
            function letraEl(el) {
                if (!el) return '';
                const direto = Array.from(el.childNodes)
                    .filter(n => n.nodeType === 3)
                    .map(n => n.textContent.trim())
                    .join('');
                if (direto) return direto;
                return (el.innerText || '').trim().replace(/\\s+/g, ' ');
            }

            // ── Estratégia 1: div.flex > span(letra) + span(conteúdo) — innerHTML ──
            const rows = container.querySelectorAll('div.flex, div[class*="flex"]');
            for (const row of rows) {
                const spans = row.querySelectorAll(':scope > span');
                if (spans.length < 2) continue;
                const letra = letraEl(spans[0]);
                if (!LETRAS.has(letra) || alts[letra]) continue;
                const html = spans[1].innerHTML.trim();
                if (!html) continue;
                alts[letra] = html;
                if (isVerde(spans[0])) gabarito = letra;
            }

            // ── Estratégia 2: qualquer span/div cujo texto direto seja A-E ──
            if (Object.keys(alts).length === 0) {
                for (const el of container.querySelectorAll('span, div')) {
                    const letra = letraEl(el);
                    if (!LETRAS.has(letra) || alts[letra]) continue;
                    const next = el.nextElementSibling;
                    if (!next) continue;
                    const html = next.innerHTML.trim();
                    if (!html) continue;
                    alts[letra] = html;
                    if (isVerde(el)) gabarito = letra;
                }
            }

            // ── Estratégia 3: fallback texto puro "A) ..." ──
            if (Object.keys(alts).length === 0) {
                const texto = container.innerText || '';
                const re = /\\b([A-E])\\)\\s*([^\\n]+)/g;
                let m;
                while ((m = re.exec(texto)) !== null) {
                    if (!alts[m[1]]) alts[m[1]] = m[2].trim();
                }
            }

            return { alts, gabarito };
        }
    """, html)

    return resultado.get('alts', {}), resultado.get('gabarito')


# ── EXTRAIR RESOLUÇÃO ────────────────────────────────────
def extrair_resolucao(page):
    """
    Modal de resolução (dissertativa). Pode ser SweetAlert2 ou MUI.
    Retorna o innerHTML do conteúdo para preservar formatação.
    """
    # Tenta SweetAlert2 primeiro
    try:
        page.wait_for_selector('.swal2-html-container', timeout=3000)
        html = page.evaluate("() => document.querySelector('.swal2-html-container').innerHTML")
        if html:
            print(f"    [res] SweetAlert2 OK ({len(html)} chars)")
            return html
    except:
        pass

    # Tenta MUI Dialog
    try:
        page.wait_for_selector('[class*="MuiDialogContent"]', timeout=3000)
        html = page.evaluate("() => document.querySelector('[class*=\"MuiDialogContent\"]').innerHTML")
        if html:
            print(f"    [res] MUI OK ({len(html)} chars)")
            return html
    except:
        pass

    return ""


# ── EXTRAIR BNCC ──────────────────────────────────────────
def extrair_bncc(page):
    """
    Modal MUI aberto. Tenta múltiplas estratégias para extrair {materia, codigo, habilidade}.
    """
    try:
        page.wait_for_selector('[class*="MuiDialogContent"], [class*="MuiDialog-paper"]', timeout=8000)
    except:
        return []

    # Expande todos os accordions fechados
    page.evaluate("""
        () => {
            document.querySelectorAll(
                '[class*="MuiAccordionSummary-root"], [class*="MuiAccordion-root"] [role="button"]'
            ).forEach(h => {
                if (h.getAttribute('aria-expanded') !== 'true') h.click();
            });
        }
    """)
    time.sleep(espera(0.6))

    return page.evaluate("""
        () => {
            // Raiz: tenta MuiDialogContent, senão o dialog inteiro
            const modal =
                document.querySelector('[class*="MuiDialogContent"]') ||
                document.querySelector('[class*="MuiDialog-paper"]');
            if (!modal) return [];

            const dados = [];

            // ── Estratégia 1: Accordion por matéria → tabela ──────────
            const accordions = modal.querySelectorAll('[class*="MuiAccordion-root"]');
            if (accordions.length > 0) {
                for (const acc of accordions) {
                    // Nome da matéria: primeiro p ou h dentro do summary
                    const headerEl = acc.querySelector(
                        '[class*="MuiAccordionSummary"] p, [class*="MuiAccordionSummary"] h6, ' +
                        '[class*="MuiAccordionSummary"] span, [class*="AccordionSummary"] *'
                    );
                    const materia = headerEl ? headerEl.innerText.trim() : '';

                    // Linhas da tabela dentro deste accordion
                    for (const tr of acc.querySelectorAll('tbody tr, tr')) {
                        const tds = tr.querySelectorAll('td');
                        if (tds.length >= 2) {
                            // Texto pode estar em <p> dentro do <td> ou direto
                            const t = i => (tds[i].querySelector('p') || tds[i]).innerText.trim();
                            const codigo = t(0);
                            const habilidade = t(1);
                            if (codigo) dados.push({ materia, codigo, habilidade });
                        }
                    }
                }
                if (dados.length > 0) return dados;
            }

            // ── Estratégia 2: tabela plana sem accordion ──────────────
            for (const tr of modal.querySelectorAll('tbody tr, tr')) {
                const tds = tr.querySelectorAll('td');
                if (tds.length >= 2) {
                    const t = i => (tds[i].querySelector('p') || tds[i]).innerText.trim();
                    const codigo = t(0);
                    const habilidade = t(1);
                    const materia = tds.length >= 3 ? t(2) : '';
                    if (codigo && /^[A-Z]{2}\\d/.test(codigo)) {
                        dados.push({ materia, codigo, habilidade });
                    }
                }
            }
            if (dados.length > 0) return dados;

            // ── Estratégia 3: parse de texto — padrão "EF01MA01" ─────
            const texto = modal.innerText;
            const re = /([A-Z]{2}\\d{2}[A-Z]{2}\\d{2,3})\\s+([^\\n]{10,})/g;
            let m, materia = '';
            for (const line of texto.split('\\n')) {
                const clean = line.trim();
                // Detecta cabeçalho de matéria (linha curta sem código BNCC)
                if (clean && clean.length < 60 && !/[A-Z]{2}\\d{2}/.test(clean)) {
                    materia = clean;
                }
                const match = re.exec(texto);
                if (match) dados.push({ materia, codigo: match[1], habilidade: match[2].trim() });
            }
            return dados;
        }
    """)


# ── EXTRAIR CARD ──────────────────────────────────────────
def extrair_card(card, page):
    q = {
        "id": "", "tipo": "",
        "origem": {"titulo": "", "ano": "", "numero": "", "extras": [], "raw": ""},
        "dificuldade": "", "materia": "", "topicos": [], "tags": [],
        "enunciado_html": "", "alternativas": {},
        "gabarito": None, "resolucao_html": "", "textos_html": "", "bncc": []
    }

    dados = card.evaluate("""
        el => {
            const html = s => { const n = el.querySelector(s); return n ? n.innerHTML : ''; };

            // ── ID ──
            const idEl = el.querySelector('[class*="_id"] span, [class*="id__"] span');

            // ── Tipo ──
            const tipoEl = el.querySelector('[class*="_tipoquestao"] span, [class*="tipoquestao__"] span, [class*="_tipo"] span');

            // ── Origem: extrai cada span separado ──
            const origemEl = el.querySelector('[class*="_origem"], [class*="origem__"]');
            let origem = { titulo: '', ano: '', numero: '', extras: [], raw: '' };
            if (origemEl) {
                const spans = Array.from(origemEl.querySelectorAll('span'));
                const textos = spans.map(s => s.innerText.trim()).filter(Boolean);
                origem.raw = textos.join(' · ');

                for (const s of spans) {
                    const t = s.innerText.trim();
                    if (!t) continue;
                    if (s.className && s.className.includes('titulo')) {
                        origem.titulo = t;
                    } else if (s.className && s.className.includes('numero')) {
                        origem.numero = t;
                    } else if (/^\\d{4}$/.test(t)) {
                        origem.ano = t;
                    } else if (!origem.titulo) {
                        origem.titulo = t; // primeiro span sem classe = título
                    } else {
                        origem.extras.push(t); // Fase, Semestre, Dia, etc.
                    }
                }
            }

            // ── Subheader: dificuldade + matéria + tópicos ──
            const subEl = el.querySelector('[class*="_subheader"], [class*="subheader__"]');
            let dificuldade = '', materia = '', topicos = [], tags = [];
            if (subEl) {
                const spans = Array.from(subEl.querySelectorAll('span'));
                for (const s of spans) {
                    const t = s.innerText.trim();
                    if (!t) continue;
                    tags.push(t);
                    if (s.className && s.className.includes('dificuldade')) {
                        dificuldade = t;
                    } else if (!materia) {
                        materia = t; // primeiro span não-dificuldade = matéria
                    } else {
                        topicos.push(t); // demais = tópicos/subtópicos
                    }
                }
            }

            return {
                id:        idEl   ? idEl.innerText.trim()   : '',
                tipo:      tipoEl ? tipoEl.innerText.trim()  : '',
                origem,
                dificuldade,
                materia,
                topicos,
                tags,
                enunciado: html('[class*="_enunciado"], [class*="enunciado__"]'),
            };
        }
    """)

    q["id"]          = dados.get("id", "")
    q["tipo"]        = dados.get("tipo", "")
    q["origem"]      = dados.get("origem", {"titulo":"","ano":"","numero":"","extras":[],"raw":""})
    q["dificuldade"] = dados.get("dificuldade", "")
    q["materia"]     = dados.get("materia", "")
    q["topicos"]     = dados.get("topicos", [])
    q["tags"]        = dados.get("tags", [])

    # Converte imagens do enunciado para base64
    enunciado_raw = dados.get("enunciado", "")
    q["enunciado_html"] = imagens_para_base64(page, enunciado_raw)

    # Limpa modais anteriores
    page.evaluate("""
        () => {
            document.querySelectorAll('[class*="MuiDialog-root"]').forEach(d => d.remove());
            document.querySelectorAll('.swal2-container').forEach(d => d.remove());
        }
    """)

    # ── Detecta dinamicamente quais botões existem no footer ──
    botoes = card.evaluate("""
        el => {
            const footer = el.querySelector('[class*="listas-view_footer"], [class*="_footer"], [class*="footer__"]');
            const result = { alternativas: false, resolucao: false, textos: false, bncc: false };
            if (footer) {
                for (const s of footer.querySelectorAll('span, button, a')) {
                    const cls = s.className || '';
                    const txt = (s.innerText || '').trim().toLowerCase();
                    if (cls.includes('alternativas') || txt === 'alternativas') result.alternativas = true;
                    if (cls.includes('resolucao')    || txt === 'resolução')    result.resolucao   = true;
                    // textos vinculados: tem classe 'textos' MAS não é o botão BNCC (texto ≠ 'bncc')
                    if (cls.includes('textos') && txt !== 'bncc')               result.textos      = true;
                    // bncc: texto é 'bncc' OU classe contém 'bncc'
                    if (txt === 'bncc' || cls.includes('bncc'))                 result.bncc        = true;
                }
            }
            return result;
        }
    """)

    def clicar_e_esperar(locator_fn, delay=1.0, retries=2):
        """Tenta clicar com retry — dá tempo ao React estabilizar entre modais."""
        for tentativa in range(retries):
            try:
                locator_fn()
                time.sleep(espera(delay))
                return True
            except Exception as e:
                if tentativa == retries - 1:
                    raise
                time.sleep(espera(0.5))
        return False

    def abrir_modal_mui(locator_fn, delay=1.5):
        """Abre modal MUI e retorna o HTML do conteúdo."""
        locator_fn()
        time.sleep(espera(delay))
        return page.evaluate("""
            () => {
                const mu = document.querySelector('[class*="MuiDialogContent"]');
                if (mu) return mu.innerHTML;
                const sw = document.querySelector('.swal2-html-container');
                if (sw) return sw.innerHTML;
                return '';
            }
        """)

    # Log do que foi detectado (só imprime se tiver algo)
    ativos = [k for k, v in botoes.items() if v]
    if ativos:
        print(f"    botoes: {ativos}")

    # ── ORDEM: MUI dialogs PRIMEIRO (resolução, textos, BNCC)
    # depois SweetAlert2 (alternativas) — evita resíduos do SweetAlert2
    # bloquearem os MUI dialogs subsequentes ──────────────────────────

    def clicar_no_footer(texto_label, classe_keyword):
        """
        Clica no botão do footer por classe OU por texto.
        Usa element.click() via evaluate() — dispara eventos React corretamente.
        Retorna True se clicou.
        """
        # Remove modais zumbis da página antes de clicar
        page.evaluate("() => { document.querySelectorAll('[class*=\"MuiDialog-root\"], .swal2-container').forEach(d => d.remove()); }")
        time.sleep(espera(0.25))
        # 1ª tentativa: Playwright .click() real — move cursor + mousedown/up/click via CDP
        for footer_sel in [
            '[class*="listas-view_footer"]',
            '[class*="listas-view_options"]',
        ]:
            try:
                loc = card.locator(f'{footer_sel} [class*="{classe_keyword}"]')
                if loc.count() > 0:
                    loc.first.click(timeout=3000)
                    return True
            except Exception:
                pass

        # 2ª tentativa: texto exato via Playwright .click()
        try:
            loc = card.locator('[class*="listas-view_footer"] span, [class*="listas-view_options"] span')
            count = loc.count()
            for idx in range(count):
                try:
                    txt = loc.nth(idx).inner_text(timeout=500)
                    if txt.strip().lower() == texto_label.lower():
                        loc.nth(idx).click(timeout=3000)
                        return True
                except Exception:
                    pass
        except Exception:
            pass

        # 3ª tentativa (fallback): JS element.click() via evaluate
        return card.evaluate(f"""
            el => {{
                const footer = el.querySelector('[class*="listas-view_footer"], [class*="listas-view_options"]');
                if (!footer) return false;
                const porClasse = footer.querySelector('[class*="{classe_keyword}"]');
                if (porClasse) {{ porClasse.click(); return true; }}
                const textoAlvo = '{texto_label}'.toLowerCase();
                for (const s of footer.querySelectorAll('span, button, a')) {{
                    if ((s.innerText || '').trim().toLowerCase() === textoAlvo) {{
                        s.click(); return true;
                    }}
                }}
                return false;
            }}
        """)

    # ── Resolução ────────────────────────────────────────
    if botoes.get('resolucao'):
        try:
            clicou = clicar_no_footer('resolução', 'resolucao')
            if clicou:
                # Aguarda o modal MUI abrir e o conteúdo carregar
                try:
                    page.wait_for_selector('[class*="MuiDialogContent"], .swal2-html-container', timeout=4000)
                except Exception:
                    pass
                try:
                    page.wait_for_function("""
                        () => {
                            const mu = document.querySelector('[class*="MuiDialogContent"]');
                            const sw = document.querySelector('.swal2-html-container');
                            const el = (mu && mu.offsetParent !== null ? mu : sw) || mu || sw;
                            if (!el) return false;
                            const text = (el.innerText || '').trim();
                            return text.length > 5 && !text.toLowerCase().includes('carregando');
                        }
                    """, timeout=8000)
                except Exception:
                    pass
                html = page.evaluate("""
                    () => {
                        const mu = document.querySelector('[class*="MuiDialogContent"]');
                        if (mu) return mu.innerHTML;
                        const sw = document.querySelector('.swal2-html-container');
                        if (sw) return sw.innerHTML;
                        return '';
                    }
                """)
                if html:
                    q["resolucao_html"] = html
                    print(f"    [res] OK ({len(html)} chars)")
                    # Fallback: em vários cards de múltipla escolha, as alternativas
                    # vêm dentro do modal de resolução (sem botão "Alternativas").
                    if _tipo_multipla(q.get("tipo")) and not q.get("alternativas"):
                        alts_res, gabarito_res = extrair_alternativas_de_html(page, html)
                        if alts_res:
                            q["alternativas"] = alts_res
                            if gabarito_res:
                                q["gabarito"] = gabarito_res
                            print(f"    [alt<-res] OK ({len(alts_res)} alternativas, gabarito={q.get('gabarito')})")
                else:
                    print(f"    [res] clicou mas modal vazio")
                    q["extracao_tentada"] = True   # sem conteúdo → não retenta
            else:
                print(f"    [res] botão não encontrado no footer")
        except Exception as e:
            print(f"    [res] {e}")
        finally:
            fechar_modal(page)
            time.sleep(espera(0.4))

    # ── Textos vinculados ────────────────────────────────
    if EXTRAIR_TEXTOS_VINCULADOS and botoes.get('textos'):
        try:
            clicou = clicar_no_footer('textos', 'textos')
            if clicou:
                try:
                    page.wait_for_selector('[class*="MuiDialogContent"], .swal2-html-container', timeout=6000)
                except Exception:
                    pass
                time.sleep(espera(0.35))
                html = page.evaluate("""
                    () => {
                        const mu = document.querySelector('[class*="MuiDialogContent"]');
                        if (mu) return mu.innerHTML;
                        const sw = document.querySelector('.swal2-html-container');
                        if (sw) return sw.innerHTML;
                        return '';
                    }
                """)
                if html:
                    q["textos_html"] = imagens_para_base64(page, html)
                    print(f"    [txt] OK ({len(html)} chars)")
                else:
                    print(f"    [txt] clicou mas modal vazio")
            else:
                print(f"    [txt] botão não encontrado no footer")
        except Exception as e:
            print(f"    [txt] {e}")
        finally:
            fechar_modal(page)
            time.sleep(espera(0.4))

    # ── BNCC ─────────────────────────────────────────────
    if EXTRAIR_BNCC and botoes.get('bncc'):
        try:
            page.evaluate("() => { document.querySelectorAll('[class*=\"MuiDialog-root\"], .swal2-container').forEach(d => d.remove()); }")
            time.sleep(espera(0.25))
            clicou_bncc = card.evaluate("""
                el => {
                    for (const s of el.querySelectorAll('span, button, a')) {
                        if ((s.innerText || '').trim() === 'BNCC') { s.click(); return true; }
                    }
                    return false;
                }
            """)
            if clicou_bncc:
                try:
                    page.wait_for_selector('[class*="MuiDialogContent"], [class*="MuiDialog-paper"]', timeout=6000)
                except Exception:
                    pass
                time.sleep(espera(0.45))
                q["bncc"] = extrair_bncc(page)
        except Exception as e:
            print(f"    [bncc] {e}")
        finally:
            fechar_modal(page)
            time.sleep(espera(0.4))

    # ── Alternativas (SweetAlert2 — ÚLTIMO para não interferir MUI) ──
    if botoes.get('alternativas'):
        try:
            clicou = clicar_no_footer('alternativas', 'alternativas')
            if not clicou:
                # Fallback: locator Playwright direto (sem escopo de footer)
                card.locator('[class*="listas-view_footer"] [class*="alternativas"],'
                             '[class*="listas-view_options"] [class*="alternativas"]').first.dispatch_event("click")
                clicou = True
            if clicou:
                try:
                    page.wait_for_selector('.swal2-html-container, [class*="MuiDialogContent"]', timeout=6000)
                except Exception:
                    pass
                time.sleep(espera(0.35))
                alts, gabarito = extrair_alternativas(page)
                if alts:
                    q["alternativas"] = alts
                    if gabarito:
                        q["gabarito"] = gabarito
                    print(f"    [alt] OK ({len(alts)} alternativas, gabarito={gabarito})")
                else:
                    print(f"    [alt] modal abriu mas sem alternativas (provável imagem/MathJax)")
                    q["extracao_tentada"] = True   # sem conteúdo extraível → não retenta
            else:
                print(f"    [alt] botão não encontrado")
        except Exception as e:
            print(f"    [alt] {e}")
        finally:
            fechar_modal(page)
            time.sleep(espera(0.4))

    # Se não tem alternativas, resolução, E não tem nenhum botão que possa gerar conteúdo,
    # marca como tentada para não reprocessar indefinidamente.
    if (not q.get("alternativas") and not q.get("resolucao_html")
            and not botoes.get("alternativas") and not botoes.get("resolucao")):
        q["extracao_tentada"] = True

    return q


# ── APLICAR FILTRO GENÉRICO ───────────────────────────────
def aplicar_filtro(page, nome, valores):
    """
    Abre o dropdown identificado por aria-description=nome,
    seleciona todos (True) ou valores específicos (lista),
    e fecha.
    """
    try:
        # O combobox fica dentro do elemento com aria-description=nome
        combobox = page.locator(f'[aria-description="{nome}"] [role="combobox"]')
        combobox.click(timeout=5000)
        time.sleep(1.2)

        if valores is True:
            page.locator('button:has-text("Selecionar todos")').first.click(timeout=4000)
            time.sleep(0.4)
        else:
            for valor in valores:
                page.locator(f'[role="option"]:has-text("{valor}")').click(timeout=3000)
                time.sleep(0.2)

        page.keyboard.press("Escape")
        time.sleep(0.5)
        print(f"  ✓ {nome}: {'todos' if valores is True else valores}")
    except Exception as e:
        print(f"  ✗ {nome}: {e}")
        page.keyboard.press("Escape")


# ── MAIN ─────────────────────────────────────────────────
def run(playwright):
    print("=" * 50)
    print("  ROBO AVALIA FÁCIL")
    print("=" * 50)
    if MATERIA_ALVO:
        print(f"[MODO] Matéria alvo: {MATERIA_ALVO}")
    print(f"[MODO] BNCC: {'ON' if EXTRAIR_BNCC else 'OFF'} | Chave única: {'id+matéria' if UNICO_POR_ID_E_MATERIA else 'id'}")

    browser = playwright.chromium.launch(headless=False)
    ctx     = browser.new_context()
    page    = ctx.new_page()
    questoes = carregar()
    ids_salvos = {_chave_questao(q) for q in questoes if _chave_questao(q)}
    pagina = 1
    indice_inicial = 0
    checkpoint_pre = carregar_checkpoint()
    if checkpoint_pre:
        print(
            f"\n[CHECKPOINT] Arquivo '{CHECKPOINT}' encontrado — ao chegar na extração, "
            f"retoma da pág. {checkpoint_pre['pagina']}, índice {checkpoint_pre['indice_proximo'] + 1}º card "
            f"(pausado em {checkpoint_pre['pausado_em']}).\n"
            f"  Para começar do zero, apague '{CHECKPOINT}' antes de rodar.\n"
        )

    try:
        # ── 1. LOGIN ──────────────────────────────────────
        print("\n[1] Login...")
        page.goto(
            "https://portaisetapa.b2clogin.com/portaisetapa.onmicrosoft.com"
            "/B2C_1_SignUpSignIn/oauth2/v2.0/authorize"
            "?client_id=0d34869e-c9d4-42de-9f06-23a5f09e9336"
            "&response_type=code"
            "&redirect_uri=https://parceiro.sistemaetapa.com.br"
            "&response_mode=query&scope=openid%20offline_access"
        )
        page.wait_for_selector("input:visible", timeout=15000)
        page.locator("input:visible").first.fill(EMAIL)
        page.locator("input[type='password']").first.fill(SENHA)
        page.click("button:has-text('ENTRAR')")
        page.wait_for_url("https://parceiro.sistemaetapa.com.br/**", timeout=30000)
        time.sleep(5)
        print("  OK")

        # ── 2. NAVEGAR ATÉ AVALIA FÁCIL ──────────────────
        print("\n[2] Navegando para Avalia Fácil...")
        page.wait_for_selector(
            'xpath=//*[@id="single-spa-application:app-portal"]'
            '/div/div/aside/div/div[1]/ul/li[2]', timeout=15000
        ).click()
        time.sleep(2)

        page.wait_for_selector(
            'xpath=//*[@id="single-spa-application:app-portal"]'
            '/div/div/aside/div/div[1]/ul/ul/li[4]/button', timeout=15000
        ).click()
        time.sleep(3)

        # Captura a nova aba aberta pelo botão ACESSAR
        with ctx.expect_page() as nova_aba:
            page.wait_for_selector(
                'xpath=//*[@id="single-spa-application:app-avaliafacil"]'
                '/div[1]/div/div[1]/div[3]/div[2]/button', timeout=15000
            ).click()

        ap = nova_aba.value
        ap.wait_for_load_state("domcontentloaded", timeout=30000)
        time.sleep(3)
        print(f"  URL: {ap.url}")

        # ── 3. CLICAR EM EDITAR DA PRIMEIRA LISTA ────────
        print("\n[3] Abrindo lista para edição...")
        try:
            ap.goto(ATIVIDADE_URL, wait_until="domcontentloaded", timeout=30000)
            try:
                ap.wait_for_selector("button:has-text('Aplicar filtros'), [class*='cardQuestao']", timeout=15000)
            except Exception:
                pass
            time.sleep(3)
            print(f"  URL: {ap.url}")
        except Exception:
            pass

        if (
            ap.locator("button:has-text('Aplicar filtros')").count() == 0
            and ap.locator('[class*="cardQuestao"]').count() == 0
        ):
            seletor_editar = (
                '[class*="_edit"], [class*="edit__"], '
                'button:has-text("Editar"), a:has-text("Editar"), span:has-text("Editar")'
            )
            ap.wait_for_selector(seletor_editar, timeout=20000)
            ap.locator(seletor_editar).first.dispatch_event("click")
            time.sleep(4)
            print(f"  URL: {ap.url}")

        # ── 4. FILTROS ────────────────────────────────────
        print("\n[4] Aplicando filtros...")
        for nome_filtro, valores in FILTROS.items():
            if not valores:
                continue
            aplicar_filtro(ap, nome_filtro, valores)

        print("  Clicando em Aplicar filtros...")
        ap.locator("button:has-text('Aplicar filtros')").click(timeout=8000)
        time.sleep(espera(1.2))

        # ── 5. EXTRAÇÃO COM PAGINAÇÃO ─────────────────────
        limite = PAGINAS_LIMITE  # None = sem limite
        meta_q = MAX_QUESTOES
        print(
            f"\n[5] Extraindo questões — páginas: {limite if limite else 'todas'} | "
            f"meta no arquivo: {meta_q if meta_q else 'sem limite'} questões completas "
            f"(já carregadas: {len(questoes)})...\n"
        )
        total = None
        cp = carregar_checkpoint()
        if cp and cp['pagina'] > 1:
            pagina_alvo = cp['pagina']
            indice_inicial = cp['indice_proximo']
            print(
                f"[CHECKPOINT] Retomando: pausado em {cp['pausado_em']} | "
                f"pág. {pagina_alvo}, próximo card (1-based): {indice_inicial + 1}"
            )
            # Navega até a página do checkpoint clicando em "próxima" com espera real
            # entre cada clique (aguarda os cards recarregarem no DOM).
            passo = 10  # reporta progresso a cada 10 páginas
            for p in range(2, pagina_alvo + 1):
                if (p - 1) % passo == 0 or p == pagina_alvo:
                    print(f"  [CHECKPOINT] avançando para pág. {p}/{pagina_alvo}...")
                clicou = clicar_proxima_pagina(ap)
                if not clicou:
                    print(f"  [CHECKPOINT] Botão de próxima página não encontrado na pág. {p}. Parando avanço.")
                    pagina_alvo = p - 1
                    indice_inicial = 0
                    break
                # Aguarda os cards da nova página aparecerem antes de continuar
                try:
                    ap.wait_for_selector('[class*="cardQuestao"]', state="detached", timeout=6000)
                except Exception:
                    pass
                try:
                    ap.wait_for_selector('[class*="cardQuestao"]', timeout=8000)
                except Exception:
                    pass
                time.sleep(0.3)
            pagina = pagina_alvo
            print(f"  [CHECKPOINT] Listagem na pág. {pagina}; primeiro índice na lista: {indice_inicial + 1}.\n")

        terminou_todas_paginas = False

        while True:
            if meta_q is not None and len(questoes) >= meta_q:
                print(f"\n  Meta de questões atingida ({len(questoes)} ≥ {meta_q}). Encerrando extração.")
                break

            print(f"── Pág {pagina}{' / ' + str(total) if total else ''} ──")

            try:
                ap.wait_for_selector('[class*="cardQuestao"]', timeout=30000)
            except Exception:
                url_atual = ap.url
                print(f"  Sem cards (URL: {url_atual}). Tentando aguardar mais...")
                time.sleep(espera(1.2))
                # Verifica se a página voltou para home (sessão expirada)
                if 'sso' in url_atual or 'login' in url_atual or 'parceiro' in url_atual:
                    print("  Sessão expirou. Fim.")
                    break
                try:
                    ap.wait_for_selector('[class*="cardQuestao"]', timeout=20000)
                except Exception:
                    print("  Cards não apareceram. Fim.")
                    break

            # Detecta total de páginas (via JS — mais confiável)
            if total is None:
                try:
                    total = ap.evaluate("""
                        () => {
                            const btns = [...document.querySelectorAll('nav button, [class*="pagination"] button')];
                            const nums = btns
                                .map(b => parseInt(b.innerText.trim()))
                                .filter(n => !isNaN(n));
                            return nums.length ? Math.max(...nums) : null;
                        }
                    """)
                    if total:
                        print(f"  Total de páginas: {total}")
                except Exception:
                    pass

            card_count = ap.locator('[class*="cardQuestao"]').count()
            print(f"  {card_count} questões nesta página")

            start_i = min(indice_inicial, card_count) if card_count else 0
            indice_inicial = 0

            atingiu_meta_questoes = False
            for i in range(start_i, card_count):
                qid = ""
                try:
                    # Recria o locator a cada iteração — evita stale após re-render
                    card = ap.locator('[class*="cardQuestao"]').nth(i)
                    card.scroll_into_view_if_needed(timeout=5000)

                    qid = card.evaluate(
                        'el => { const s = el.querySelector(\'[class*="_id"] span, [class*="id__"] span\'); return s ? s.innerText.trim() : ""; }',
                        timeout=10000
                    )
                    if not qid:
                        salvar_checkpoint(pagina, i + 1)
                        continue
                    materia_card = card.evaluate(
                        """el => {
                            const subEl = el.querySelector('[class*="_subheader"], [class*="subheader__"]');
                            if (!subEl) return '';
                            const spans = Array.from(subEl.querySelectorAll('span')).map(s => (s.innerText || '').trim()).filter(Boolean);
                            if (spans.length === 0) return '';
                            const difs = new Set(['fácil','facil','médio','medio','difícil','dificil']);
                            for (const t of spans) {
                                if (!difs.has((t || '').toLowerCase())) return t;
                            }
                            return '';
                        }"""
                    )
                    chave_card = f"{qid}__{(materia_card or '').strip().upper()}" if UNICO_POR_ID_E_MATERIA else qid

                    if chave_card in ids_salvos:
                        sufixo = f" ({materia_card})" if materia_card else ""
                        print(f"  [{i+1}] #{qid}{sufixo} já salva, pulando.")
                        salvar_checkpoint(pagina, i + 1, qid)
                        continue

                    print(f"  [{i+1}] #{qid}...")
                    q = extrair_card(card, ap)
                    questoes.append(q)
                    ids_salvos.add(_chave_questao(q))
                    salvar_checkpoint(pagina, i + 1, qid)

                    if len(questoes) % 10 == 0:
                        salvar(questoes)
                        print(f"  >> {len(questoes)} salvas")

                    if meta_q is not None and len(questoes) >= meta_q:
                        print(f"\n  Meta de {meta_q} questões no arquivo atingida ({len(questoes)} no total).")
                        salvar(questoes)
                        atingiu_meta_questoes = True
                        break

                except KeyboardInterrupt:
                    salvar_checkpoint(pagina, i, qid)
                    salvar(questoes)
                    print(f"\n[INTERRUPÇÃO] Checkpoint salvo: pág. {pagina}, card índice {i + 1} (reprocessa este ao voltar).")
                    raise
                except Exception as e:
                    print(f"  [{i+1}] erro: {e}")

            salvar(questoes)
            print(f"  Pág {pagina} OK. Total acumulado: {len(questoes)}")

            if atingiu_meta_questoes:
                break

            # Para se atingiu o limite de páginas do teste
            if limite and pagina >= limite:
                print(f"\n  Limite de {limite} páginas atingido.")
                salvar_checkpoint(pagina + 1, 0)
                break

            # Para se chegou na última página
            if total and pagina >= total:
                print("\n  Última página atingida.")
                terminou_todas_paginas = True
                break

            # ── Navega para próxima página ──
            clicou = clicar_proxima_pagina(ap)

            if not clicou:
                print("  Botão de próxima página não encontrado. Encerrando para reiniciar.")
                salvar_checkpoint(pagina + 1, 0)
                break

            salvar_checkpoint(pagina + 1, 0)
            pagina += 1
            time.sleep(espera(1.2))
            # Confirma que a página mudou (cards antigos devem ter sumido)
            try:
                ap.wait_for_selector('[class*="cardQuestao"]', state="detached", timeout=8000)
            except Exception:
                pass  # OK se já recarregou
            print(f"  → navegando pág {pagina} (URL: {ap.url})")

        if terminou_todas_paginas:
            apagar_checkpoint()
            print("\n  Checkpoint removido (extração completa).")

        print(f"\n{'='*50}")
        print(f"  CONCLUÍDO! {len(questoes)} questões em '{SAIDA}'")
        print(f"{'='*50}")
        time.sleep(10)

    except KeyboardInterrupt:
        print("\n[INTERRUPÇÃO] Encerrado pelo usuário.")
        try:
            salvar(questoes)
        except Exception:
            pass
        time.sleep(3)

    except Exception as e:
        print(f"\n[ERRO] {e}")
        import traceback; traceback.print_exc()
        salvar(questoes)
        try:
            salvar_checkpoint(pagina, indice_inicial)
        except Exception:
            pass
        time.sleep(30)

    finally:
        ctx.close()
        browser.close()


if __name__ == "__main__":
    with sync_playwright() as pw:
        run(pw)
