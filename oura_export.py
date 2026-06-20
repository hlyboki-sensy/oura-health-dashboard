#!/usr/bin/env python3
"""
Oura Ring → локальний експорт усіх даних.

Що робить:
  1. Перший запуск: відкриває браузер для авторизації (OAuth2), ти тиснеш "Дозволити",
     скрипт ловить код на http://localhost:8765/callback і міняє його на токени.
     Токени зберігаються у tokens.json (далі логінитися не треба — оновлюються самі).
  2. Стягує всі типи даних Oura за заданий період у теку ./data/ (JSON + CSV).

Запуск:
    python3 oura_export.py                # період за замовчуванням (2020-01-01 → сьогодні)
    python3 oura_export.py 2024-01-01     # з вказаної дати
    python3 oura_export.py 2024-01-01 2024-12-31
"""

import csv
import json
import os
import sys
import threading
import time
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
TOKENS_PATH = os.path.join(HERE, "tokens.json")
DATA_DIR = os.path.join(HERE, "data")

AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
TOKEN_URL = "https://moi.ouraring.com/oauth/v2/ext/oauth-token"
API_BASE = "https://api.ouraring.com/v2/usercollection"

# Усі скоупи, які ми ввімкнули при створенні застосунку.
SCOPES = [
    "email", "personal", "daily", "heartrate", "tag", "workout",
    "session", "spo2", "ring_configuration", "stress", "heart_health",
]

# Ендпоінти з фільтром по даті (start_date / end_date).
DATE_ENDPOINTS = [
    "daily_activity", "daily_sleep", "daily_readiness", "daily_spo2",
    "daily_stress", "daily_resilience", "daily_cardiovascular_age",
    "sleep", "sleep_time", "workout", "session",
    "tag", "enhanced_tag", "rest_mode_period", "vO2_max",
]
# Ендпоінти без параметрів (повертають поточний стан).
PLAIN_ENDPOINTS = ["personal_info", "ring_configuration"]
# Пульс — окремий формат (datetime).
HEARTRATE = "heartrate"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# OAuth2
# ---------------------------------------------------------------------------
class _CallbackHandler(BaseHTTPRequestHandler):
    code = None
    error = None

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        if "code" in qs:
            _CallbackHandler.code = qs["code"][0]
            msg = "Готово! Авторизація успішна. Можеш закрити цю вкладку."
        else:
            _CallbackHandler.error = qs.get("error", ["unknown"])[0]
            msg = "Помилка авторизації: " + _CallbackHandler.error
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            f"<html><body style='font-family:sans-serif;text-align:center;"
            f"margin-top:80px'><h2>{msg}</h2></body></html>".encode("utf-8")
        )

    def log_message(self, *args):
        pass  # тиша


def do_oauth(cfg):
    redirect = cfg["redirect_uri"]
    port = urlparse(redirect).port or 80
    state = "oura-export"
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": redirect,
        "scope": " ".join(SCOPES),
        "state": state,
    }
    url = AUTHORIZE_URL + "?" + urlencode(params)

    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    t = threading.Thread(target=server.handle_request)  # обслуговуємо 1 запит
    t.start()

    print(f"\n→ Відкриваю браузер для авторизації Oura...")
    print(f"  Якщо не відкрилось — перейди вручну:\n  {url}\n")
    webbrowser.open(url)

    # чекаємо на колбек (макс. 5 хв)
    for _ in range(300):
        if _CallbackHandler.code or _CallbackHandler.error:
            break
        time.sleep(1)
    t.join(timeout=2)

    if _CallbackHandler.error:
        sys.exit(f"Авторизація не вдалася: {_CallbackHandler.error}")
    if not _CallbackHandler.code:
        sys.exit("Не дочекалися коду авторизації (таймаут).")

    print("✓ Код отримано, міняю на токени...")
    resp = _token_request(cfg, {
        "grant_type": "authorization_code",
        "code": _CallbackHandler.code,
        "redirect_uri": redirect,
    })
    tokens = resp.json()
    tokens["_obtained_at"] = int(time.time())
    save_tokens(tokens)
    print("✓ Токени збережено.")
    return tokens


def save_tokens(tokens):
    with open(TOKENS_PATH, "w") as f:
        json.dump(tokens, f, indent=2)
    os.chmod(TOKENS_PATH, 0o600)


def _token_request(cfg, data):
    """Обмін на токени. Пробує Basic auth, при потребі — креди в тілі."""
    from requests.auth import HTTPBasicAuth
    # Спроба 1: HTTP Basic auth (client_id:client_secret)
    resp = requests.post(
        TOKEN_URL, data=data,
        auth=HTTPBasicAuth(cfg["client_id"], cfg["client_secret"]),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code == 401:
        # Спроба 2: креди в тілі запиту
        body = dict(data)
        body["client_id"] = cfg["client_id"]
        body["client_secret"] = cfg["client_secret"]
        resp = requests.post(
            TOKEN_URL, data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if not resp.ok:
        print(f"  Помилка {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    return resp


def refresh_tokens(cfg, tokens):
    print("→ Токен застарів, оновлюю...")
    resp = _token_request(cfg, {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
    })
    new = resp.json()
    new["_obtained_at"] = int(time.time())
    save_tokens(new)
    return new


def get_access_token(cfg):
    if os.path.exists(TOKENS_PATH):
        with open(TOKENS_PATH) as f:
            tokens = json.load(f)
        age = time.time() - tokens.get("_obtained_at", 0)
        # access token живе ~30 днів; оновлюємо завчасно після 25 діб
        if age > 25 * 24 * 3600:
            try:
                tokens = refresh_tokens(cfg, tokens)
            except Exception as e:
                print(f"  (refresh не вдався: {e} — авторизуюся заново)")
                tokens = do_oauth(cfg)
        return tokens["access_token"]
    return do_oauth(cfg)["access_token"]


# ---------------------------------------------------------------------------
# Витяг даних
# ---------------------------------------------------------------------------
def fetch_all(endpoint, headers, params):
    """Збирає всі сторінки одного ендпоінта."""
    rows = []
    url = f"{API_BASE}/{endpoint}"
    p = dict(params)
    while True:
        r = requests.get(url, headers=headers, params=p)
        if r.status_code == 404:
            return None  # ендпоінт відсутній
        if r.status_code == 403:
            print(f"    ⚠ {endpoint}: немає доступу (403) — пропускаю")
            return rows
        if r.status_code == 429:
            print("    ⏳ ліміт запитів, чекаю 60с...")
            time.sleep(60)
            continue
        r.raise_for_status()
        body = r.json()
        if "data" in body:
            rows.extend(body["data"])
            nxt = body.get("next_token")
            if nxt:
                p["next_token"] = nxt
                continue
            return rows
        # ендпоінти без пагінації (personal_info, ring_configuration)
        return body


def flatten(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_outputs(name, data):
    # JSON
    with open(os.path.join(DATA_DIR, f"{name}.json"), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # CSV (лише для списків записів)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        keys = []
        for row in data:
            for k in row:
                if k not in keys:
                    keys.append(k)
        with open(os.path.join(DATA_DIR, f"{name}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for row in data:
                w.writerow({k: flatten(row.get(k, "")) for k in keys})


def main():
    cfg = load_config()
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    start = pos[0] if len(pos) > 0 else "2020-01-01"
    end = pos[1] if len(pos) > 1 else date.today().isoformat()
    skip_hr = "--no-heartrate" in flags
    os.makedirs(DATA_DIR, exist_ok=True)

    token = get_access_token(cfg)
    headers = {"Authorization": f"Bearer {token}"}

    print(f"\n📥 Тягну дані за період {start} → {end}\n")
    summary = []

    for ep in PLAIN_ENDPOINTS:
        data = fetch_all(ep, headers, {})
        if data is None:
            print(f"  – {ep}: недоступний")
            continue
        write_outputs(ep, data)
        print(f"  ✓ {ep}")
        summary.append((ep, "ok"))

    for ep in DATE_ENDPOINTS:
        data = fetch_all(ep, headers, {"start_date": start, "end_date": end})
        if data is None:
            print(f"  – {ep}: недоступний (404)")
            continue
        write_outputs(ep, data)
        n = len(data) if isinstance(data, list) else 1
        print(f"  ✓ {ep}: {n} записів")
        summary.append((ep, n))

    # Пульс: окремий формат datetime + короткі вікна (Oura не дає широкий діапазон)
    if skip_hr:
        print("  – heartrate: пропущено (--no-heartrate)")
        print(f"\n✅ Готово (без пульсу). Дані тут: {DATA_DIR}")
        return
    hr_all = []
    d0 = datetime.fromisoformat(start)
    d1 = datetime.fromisoformat(end)
    cur = d0
    while cur < d1:
        chunk_end = min(cur + timedelta(days=30), d1)
        part = fetch_all(HEARTRATE, headers, {
            "start_datetime": cur.strftime("%Y-%m-%dT00:00:00+00:00"),
            "end_datetime": chunk_end.strftime("%Y-%m-%dT00:00:00+00:00"),
        })
        if isinstance(part, list):
            hr_all.extend(part)
        cur = chunk_end
    write_outputs(HEARTRATE, hr_all)
    print(f"  ✓ {HEARTRATE}: {len(hr_all)} вимірів")
    summary.append((HEARTRATE, len(hr_all)))

    print(f"\n✅ Готово. Дані тут: {DATA_DIR}")
    print("   Формати: .json (повні) + .csv (для Excel/Sheets)")


if __name__ == "__main__":
    main()
