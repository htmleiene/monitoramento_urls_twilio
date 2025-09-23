import os
import re
import json
from datetime import datetime
from dateutil.tz import gettz
from selenium import webdriver
from selenium.webdriver.common.by import By
from twilio.rest import Client
import time

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
        cache[today] = {"offline": [], "sent_ok": False}

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(MONITOR_URL)
        print("⏳ Aguardando a página carregar dinamicamente...")

        # Espera até terminar de verificar
        while True:
            checking_elements = driver.find_elements(By.CSS_SELECTOR, "span.status.checking")
            if not checking_elements:
                break
            print(f"⏳ Ainda verificando {len(checking_elements)} URLs...")
            time.sleep(2)

        print("✅ Todos os sites concluíram a verificação.")

        # Raspar tabela
        rows = driver.find_elements(By.CSS_SELECTOR, "#tabelaUrls tbody tr")
        offline_sites = []

        for i in range(len(rows)):
            try:
                row = driver.find_elements(By.CSS_SELECTOR, "#tabelaUrls tbody tr")[i]
                url_element = row.find_element(By.CSS_SELECTOR, "td a.url")
                status_element = row.find_element(By.CSS_SELECTOR, "td span.status")

                url = url_element.text.strip()
                status = status_element.get_attribute("class")

                if "offline" in status.lower() and url not in cache[today]["offline"]:
                    offline_sites.append(url)

            except Exception as e:
                print(f"⚠️ Aviso: Elemento 'stale', pulando. Erro: {e}")
                continue

        if not offline_sites:
            print("✅ Nenhum site offline novo hoje.")
            # Só envia 1x por dia quando tudo está ok
            if not cache[today]["sent_ok"]:
                message = f"✅ Todos os sites monitorados estão online em {now_formatted()}."
                send_sms(message)
                cache[today]["sent_ok"] = True
                save_cache(cache)
        else:
            print(f"🚨 Sites offline detectados: {', '.join(offline_sites)}")
            offline_list = "\n".join(offline_sites)
            offline_list_clean = re.sub(r'[^\x00-\x7F]+','', offline_list)
            message = f"🚨 ALERTA - {len(offline_sites)} site(s) offline em {now_formatted()}:\n{offline_list_clean}"
            send_sms(message)
            cache[today]["offline"].extend(offline_sites)
            save_cache(cache)

    except Exception as e:
        print(f"❌ Erro durante a verificação: {e}")
    finally:
        driver.quit()

# ---------- EXECUÇÃO DO SCRIPT ----------
if __name__ == "__main__":
    check_offline_sites()
