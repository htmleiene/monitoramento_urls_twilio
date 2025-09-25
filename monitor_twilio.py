import os
import re
import json
from datetime import datetime
from dateutil.tz import gettz
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
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
DEBUG = False   # coloque True para ver prints detalhados de debug

# ---------- FUNÇÕES AUXILIARES ----------
def now_formatted():
    tz = gettz(TIMEZONE)
    return datetime.now(tz).strftime("%d-%m-%Y %H:%M:%S")

def read_cache():
    try:
        if not os.path.exists(CACHE_FILE):
            return {}
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"❌ Erro ao ler cache: {e}")
        return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        if DEBUG:
            print("🗄️ Cache atualizado.")
    except IOError as e:
        print(f"❌ Erro ao salvar cache: {e}")

def send_sms(message):
    try:
        client.messages.create(body=message, from_=from_number, to=to_number)
        print(f"📩 SMS enviado com sucesso para {to_number}")
    except Exception as e:
        print(f"❌ Falha ao enviar SMS: {e}")

def normalize_text(s: str) -> str:
    if not s:
        return ""
    return re.sub(r'\s+', ' ', s).strip().lower()

# ---------- LÓGICA DE DETECÇÃO DE STATUS ----------
def detect_status_from_element(status_element):
    """
    Retorna uma string: 'online', 'offline', 'checking', ou 'unknown'
    Faz múltiplas heurísticas: class, innerText, ícone <i> interno, outerHTML.
    """
    try:
        status_text = normalize_text(status_element.text)
    except Exception:
        status_text = ""

    status_class = (status_element.get_attribute("class") or "").lower()
    status_html = (status_element.get_attribute("outerHTML") or "").lower()

    # Checar ícone interno (fa-times-circle => offline, fa-check-circle => online, fa-sync-alt => checking)
    icon_class = ""
    try:
        icon_el = status_element.find_element(By.CSS_SELECTOR, "i")
        icon_class = (icon_el.get_attribute("class") or "").lower()
    except Exception:
        icon_class = ""

    if DEBUG:
        print("    >>> status read:")
        print(f"       texto : '{status_text}'")
        print(f"       classe: '{status_class}'")
        print(f"       icone : '{icon_class}'")
        # não printar status_html inteiro sempre, só quando DEBUG verdade
        print(f"       html  : {status_html[:200]}{'...' if len(status_html)>200 else ''}")

    # heurísticas por prioridade
    # 1) classe
    if "offline" in status_class:
        return "offline"
    if "online" in status_class:
        return "online"
    if "checking" in status_class or "verificando" in status_class:
        return "checking"

    # 2) texto (pt-br e en)
    if any(x in status_text for x in ("offline", "off-line", "não verificado", "verificando", "offline)")):
        # preferir offline if explicit
        if "offline" in status_text or "off-line" in status_text:
            return "offline"
        if "verificando" in status_text or "não verificado" in status_text or "verificando..." in status_text:
            return "checking"
    if any(x in status_text for x in ("online", "on-line", "ok")):
        return "online"

    # 3) ícone
    if "fa-times-circle" in icon_class or "fa-times" in icon_class:
        return "offline"
    if "fa-check-circle" in icon_class or "fa-check" in icon_class:
        return "online"
    if "fa-sync-alt" in icon_class or "fa-spinner" in icon_class or "spin" in icon_class:
        return "checking"

    # 4) fallback: procurar palavras no outerHTML (caso use outros rótulos)
    if "offline" in status_html or "off-line" in status_html:
        return "offline"
    if "online" in status_html or "on-line" in status_html:
        return "online"
    if "verificando" in status_html or "não verificado" in status_html:
        return "checking"

    return "unknown"

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
    # opcional: reduzir logs do chrome
    options.add_argument("--log-level=3")

    try:
        driver = webdriver.Chrome(options=options)
    except WebDriverException as e:
        print(f"❌ Não foi possível iniciar o Chrome WebDriver: {e}")
        return

    try:
        driver.get(MONITOR_URL)
        print("⏳ Aguardando a página carregar dinamicamente...")

        # espera simples: enquanto houver elementos com classe 'status checking' (verificando), aguarda
        # limitamos a espera para evitar loop infinito
        max_wait = 60  # segundos
        waited = 0
        while True:
            checking_elements = driver.find_elements(By.CSS_SELECTOR, "span.status.checking, span.status.verificando, span.status:not([class*='online']):not([class*='offline']):not([class*='checking'])")
            # se não houver nenhum com 'checking' explicitamente, break
            explicit_checking = driver.find_elements(By.CSS_SELECTOR, "span.status.checking, span.status.verificando")
            if not explicit_checking:
                break
            if DEBUG:
                print(f"⏳ Ainda verificando {len(explicit_checking)} URLs... (esperado)")
            time.sleep(2)
            waited += 2
            if waited >= max_wait:
                if DEBUG:
                    print("⚠️ Tempo máximo de espera atingido — prosseguindo com leitura do DOM.")
                break

        print("✅ Tentando ler status finais na tabela...")

        # Raspar tabela - lemos o número de linhas e para cada índice pegamos a nova referência (evitar stale)
        rows = driver.find_elements(By.CSS_SELECTOR, "#tabelaUrls tbody tr")
        offline_sites = []
        detected_offline_all = []  # todos detectados offline (mesmo que já no cache)
        detected_unknown = []

        for i in range(len(rows)):
            try:
                # refetch da linha para evitar StaleElementReference
                row = driver.find_elements(By.CSS_SELECTOR, "#tabelaUrls tbody tr")[i]
                url_element = row.find_element(By.CSS_SELECTOR, "td a.url")
                status_element = row.find_element(By.CSS_SELECTOR, "td span.status")
                
                url = url_element.text.strip()
                status = detect_status_from_element(status_element)

                if DEBUG:
                    print(f">>> Linha {i} -> {url} => status_detected: {status}")

                if status == "offline":
                    detected_offline_all.append(url)
                    # só trata como 'novo offline' se não estiver no cache do dia
                    if url not in cache[today]:
                        offline_sites.append(url)

                elif status == "unknown":
                    detected_unknown.append((url, status_element.get_attribute("outerHTML")))

            except StaleElementReferenceException as e:
                print(f"⚠️ Aviso: Elemento 'stale' na linha {i}, refetch e pulo. Erro: {e}")
                continue
            except Exception as e:
                print(f"⚠️ Erro ao processar linha {i}: {e}")
                continue

        # Preparar mensagens
        if not offline_sites:
            # Não houve novos offline hoje
            if detected_offline_all:
                # existem offlines detectados, mas já estavam no cache hoje
                message = (f"⚠️ Nenhum site *novo* offline em {now_formatted()}, "
                           f"porém {len(detected_offline_all)} site(s) permanecem como offline hoje: "
                           f"{', '.join(detected_offline_all)}")
                print("⚠️ Nenhum site offline *novo*, mas existem offlines já conhecidos no cache.")
                send_sms(message)
            else:
                # nenhum offline detectado
                print("✅ Nenhum site offline novo hoje.")
                message = f"✅ Todos os sites monitorados estão online em {now_formatted()}."
                send_sms(message)
        else:
            print(f"🚨 Sites offline detectados (novos): {', '.join(offline_sites)}")
            offline_list = "\n".join(offline_sites)
            offline_list_clean = re.sub(r'[^\x00-\x7F]+','', offline_list)
            message = f"🚨 ALERTA - {len(offline_sites)} site(s) offline em {now_formatted()}:\n{offline_list_clean}"
            send_sms(message)
            # atualizar cache com os novos offline
            cache[today].extend(offline_sites)
            save_cache(cache)

        if DEBUG and detected_unknown:
            print("⚠️ Foram detectados status 'unknown' em algumas URLs (mostrando outerHTML):")
            for url, html in detected_unknown:
                print(f"   - {url}")
                print(f"     HTML snippet: {html[:300]}{'...' if len(html)>300 else ''}")

    except Exception as e:
        print(f"❌ Erro durante a verificação: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

# ---------- EXECUÇÃO DO SCRIPT ----------
if __name__ == "__main__":
    check_offline_sites()
