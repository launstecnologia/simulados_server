from playwright.sync_api import sync_playwright
import time, json

EMAIL = "matheustozzo@yahoo.com.br"
SENHA = "Mat09074170#"

def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    ctx = browser.new_context()
    page = ctx.new_page()

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

    page.wait_for_selector('xpath=//*[@id="single-spa-application:app-portal"]/div/div/aside/div/div[1]/ul/li[2]', timeout=15000).click()
    time.sleep(2)
    page.wait_for_selector('xpath=//*[@id="single-spa-application:app-portal"]/div/div/aside/div/div[1]/ul/ul/li[4]/button', timeout=15000).click()
    time.sleep(3)

    with ctx.expect_page() as nova_aba:
        page.wait_for_selector('xpath=//*[@id="single-spa-application:app-avaliafacil"]/div[1]/div/div[1]/div[3]/div[2]/button', timeout=15000).click()

    ap = nova_aba.value
    ap.wait_for_load_state("domcontentloaded", timeout=30000)
    time.sleep(3)

    ap.wait_for_selector(".home_edit__OWKgG", timeout=20000)
    ap.locator(".home_edit__OWKgG").first.dispatch_event("click")
    time.sleep(4)

    ap.wait_for_selector('[class*="cardQuestao"]', timeout=15000)
    time.sleep(1)

    # Dump do HTML do primeiro card
    html = ap.locator('[class*="cardQuestao"]').first.inner_html()
    with open("card_debug.html", "w") as f:
        f.write(html)
    print("HTML salvo em card_debug.html")

    # Lista todos os elementos clicáveis dentro do card
    elementos = ap.evaluate("""
        () => {
            const card = document.querySelector('[class*="cardQuestao"]');
            if (!card) return [];
            const els = card.querySelectorAll('span, button, a, [role="button"]');
            return Array.from(els).map(e => ({
                tag: e.tagName,
                cls: e.className,
                txt: e.innerText.trim().slice(0, 60)
            }));
        }
    """)
    print("\nElementos clicáveis no card:")
    for el in elementos:
        print(f"  <{el['tag']}> cls='{el['cls']}' txt='{el['txt']}'")

    time.sleep(10)
    ctx.close()
    browser.close()

with sync_playwright() as pw:
    run(pw)
