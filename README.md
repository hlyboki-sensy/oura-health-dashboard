# Тіло як текст · Oura Health Dashboard

Приватний само-хостед дашборд для кільця **Oura Ring** — уся аналітика локально, нічого не йде на чужі сервери. Українською, з нейронною озвучкою й щотижневим AI-планом.

A private, self-hosted dashboard for your **Oura Ring** — all analytics stay on your machine. Ukrainian UI, neural voice read-aloud, and a weekly AI plan.

> ⚠️ Інформаційний інструмент із ваших власних даних, **не медичний діагноз**. Проєкт неофіційний, не пов'язаний з Oura Health.
> Informational tool built from your own data — **not medical advice**. Unofficial project, not affiliated with Oura Health.

---

## Що це вміє / Features

- **5 вкладок:** Огляд · Щоденно (всі показники + тлумачення) · Потижнево · План на тиждень (AI-тренер) · Словник.
- **Усі дані локально** — експорт через офіційний Oura Cloud API v2 у JSON + CSV.
- **Тижневі рекомендації** на ваших **реальних кореляціях** (стрес→HRV, сон→готовність тощо).
- **Нейронна озвучка** будь-якої вкладки — природним українським голосом, **безкоштовно й без ключів** (Microsoft Edge TTS). Опційно — Azure / OpenAI.
- **Кнопка «Оновити з кільця»** прямо в дашборді + щотижневий авто-план.
- Редакторський дизайн (Fraunces + Instrument Sans), без зовнішніх залежностей, окрім Chart.js (CDN).

---

## 🇺🇦 Налаштування (5 хвилин)

**Потрібно:** Python 3.9+, macOS або Linux.

1. **Залежності:**
   ```bash
   pip install requests edge-tts
   ```
2. **Зареєструй свій застосунок Oura** на https://developer.ouraring.com → *Create New* →
   Redirect URI: `http://localhost:8765/callback` → скопіюй **Client ID** і **Client Secret**.
3. **Конфіг:**
   ```bash
   cp config.example.json config.json
   ```
   Встав свої `client_id` і `client_secret`.
4. **Перший експорт** (відкриє браузер для входу в Oura):
   ```bash
   python3 oura_export.py
   ```
5. **Збери дашборд і відкрий:**
   ```bash
   python3 build_dashboard.py
   python3 serve.py        # → http://127.0.0.1:8910/
   ```
   На macOS можна просто двічі клікнути **`start.command`**.

**Оновлювати далі:** кнопка «↻ Оновити з кільця» в дашборді, або `python3 oura_export.py && python3 build_dashboard.py`.

### Щотижневий AI-тренер (опційно)
`coach_weekly.sh` щотижня оновлює «План на тиждень». Детермінований двигун працює завжди; для **глибокого** AI-розбору встанови [Claude Code](https://claude.com/claude-code) і зроби `claude login`. Постав на розклад (cron/launchd) — приклад у розділі English нижче.

### Голос
За замовчуванням — Edge TTS (голос `uk-UA-PolinaNeural`, без ключа). Зміни голос/швидкість у `tts_config.json` (`uk-UA-OstapNeural` — чоловічий). Для Azure/OpenAI див. `tts_config.example.json`.

---

## 🇬🇧 Setup (5 minutes)

**Requires:** Python 3.9+, macOS or Linux.

1. **Dependencies:** `pip install requests edge-tts`
2. **Register your Oura app** at https://developer.ouraring.com → *Create New* →
   Redirect URI `http://localhost:8765/callback` → copy **Client ID** & **Client Secret**.
3. **Config:** `cp config.example.json config.json` and paste your keys.
4. **First export** (opens browser to authorize): `python3 oura_export.py`
5. **Build & open:** `python3 build_dashboard.py` then `python3 serve.py` → http://127.0.0.1:8910/
   (or double-click `start.command` on macOS).

**Refresh later:** the “Оновити з кільця” (Refresh) button in the dashboard, or rerun the two commands.

### Weekly AI coach (optional)
`coach_weekly.sh` refreshes the weekly plan. The deterministic engine always works; for the **deep** AI write-up install [Claude Code](https://claude.com/claude-code) and run `claude login`. Schedule it weekly, e.g. macOS launchd or cron:
```bash
# crontab -e  → every Monday 08:30
30 8 * * 1 /bin/bash /path/to/coach_weekly.sh
```

### Voice
Defaults to free Edge TTS (`uk-UA-PolinaNeural`, no key). Change voice/rate in `tts_config.json`. Azure/OpenAI options in `tts_config.example.json`.

---

## Privacy / Приватність

Your health data **never leaves your computer**. `.gitignore` keeps `config.json`, `tokens.json`, and all `data/` out of git. The dashboard runs on `localhost` only.

The UI is in Ukrainian. Translations / PRs welcome.

## License
MIT © 2026 Olena Dubytska. Built with help from Claude.
