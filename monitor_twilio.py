import os
import json
from datetime import datetime
from dateutil.tz import gettz
from selenium import webdriver
from selenium.webdriver.common.by import By
from twilio.rest import Client

# ---------- CONFIGURAÇÃO TWILIO ----------
account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token  = os.environ.get("TWILIO_AUTH_TOKEN")
client = Client(account_sid, auth_token)
from_number = os.environ.get("TWILIO_PHONE")
to_number   = os.environ.get("MY_PHONE")

# ---------- CONFIGURAÇÃO MONITOR ----------
MONITOR_URL = "https://htmleiene.github.io/monitoramento_urls/"
TIMEZONE = "America/Sao_Paulo"
CACHE_FILE = "offline_cache.json"

# ---------- FUNÇÕES AUXILIARES ----------

def now_formatted():
    """Formata data/hora em DD-MM-YYYY HH:mm:ss (São Paulo)"""
    tz = gettz(TIMEZONE)
    return datetime.now(tz).strftime("%d-%m-%Y %H:%M:%S")

def read_cache():
    """Lê cache diário"""
    try:
        if not os.path.exists(CACHE_FILE):
            return {}
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"❌ Erro ao ler cache: {e}")
        return {}

def save_cache(cache):
    """Salva cache diário"""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
        print("🗄️ Cache atualizado.")
    except IOError as e:
        print(f"❌ Erro ao salvar cache: {e}")

def send_sms(message):
    """Envia SMS via Twilio"""
    try:
        client.messages.create(body=message, from_=from_number, to=to_number)
        print(f"📩 SMS enviado com sucesso para {to_number}")
    except Exception as e:
        print(f"❌ Falha ao enviar SMS: {e}")

# ---------- FUNÇÃO PRINCIPAL ----------

def check_offline_sites():
    print(f"\n🟢 Iniciando verificação em {now_formatted()}")
    cache = read_cache()
    today = datetime.now(gettz(TIMEZONE)).strftime("%d-%m-%Y")
    if today not in cache:
        cache[today] = []

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(MONITOR_URL)
        print("⏳ Aguardando a página carregar...")
        driver.implicitly_wait(15) # Espera implícita de até 15s

        # Raspar tabela
        rows = driver.find_elements(By.CSS_SELECTOR, "#tabelaUrls tbody tr")
        
        offline_sites = []
        # --- CORREÇÃO DO ERRO StaleElementReferenceException ---
        # Percorre a lista de elementos usando um índice para evitar o erro.
        for i in range(len(rows)):
            try:
                # O elemento é encontrado novamente a cada iteração para garantir que seja o mais atual.
                row = driver.find_elements(By.CSS_SELECTOR, "#tabelaUrls tbody tr")[i]
                
                url_element = row.find_element(By.CSS_SELECTOR, "td a.url")
                status_element = row.find_element(By.CSS_SELECTOR, "td span.status")
                
                url = url_element.text.strip()
                status = status_element.text.strip().lower()

                if "offline" in status and url not in cache[today]:
                    offline_sites.append(url)

            except Exception as e:
                print(f"⚠️ Aviso: Elemento 'stale', pulando para o próximo. Erro: {e}")
                continue
        # --- FIM DA CORREÇÃO ---
        if not offline_sites:
            print("✅ Nenhum site offline novo hoje.")
        else:
            print(f"🚨 Sites offline detectados: {', '.join(offline_sites)}")
            
            offline_list = "\n".join(offline_sites)
            message = f"🚨 ALERTA - {len(offline_sites)} site(s) offline em {now_formatted()}:\n{offline_list}"
            
            send_sms(message)
            cache[today].extend(offline_sites)
            save_cache(cache)
            
    except Exception as e:
        print(f"❌ Erro durante a verificação: {e}")
    finally:
        driver.quit()

# ---------- EXECUÇÃO DO SCRIPT ----------
if __name__ == "__main__":
    check_offline_sites()
