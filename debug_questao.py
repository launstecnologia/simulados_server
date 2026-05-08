"""
Debug focado na questão #474654 — despeja HTML dos modais de alternativas, resolução e BNCC.
"""
from playwright.sync_api import sync_playwright
import time, json

EMAIL = "matheustozzo@yahoo.com.br"
SENHA = "Mat09074170#"
QUESTAO_ID = "474610"

def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    ctx  = browser.new_context()
    page = ctx.new_page()

    # ── Login ──────────────────────────────────────────────
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
    print("Login OK")

    # ── Navegar até Avalia Fácil ───────────────────────────
    page.wait_for_selector('xpath=//*[@id="single-spa-application:app-portal"]/div/div/aside/div/div[1]/ul/li[2]', timeout=15000).click()
    time.sleep(2)
    page.wait_for_selector('xpath=//*[@id="single-spa-application:app-portal"]/div/div/aside/div/div[1]/ul/ul/li[4]/button', timeout=15000).click()
    time.sleep(3)

    with ctx.expect_page() as nova_aba:
        page.wait_for_selector('xpath=//*[@id="single-spa-application:app-avaliafacil"]/div[1]/div/div[1]/div[3]/div[2]/button', timeout=15000).click()

    ap = nova_aba.value
    ap.wait_for_load_state("domcontentloaded", timeout=30000)
    time.sleep(3)

    # ── Abrir lista ────────────────────────────────────────
    ap.wait_for_selector('[class*="_edit"], [class*="edit__"]', timeout=20000)
    ap.locator('[class*="_edit"], [class*="edit__"]').first.dispatch_event("click")
    time.sleep(4)

    # Aplica Matérias: todas
    try:
        combobox = ap.locator('[aria-description="Matérias"] [role="combobox"]')
        combobox.click(timeout=5000)
        time.sleep(1.2)
        ap.locator('button:has-text("Selecionar todos")').first.click(timeout=4000)
        time.sleep(0.4)
        ap.keyboard.press("Escape")
        time.sleep(0.5)
        ap.locator("button:has-text('Aplicar filtros')").click(timeout=8000)
        time.sleep(5)
        print("Filtros aplicados")
    except Exception as e:
        print(f"Filtro: {e}")

    # ── Encontrar questão #474654 ──────────────────────────
    card = None
    for pagina in range(1, 10):
        ap.wait_for_selector('[class*="cardQuestao"]', timeout=15000)
        count = ap.locator('[class*="cardQuestao"]').count()

        for i in range(count):
            c = ap.locator('[class*="cardQuestao"]').nth(i)
            qid = c.evaluate('el => { const s = el.querySelector(\'[class*="_id"] span\'); return s ? s.innerText.trim() : ""; }')
            if qid == QUESTAO_ID:
                card = c
                print(f"Questão #{QUESTAO_ID} encontrada na página {pagina}, posição {i+1}")
                break
        if card:
            break

        # Próxima página
        clicou = ap.evaluate("""
            () => {
                const navBtns = [...document.querySelectorAll('nav button, [class*="pagination"] button')];
                const proxBtn = navBtns.find(b => (b.innerText.trim() === '>' || b.innerText.trim() === '›') && !b.disabled);
                if (proxBtn) { proxBtn.click(); return true; }
                return false;
            }
        """)
        if not clicou:
            print("Sem mais páginas")
            break
        time.sleep(3)

    if not card:
        print(f"Questão #{QUESTAO_ID} não encontrada!")
        time.sleep(10)
        return

    card.scroll_into_view_if_needed()
    time.sleep(0.5)

    # ── Dump do card HTML ──────────────────────────────────
    card_html = card.inner_html()
    with open("debug_card_474654.html", "w") as f:
        f.write(card_html)
    print(f"Card HTML salvo ({len(card_html)} chars)")

    # ── Lista todos os botões/spans no footer ──────────────
    footer_els = card.evaluate("""
        el => {
            const footer = el.querySelector('[class*="footer"], [class*="_options"]');
            if (!footer) return 'sem footer';
            const els = footer.querySelectorAll('span, button, a');
            return Array.from(els).map(e => ({
                tag: e.tagName,
                cls: e.className,
                txt: e.innerText.trim()
            }));
        }
    """)
    print("\nElementos no footer:")
    print(json.dumps(footer_els, ensure_ascii=False, indent=2))

    def limpa_modais():
        ap.evaluate("""
            () => {
                document.querySelectorAll('[class*="MuiDialog-root"]').forEach(d => d.remove());
                document.querySelectorAll('.swal2-container').forEach(d => d.remove());
            }
        """)
        time.sleep(0.3)

    def fecha_modal():
        ap.evaluate("""
            () => {
                const swal = document.querySelector('.swal2-confirm');
                if (swal) { swal.click(); return; }
                for (const btn of document.querySelectorAll('button')) {
                    if (btn.innerText.trim() === 'Fechar') { btn.click(); return; }
                }
                document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape',bubbles:true}));
            }
        """)
        time.sleep(0.8)

    # ── Testa: Alternativas ────────────────────────────────
    print("\n=== TESTANDO ALTERNATIVAS ===")
    limpa_modais()
    try:
        card.locator('[class*="alternativas"]').first.dispatch_event("click")
        time.sleep(1.5)
        html_alts = ap.evaluate("""
            () => {
                const sw = document.querySelector('.swal2-html-container');
                if (sw) return {tipo: 'swal2', html: sw.innerHTML};
                const mu = document.querySelector('[class*="MuiDialogContent"]');
                if (mu) return {tipo: 'mui', html: mu.innerHTML};
                return {tipo: 'nenhum', html: ''};
            }
        """)
        print(f"Modal tipo: {html_alts['tipo']}")
        print(f"HTML ({len(html_alts['html'])} chars):\n{html_alts['html'][:500]}")
        with open("debug_alternativas_474654.html", "w") as f:
            f.write(html_alts['html'])
    except Exception as e:
        print(f"Erro: {e}")
    fecha_modal()

    # ── Testa: Resolução ──────────────────────────────────
    print("\n=== TESTANDO RESOLUÇÃO ===")
    limpa_modais()
    try:
        card.locator('[class*="listas-view_footer"] [class*="resolucao"]').first.dispatch_event("click")
        time.sleep(1.5)
        html_res = ap.evaluate("""
            () => {
                const sw = document.querySelector('.swal2-html-container');
                if (sw) return {tipo: 'swal2', html: sw.innerHTML};
                const mu = document.querySelector('[class*="MuiDialogContent"]');
                if (mu) return {tipo: 'mui', html: mu.innerHTML};
                return {tipo: 'nenhum', html: ''};
            }
        """)
        print(f"Modal tipo: {html_res['tipo']}")
        print(f"HTML ({len(html_res['html'])} chars):\n{html_res['html'][:300]}")
        with open("debug_resolucao_474654.html", "w") as f:
            f.write(html_res['html'])
    except Exception as e:
        print(f"Erro resolução: {e}")
    fecha_modal()

    # ── Testa: BNCC ───────────────────────────────────────
    print("\n=== TESTANDO BNCC ===")
    limpa_modais()
    try:
        clicou = card.evaluate("""
            el => {
                const spans = el.querySelectorAll('span, button');
                for (const s of spans) {
                    if (s.innerText.trim() === 'BNCC') { s.click(); return true; }
                }
                return false;
            }
        """)
        print(f"Clicou BNCC: {clicou}")
        time.sleep(1.5)
        html_bncc = ap.evaluate("""
            () => {
                const mu = document.querySelector('[class*="MuiDialogContent"]');
                if (mu) return {tipo: 'mui', html: mu.innerHTML};
                const sw = document.querySelector('.swal2-html-container');
                if (sw) return {tipo: 'swal2', html: sw.innerHTML};
                return {tipo: 'nenhum', html: ''};
            }
        """)
        print(f"Modal tipo: {html_bncc['tipo']}")
        print(f"HTML ({len(html_bncc['html'])} chars):\n{html_bncc['html'][:300]}")
        with open("debug_bncc_474654.html", "w") as f:
            f.write(html_bncc['html'])
    except Exception as e:
        print(f"Erro BNCC: {e}")
    fecha_modal()

    print("\n=== DONE — browser aberto por 30s para inspeção ===")
    time.sleep(30)
    ctx.close()
    browser.close()

with sync_playwright() as pw:
    run(pw)
