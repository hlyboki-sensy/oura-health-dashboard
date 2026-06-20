#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Локальний сервер дашборду: статика + оновлення даних + нейронна озвучка.

Запуск:  python3 serve.py        →  http://127.0.0.1:8910/

Маршрути:
  /                 → index.html
  GET  /api/refresh → свіжі дані з кільця (без пульсу) + ребілд
  POST /api/tts     → синтез тексту нейронним голосом (Azure / OpenAI) → audio/mpeg
"""
import asyncio
import html as _html
import json
import os
import re
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8910
TTS_CFG = os.path.join(HERE, "tts_config.json")


def load_tts_cfg():
    if not os.path.exists(TTS_CFG):
        return None
    try:
        cfg = json.load(open(TTS_CFG))
        return cfg if cfg.get("provider") and not cfg.get("disabled") else None
    except Exception:
        return None


def _chunks(text, n):
    """Розбити текст на шматки ≤ n символів по межах речень."""
    parts, buf = [], ""
    for sent in re.split(r"(?<=[.!?…])\s+", text):
        if len(buf) + len(sent) + 1 > n and buf:
            parts.append(buf); buf = sent
        else:
            buf = (buf + " " + sent).strip()
    if buf:
        parts.append(buf)
    return parts or [text]


def edge_tts_synth(text, cfg):
    """Безкоштовний нейронний голос через Microsoft Edge (edge-tts) — без ключа."""
    import edge_tts
    voice = cfg.get("edge_voice", "uk-UA-PolinaNeural")
    rate = cfg.get("rate", "+0%")

    async def one(t):
        audio = b""
        comm = edge_tts.Communicate(t, voice, rate=rate)
        async for ch in comm.stream():
            if ch["type"] == "audio":
                audio += ch["data"]
        return audio

    out = b""
    for chunk in _chunks(text, 4000):
        out += asyncio.run(one(chunk))
    return out


def azure_tts(text, cfg):
    region = cfg["azure_region"]; key = cfg["azure_key"]
    voice = cfg.get("azure_voice", "uk-UA-PolinaNeural")
    rate = cfg.get("rate", "+0%")
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    audio = b""
    for chunk in _chunks(text, 1800):
        ssml = (f"<speak version='1.0' xml:lang='uk-UA'>"
                f"<voice name='{voice}'><prosody rate='{rate}'>"
                f"{_html.escape(chunk)}</prosody></voice></speak>")
        r = requests.post(url, data=ssml.encode("utf-8"), timeout=60, headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "oura-dashboard"})
        r.raise_for_status(); audio += r.content
    return audio


def openai_tts(text, cfg):
    key = cfg["openai_key"]
    voice = cfg.get("openai_voice", "nova")
    model = cfg.get("openai_model", "gpt-4o-mini-tts")
    audio = b""
    for chunk in _chunks(text, 3500):
        body = {"model": model, "voice": voice, "input": chunk, "response_format": "mp3"}
        inst = cfg.get("openai_instructions")
        if inst:
            body["instructions"] = inst
        r = requests.post("https://api.openai.com/v1/audio/speech", timeout=60,
                          headers={"Authorization": f"Bearer {key}"}, json=body)
        r.raise_for_status(); audio += r.content
    return audio


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/refresh"):
            return self._refresh()
        if self.path.startswith("/api/tts-status"):
            cfg = load_tts_cfg()
            return self._json({"enabled": bool(cfg), "provider": (cfg or {}).get("provider")})
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/tts"):
            return self._tts()
        self.send_response(404); self.end_headers()

    def _tts(self):
        cfg = load_tts_cfg()
        if not cfg:
            return self._json({"error": "not_configured"}, 503)
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            text = (data.get("text") or "").strip()
            if not text:
                return self._json({"error": "empty"}, 400)
            if cfg["provider"] == "edge":
                audio = edge_tts_synth(text, cfg)
            elif cfg["provider"] == "azure":
                audio = azure_tts(text, cfg)
            elif cfg["provider"] == "openai":
                audio = openai_tts(text, cfg)
            else:
                return self._json({"error": "bad_provider"}, 400)
        except requests.HTTPError as e:
            return self._json({"error": f"{e.response.status_code}: {e.response.text[:200]}"}, 502)
        except Exception as e:
            return self._json({"error": str(e)[:300]}, 502)
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.end_headers(); self.wfile.write(audio)

    def _refresh(self):
        result = {"ok": False, "log": ""}
        try:
            r1 = subprocess.run([sys.executable, "oura_export.py", "--no-heartrate"],
                                cwd=HERE, capture_output=True, text=True, timeout=300)
            r2 = subprocess.run([sys.executable, "build_dashboard.py"],
                                cwd=HERE, capture_output=True, text=True, timeout=120)
            r3 = subprocess.run([sys.executable, "coach_plan.py"],
                                cwd=HERE, capture_output=True, text=True, timeout=60)
            result["ok"] = (r1.returncode == 0 and r2.returncode == 0)
            result["log"] = (r1.stdout + r1.stderr + r2.stdout + r2.stderr + r3.stdout + r3.stderr)[-800:]
        except subprocess.TimeoutExpired:
            result["log"] = "Перевищено час очікування."
        except Exception as e:
            result["log"] = f"Помилка: {e}"
        self._json(result, 200 if result["ok"] else 500)


if __name__ == "__main__":
    os.chdir(HERE)
    cfg = load_tts_cfg()
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Дашборд: http://127.0.0.1:{PORT}/  (Ctrl+C — зупинити)")
    print(f"Нейронна озвучка: {'УВІМКНЕНА (' + cfg['provider'] + ')' if cfg else 'вимкнена (немає tts_config.json)'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nЗупинено.")
