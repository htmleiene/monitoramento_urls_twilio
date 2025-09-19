// monitor_twilio.js
import puppeteer from "puppeteer";
import twilio from "twilio";
import fs from "fs";
import path from "path";
import { format } from "date-fns";
import { utcToZonedTime } from "date-fns-tz";

// ---------- CONFIGURAÇÃO TWILIO ----------
const accountSid = process.env.TWILIO_ACCOUNT_SID;
const authToken  = process.env.TWILIO_AUTH_TOKEN;
const client     = twilio(accountSid, authToken);
const fromNumber = process.env.TWILIO_PHONE; // Twilio
const toNumber   = process.env.MY_PHONE;     // Seu celular

// ---------- CONFIGURAÇÃO MONITOR ----------
const MONITOR_URL = "https://htmleiene.github.io/monitoramento_urls/";
const CHECK_INTERVAL_MS = 15_000; // 15 segundos
const TIMEZONE = "America/Sao_Paulo";
const CACHE_FILE = path.resolve("./offline_cache.json");

// ---------- FUNÇÕES AUXILIARES ----------

// Formata data/hora em DD-MM-YYYY HH:mm:ss (São Paulo)
function nowFormatted() {
  const zoned = utcToZonedTime(new Date(), TIMEZONE);
  return format(zoned, "dd-MM-yyyy HH:mm:ss", { timeZone: TIMEZONE });
}

// Lê cache diário
function readCache() {
  try {
    if (!fs.existsSync(CACHE_FILE)) return {};
    const raw = fs.readFileSync(CACHE_FILE, "utf-8");
    return JSON.parse(raw);
  } catch (err) {
    console.error("❌ Erro ao ler cache:", err.message);
    return {};
  }
}

// Salva cache diário
function saveCache(cache) {
  try {
    fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2));
    console.log("🗄️ Cache atualizado.");
  } catch (err) {
    console.error("❌ Erro ao salvar cache:", err.message);
  }
}

// Envia SMS via Twilio
async function sendSMS(message) {
  try {
    await client.messages.create({ body: message, from: fromNumber, to: toNumber });
    console.log(`📩 SMS enviado com sucesso para ${toNumber}`);
  } catch (err) {
    console.error("❌ Falha ao enviar SMS:", err.message);
  }
}

// ---------- FUNÇÃO PRINCIPAL ----------
async function checkOfflineSites() {
  console.log(`\n🟢 Iniciando verificação em ${nowFormatted()}`);
  const cache = readCache();
  const today = format(new Date(), "dd-MM-yyyy", { timeZone: TIMEZONE });
  if (!cache[today]) cache[today] = [];

  let offlineSites = [];

  const browser = await puppeteer.launch({ headless: "new" });
  try {
    const page = await browser.newPage();
    await page.goto(MONITOR_URL, { waitUntil: "networkidle2" });
    console.log("⏳ Aguardando 15 segundos para página carregar...");
    await page.waitForTimeout(15_000);

    // Raspar tabela
    const rows = await page.$$eval("#tabelaUrls tbody tr", trs =>
      trs.map(tr => {
        const url = tr.querySelector("td a.url")?.textContent.trim();
        const status = tr.querySelector("td span.status")?.textContent.trim().toLowerCase();
        return { url, status };
      })
    );

    offlineSites = rows
      .filter(r => r.status.includes("offline"))
      .map(r => r.url)
      .filter(url => !cache[today].includes(url));

    if (offlineSites.length === 0) {
      console.log("✅ Nenhum site offline novo hoje.");
    } else {
      console.log(`🚨 Sites offline detectados: ${offlineSites.join(", ")}`);
      const message = `🚨 ALERTA - ${offlineSites.length} site(s) offline em ${nowFormatted()}:\n${offlineSites.join("\n")}`;
      await sendSMS(message);
      // Atualiza cache
      cache[today].push(...offlineSites);
      saveCache(cache);
    }
  } catch (err) {
    console.error("❌ Erro durante verificação:", err.message);
  } finally {
    await browser.close();
  }
}

// ---------- LOOP CONTÍNUO ----------
(async function main() {
  console.log(`🟢 Monitoramento contínuo iniciado em ${nowFormatted()}`);
  while (true) {
    try {
      await checkOfflineSites();
    } catch (err) {
      console.error("❌ Erro inesperado:", err.message);
    }
    console.log(`⏰ Próxima verificação em ${CHECK_INTERVAL_MS / 1000} segundos`);
    await new Promise(r => setTimeout(r, CHECK_INTERVAL_MS));
  }
})();


