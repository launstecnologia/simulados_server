from playwright.sync_api import sync_playwright
import time
def run(pw):
    b = pw.chromium.launch(headless=False)
    page = b.new_page()
    page.goto("https://portaisetapa.b2clogin.com/portaisetapa.onmicrosoft.com/B2C_1_SignUpSignIn/oauth2/v2.0/authorize?client_id=0d34869e-c9d4-42de-9f06-23a5f09e9336&response_type=code&redirect_uri=https://parceiro.sistemaetapa.com.br&response_mode=query&scope=openid%20offline_access")
    page.wait_for_selector("input:visible").fill("matheustozzo@yahoo.com.br")
    page.locator("input[type='password']").fill("Mat09074170#")
    page.click("button:has-text('ENTRAR')")
    time.sleep(3)
    page.wait_for_selector('xpath=//*[@id="single-spa-application:app-portal"]/div/div/aside/div/div[1]/ul/li[2]').click()
    page.wait_for_selector('xpath=//*[@id="single-spa-application:app-portal"]/div/div/aside/div/div[1]/ul/ul/li[4]/button').click()
    time.sleep(2)
    with page.context.expect_page() as n:
        page.wait_for_selector('xpath=//*[@id="single-spa-application:app-avaliafacil"]/div[1]/div/div[1]/div[3]/div[2]/button').click()
    ap = n.value
    ap.wait_for_selector(".home_edit__OWKgG", timeout=20000)
    ap.locator(".home_edit__OWKgG").first.click()
    time.sleep(3)
    ap.locator("button:has-text('Aplicar filtros')").click(timeout=8000)
    
    ap.wait_for_selector('[class*="cardQuestao"]', timeout=30000)
    time.sleep(2)
    
    print("Encontrado card! Clicando em alternativas...")
    card = ap.locator('[class*="cardQuestao"]').first
    # procura 'Alternativas' no span
    btn = card.locator('span', has_text="Alternativas").first
    btn.click()
    time.sleep(2)
    
    html = ap.evaluate("() => document.querySelector('.swal2-html-container') ? document.querySelector('.swal2-html-container').innerHTML : document.body.innerHTML")
    with open("modal_debug.html", "w") as f:
        f.write(html)
    print("Salvo HTML!")
    b.close()
with sync_playwright() as p:
    run(p)
