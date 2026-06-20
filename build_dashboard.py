#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Будує дашборд здоров'я з даних Oura (тека ./data) → dashboard.html.
Українською, з графіками (Chart.js) і тижневими рекомендаціями.

Запуск:  python3 build_dashboard.py
Потім:   відкрити dashboard.html у браузері.
"""

import json
import os
import re
import statistics as st
from datetime import datetime, date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "dashboard.html")


# ---------- утиліти ----------
def load(name):
    p = os.path.join(DATA, f"{name}.json")
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return json.load(f)


# Українська типографіка: 1–2-літерні слова не висять у кінці рядка → NBSP.
def nbsp(s):
    return re.sub(r'(?<![\w ])([A-Za-zА-Яа-яІіЇїЄєҐґ0-9]{1,2})\s+',
                  lambda m: m.group(1) + ' ', s)


def parse_day(d):
    return datetime.strptime(d[:10], "%Y-%m-%d").date()


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def by_day(records, key, day_key="day"):
    """{date: value} для одного поля."""
    out = {}
    for r in records:
        if r.get(key) is not None and r.get(day_key):
            out[parse_day(r[day_key])] = r[key]
    return out


def series(d):
    """відсортований [(date, value)]"""
    return sorted(d.items())


def iso(d):
    return d.isoformat()


# ---------- завантаження ----------
d_sleep = load("daily_sleep")
d_ready = load("daily_readiness")
d_act = load("daily_activity")
d_spo2 = load("daily_spo2")
d_stress = load("daily_stress")
d_resil = load("daily_resilience")
d_cva = load("daily_cardiovascular_age")
sleep = [s for s in load("sleep") if s.get("type") == "long_sleep"]
workout = load("workout")
pinfo = load("personal_info")
ring = load("ring_configuration")

pinfo = pinfo if isinstance(pinfo, dict) else (pinfo[0] if pinfo else {})
ring = ring if isinstance(ring, dict) else (ring[0] if ring else {})

# ---------- ряди для графіків ----------
ready_score = by_day(d_ready, "score")
sleep_score = by_day(d_sleep, "score")
act_score = by_day(d_act, "score")
steps = by_day(d_act, "steps")
active_cal = by_day(d_act, "active_calories")
sedentary = by_day(d_act, "sedentary_time")
temp_dev = by_day(d_ready, "temperature_deviation")

# нічні метрики з детального сну
night = {}
for s in sleep:
    day = parse_day(s["day"])
    night[day] = {
        "total_h": (s.get("total_sleep_duration") or 0) / 3600,
        "efficiency": s.get("efficiency"),
        "hrv": s.get("average_hrv"),
        "rhr": s.get("lowest_heart_rate"),
        "avg_hr": s.get("average_heart_rate"),
        "deep_h": (s.get("deep_sleep_duration") or 0) / 3600,
        "rem_h": (s.get("rem_sleep_duration") or 0) / 3600,
        "light_h": (s.get("light_sleep_duration") or 0) / 3600,
        "breath": s.get("average_breath"),
        "restless": s.get("restless_periods"),
        "avg_hr": s.get("average_heart_rate"),
        "bedtime": s.get("bedtime_start"),
        "wake": s.get("bedtime_end"),
    }

n_total = {d: v["total_h"] for d, v in night.items()}
n_eff = {d: v["efficiency"] for d, v in night.items()}
n_hrv = {d: v["hrv"] for d, v in night.items()}
n_rhr = {d: v["rhr"] for d, v in night.items()}
n_deep = {d: v["deep_h"] for d, v in night.items()}
n_rem = {d: v["rem_h"] for d, v in night.items()}
n_light = {d: v["light_h"] for d, v in night.items()}
n_breath = {d: v["breath"] for d, v in night.items()}
spo2 = {parse_day(r["day"]): (r.get("spo2_percentage") or {}).get("average")
        for r in d_spo2 if r.get("spo2_percentage")}
vasc = by_day(d_cva, "vascular_age")

all_days = sorted(set(ready_score) | set(sleep_score) | set(act_score) | set(night))
if not all_days:
    raise SystemExit("Немає даних у ./data — спершу запусти oura_export.py")

last_day = all_days[-1]
week_days = [d for d in all_days if d > last_day - timedelta(days=7)]
prev_week = [d for d in all_days if last_day - timedelta(days=14) < d <= last_day - timedelta(days=7)]


def wmean(dct, days):
    return mean([dct.get(d) for d in days])


def baseline(dct):
    return mean(list(dct.values()))


# ---------- KPI (останнє + Δ до базового рівня) ----------
def kpi(label, dct, days, fmt="{:.0f}", unit="", good_high=True, ndigits=0):
    cur = wmean(dct, days)
    base = baseline(dct)
    if cur is None:
        return None
    delta = (cur - base) if base is not None else 0
    arrow = "→"
    cls = "flat"
    if base is not None and abs(delta) > (abs(base) * 0.02 + 1e-9):
        up = delta > 0
        good = up if good_high else (not up)
        arrow = "↑" if up else "↓"
        cls = "good" if good else "bad"
    return {
        "label": label, "value": fmt.format(cur), "unit": unit,
        "delta": f"{arrow} {abs(delta):.{ndigits}f}{unit}", "cls": cls,
    }


kpis = [
    kpi("Готовність (7 дн)", ready_score, week_days, "{:.0f}", ""),
    kpi("Сон, скор (7 дн)", sleep_score, week_days, "{:.0f}", ""),
    kpi("Активність (7 дн)", act_score, week_days, "{:.0f}", ""),
    kpi("Тривалість сну", n_total, week_days, "{:.1f}", " год", ndigits=1),
    kpi("Ефективність сну", n_eff, week_days, "{:.0f}", "%"),
    kpi("Пульс спокою", n_rhr, week_days, "{:.0f}", " уд", good_high=False),
    kpi("HRV (варіаб.)", n_hrv, week_days, "{:.0f}", " мс"),
    kpi("Частота дихання", n_breath, week_days, "{:.1f}", "/хв", good_high=False, ndigits=1),
]
kpis = [k for k in kpis if k]


# ---------- движок тижневих рекомендацій ----------
recs = []  # {sev, icon, title, text}   sev: alert/warn/good


def add(sev, icon, title, text):
    recs.append({"sev": sev, "icon": icon, "title": nbsp(title), "text": nbsp(text)})


sl_h = wmean(n_total, week_days)
sl_h_prev = wmean(n_total, prev_week)
eff = wmean(n_eff, week_days)
rd = wmean(ready_score, week_days)
rhr_w = wmean(n_rhr, week_days)
rhr_base = baseline(n_rhr)
hrv_w = wmean(n_hrv, week_days)
hrv_base = baseline(n_hrv)
deep_w = wmean(n_deep, week_days)
rem_w = wmean(n_rem, week_days)
tmp_w = mean([abs(temp_dev[d]) for d in week_days if temp_dev.get(d) is not None])
tmp_max = max([temp_dev[d] for d in week_days if temp_dev.get(d) is not None], default=None)
steps_w = wmean(steps, week_days)
sed_w = wmean(sedentary, week_days)
spo2_w = wmean(spo2, week_days)
breath_w = wmean(n_breath, week_days)
breath_base = baseline(n_breath)

# bedtime consistency (хв розкид часу відходу до сну)
bt_minutes = []
for d in week_days:
    bt = night.get(d, {}).get("bedtime")
    if bt:
        t = datetime.fromisoformat(bt)
        m = t.hour * 60 + t.minute
        if m < 12 * 60:      # після опівночі → +24год для безперервності
            m += 24 * 60
        bt_minutes.append(m)
bt_std = st.pstdev(bt_minutes) if len(bt_minutes) >= 3 else None

# --- сон: тривалість ---
if sl_h is not None:
    if sl_h < 6:
        add("alert", "😴", "Критично мало сну",
            f"Цього тижня ти спала в середньому {sl_h:.1f} год за ніч. Це нижче за фізіологічну потребу (7–9 год). Хронічний недосип б'є по HRV, концентрації та імунітеті. Спробуй лягати на 30–45 хв раніше вже цього тижня.")
    elif sl_h < 7:
        add("warn", "😴", "Сну трохи замало",
            f"Середня тривалість сну — {sl_h:.1f} год (оптимум 7–9). Зсунь відбій на 20–30 хв раніше і прибери екран за годину до сну.")
    else:
        add("good", "😴", "Тривалість сну в нормі",
            f"Ти спиш у середньому {sl_h:.1f} год — це в здоровому діапазоні. Тримай так.")

# --- ефективність сну ---
if eff is not None and eff < 85:
    add("warn", "🛏️", "Сон уривчастий",
        f"Ефективність сну {eff:.0f}% (добре — від 85%). Часті пробудження зазвичай від алкоголю ввечері, пізньої їжі, теплої спальні чи стресу. Спробуй прохолодніше в кімнаті (18–19°C) і без їжі за 3 год до сну.")

# --- послідовність відбою ---
if bt_std is not None and bt_std > 60:
    add("warn", "⏰", "Нестабільний час відходу до сну",
        f"Час відбою «гуляє» в межах ±{bt_std/60:.1f} год за тиждень. Сталий ритм — один із найсильніших важелів для готовності й HRV. Цілься у вікно відбою в межах 30 хв щодня.")

# --- готовність ---
if rd is not None:
    if rd < 70:
        add("alert", "🔋", "Низька готовність",
            f"Середня готовність за тиждень {rd:.0f} (оптимум ≥85). Організм під навантаженням. Цей тиждень — про відновлення: легші тренування, більше сну, менше стимуляторів увечері.")
    elif rd < 85:
        add("warn", "🔋", "Готовність нижча за оптимум",
            f"Готовність {rd:.0f} (оптимум ≥85). Є запас для покращення — почни зі сну й сталого режиму, решта підтягнеться.")
    else:
        add("good", "🔋", "Чудова готовність",
            f"Середня готовність {rd:.0f} — організм добре відновлюється. Можеш дозволити собі трохи більше навантаження.")

# --- пульс спокою ---
if rhr_w is not None and rhr_base is not None and rhr_w > rhr_base + 2:
    add("warn", "❤️", "Пульс спокою вищий за звичний",
        f"Цього тижня пульс спокою уві сні {rhr_w:.0f} уд/хв — на {rhr_w - rhr_base:.0f} вище за твій базовий ({rhr_base:.0f}). Часті причини: алкоголь, пізнє тренування, зневоднення, стрес або початок застуди. Придивись, що змінилось.")
elif rhr_w is not None and rhr_base is not None and rhr_w <= rhr_base:
    add("good", "❤️", "Пульс спокою стабільний",
        f"Пульс спокою {rhr_w:.0f} уд/хв — на рівні або нижче твого базового. Хороший знак відновлення.")

# --- HRV ---
if hrv_w is not None and hrv_base is not None:
    if hrv_w < hrv_base * 0.9:
        add("warn", "📉", "HRV просіла",
            f"Варіабельність пульсу за тиждень {hrv_w:.0f} мс — нижче твого базового рівня ({hrv_base:.0f}). Це сигнал стресу чи недовідновлення. Пріоритет — сон і зниження навантаження; алкоголь особливо тисне HRV.")
    elif hrv_w >= hrv_base:
        add("good", "📈", "HRV на рівні або вище норми",
            f"HRV {hrv_w:.0f} мс — на рівні чи вище твого базового. Нервова система добре відновлюється.")

# --- фази сну ---
if sl_h and deep_w is not None and (deep_w / sl_h) < 0.13:
    add("warn", "🌊", "Мало глибокого сну",
        f"Глибокий сон ~{deep_w*60:.0f} хв ({deep_w/sl_h*100:.0f}% від сну; норма 13–20%). Глибокий сон — це фізичне відновлення. Допомагають: сталий режим, прохолода, відсутність алкоголю та інтенсивний рух удень (але не пізно ввечері).")
if sl_h and rem_w is not None and (rem_w / sl_h) < 0.18:
    add("warn", "🧠", "Мало REM-сну",
        f"REM-сон ~{rem_w*60:.0f} хв ({rem_w/sl_h*100:.0f}% від сну; норма ~20–25%). REM відповідає за пам'ять і емоції. Найбільше REM — у другій половині ночі, тож достатня тривалість сну і відсутність алкоголю критичні.")

# --- температура / хвороба ---
if tmp_max is not None and tmp_max > 0.5:
    add("alert", "🌡️", "Підвищене відхилення температури",
        f"Цього тижня температура тіла відхилялась до +{tmp_max:.1f}°C від норми. Разом із вищим пульсом це може бути ознакою хвороби або фазою циклу. Дай собі відновитись і спостерігай за самопочуттям.")

# --- частота дихання ---
if breath_w is not None and breath_base is not None and breath_w > breath_base + 1.5:
    add("warn", "🫁", "Підвищена частота дихання",
        f"Частота дихання уві сні {breath_w:.1f}/хв — вище звичного ({breath_base:.1f}). Може супроводжувати застуду, алкоголь чи стрес. Якщо тримається кілька днів — придивись до самопочуття.")

# --- SpO2 ---
if spo2_w is not None and spo2_w < 95:
    add("warn", "🩸", "Знижена сатурація уві сні",
        f"Середній SpO₂ {spo2_w:.0f}% (норма ≥95%). Якщо стабільно низький — варто звернути увагу на дихання уві сні. Поодинокі заниження часто є артефактом вимірювання.")

# --- активність: спад скору ---
act_w = wmean(act_score, week_days)
act_base = baseline(act_score)
if act_w is not None and act_base is not None and act_w < act_base - 8:
    add("warn", "📉", "Активність просіла за тиждень",
        f"Скор активності цього тижня {act_w:.0f} — помітно нижче твого базового ({act_base:.0f}). Готовність висока, тож є ресурс додати руху: 2–3 прогулянки по 20–30 хв або легке кардіо. Це підтримає судинний вік і HRV.")

# --- активність: кроки ---
if steps_w is not None:
    if steps_w < 5000:
        add("warn", "🚶", "Мало руху",
            f"У середньому {steps_w:.0f} кроків/день. Для здоров'я серця й судин цільтеся хоча б у 7–8 тис. Почни з 10-хвилинних прогулянок і функції «рух щогодини».")
    elif steps_w >= 8000:
        add("good", "🚶", "Хороший рівень руху",
            f"Середньо {steps_w:.0f} кроків/день — чудовий рівень активності. Тримай баланс із відновленням.")

# сортування за пріоритетом
order = {"alert": 0, "warn": 1, "good": 2}
recs.sort(key=lambda r: order[r["sev"]])


# ---------- збірка HTML ----------
def chart_arrays(dct):
    s = series(dct)
    return [iso(d) for d, _ in s], [round(v, 2) if isinstance(v, float) else v for _, v in s]


payload = {
    "labels_main": [iso(d) for d in all_days],
    "ready": [ready_score.get(d) for d in all_days],
    "sleep": [sleep_score.get(d) for d in all_days],
    "act": [act_score.get(d) for d in all_days],
    "total_h": [round(n_total.get(d), 2) if n_total.get(d) else None for d in all_days],
    "eff": [n_eff.get(d) for d in all_days],
    "rhr": [n_rhr.get(d) for d in all_days],
    "hrv": [n_hrv.get(d) for d in all_days],
    "deep": [round(n_deep.get(d), 2) if n_deep.get(d) is not None else None for d in all_days],
    "rem": [round(n_rem.get(d), 2) if n_rem.get(d) is not None else None for d in all_days],
    "light": [round(n_light.get(d), 2) if n_light.get(d) is not None else None for d in all_days],
    "steps": [steps.get(d) for d in all_days],
    "spo2": [round(spo2.get(d), 1) if spo2.get(d) else None for d in all_days],
    "temp": [temp_dev.get(d) for d in all_days],
    "breath": [n_breath.get(d) for d in all_days],
}

kpi_html = ""
for k in kpis:
    kpi_html += f'''<div class="kpi">
      <div class="kpi-label">{nbsp(k["label"])}</div>
      <div class="kpi-value">{k["value"]}<span class="kpi-unit">{k["unit"]}</span></div>
      <div class="kpi-delta {k["cls"]}">{k["delta"]} <span class="muted">vs базовий</span></div>
    </div>'''

rec_html = ""
sev_label = {"alert": "Увага", "warn": "Варто", "good": "Добре"}
for r in recs:
    rec_html += f'''<div class="rec {r["sev"]}">
      <div class="rec-icon">{r["icon"]}</div>
      <div class="rec-body">
        <div class="rec-head"><span class="rec-tag {r["sev"]}">{sev_label[r["sev"]]}</span> {r["title"]}</div>
        <div class="rec-text">{r["text"]}</div>
      </div>
    </div>'''

age = pinfo.get("age", "—")
sex = {"female": "жін", "male": "чол"}.get(pinfo.get("biological_sex"), "—")
vasc_last = vasc.get(max(vasc)) if vasc else None
resil_last = (d_resil[-1].get("level") if d_resil else None)
resil_ua = {"limited": "обмежена", "adequate": "достатня", "solid": "ґрунтовна",
            "strong": "міцна", "exceptional": "виняткова"}.get(resil_last, resil_last or "—")
n_workouts = len(workout)
date_from, date_to = iso(all_days[0]), iso(all_days[-1])
generated = datetime.fromtimestamp(os.path.getmtime(os.path.join(DATA, "daily_sleep.json"))).strftime("%Y-%m-%d %H:%M")

subtitle = nbsp(f"Дані за {date_from} → {date_to} · {len(all_days)} днів · "
                f"кільце {ring.get('hardware_type','')} · вік {age}, {sex} · "
                f"судинний вік {vasc_last or '—'} · резильєнтність: {resil_ua} · тренувань: {n_workouts}")

TEMPLATE = r"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oura · Дашборд здоров'я</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#0e1116; --panel:#161b22; --panel2:#1c232d; --line:#283242;
  --text:#e8edf4; --muted:#8b98a9; --accent:#FFD20E;
  --good:#3ecf8e; --warn:#f0b429; --alert:#f0656f; --blue:#5aa9ff; --violet:#b18cff;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;
  font-feature-settings:"tnum";-webkit-font-smoothing:antialiased;line-height:1.5}
.wrap{max-width:1180px;margin:0 auto;padding:32px 24px 80px}
header{margin-bottom:28px}
h1{font-size:30px;font-weight:700;letter-spacing:-.02em;margin:0 0 6px}
h1 .dot{color:var(--accent)}
.sub{color:var(--muted);font-size:13px;max-width:880px}
h2{font-size:15px;font-weight:600;color:var(--muted);text-transform:uppercase;
  letter-spacing:.08em;margin:38px 0 16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.kpi-label{font-size:12px;color:var(--muted);margin-bottom:8px}
.kpi-value{font-size:30px;font-weight:700;letter-spacing:-.02em}
.kpi-unit{font-size:14px;color:var(--muted);font-weight:500;margin-left:2px}
.kpi-delta{font-size:12px;margin-top:6px;font-weight:600}
.kpi-delta.good{color:var(--good)} .kpi-delta.bad{color:var(--alert)} .kpi-delta.flat{color:var(--muted)}
.muted{color:var(--muted);font-weight:400}
.recs{display:grid;gap:10px}
.rec{display:flex;gap:14px;background:var(--panel);border:1px solid var(--line);
  border-left-width:3px;border-radius:12px;padding:14px 16px}
.rec.alert{border-left-color:var(--alert)} .rec.warn{border-left-color:var(--warn)}
.rec.good{border-left-color:var(--good)}
.rec-icon{font-size:22px;line-height:1.2}
.rec-head{font-weight:600;font-size:15px;margin-bottom:4px}
.rec-text{font-size:13.5px;color:#cbd5e1}
.rec-tag{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
  padding:2px 7px;border-radius:6px;margin-right:8px;vertical-align:1px}
.rec-tag.alert{background:rgba(240,101,111,.16);color:var(--alert)}
.rec-tag.warn{background:rgba(240,180,41,.16);color:var(--warn)}
.rec-tag.good{background:rgba(62,207,142,.16);color:var(--good)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:820px){.grid{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}
.card h3{margin:0 0 4px;font-size:15px;font-weight:600}
.card .hint{font-size:12px;color:var(--muted);margin:0 0 14px}
.card.full{grid-column:1/-1}
.chart-box{position:relative;height:220px}
.chart-box.tall{height:300px}
canvas{width:100%!important}
footer{margin-top:48px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:18px}
code{background:var(--panel2);padding:2px 6px;border-radius:5px;color:var(--accent);font-size:12px}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Oura <span class="dot">·</span> дашборд здоров'я</h1>
  <div class="sub">__SUBTITLE__</div>
</header>

<h2>Ключові показники · останні 7 днів</h2>
<div class="kpis">__KPIS__</div>

<h2>Тижневі рекомендації</h2>
<div class="recs">__RECS__</div>

<h2>Тренди</h2>
<div class="grid">
  <div class="card full">
    <h3>Три скори в часі</h3>
    <p class="hint">Готовність, сон і активність (0–100). Дивись на напрямок, а не окремі дні.</p>
    <div class="chart-box tall"><canvas id="c_scores"></canvas></div>
  </div>
  <div class="card">
    <h3>Сон: тривалість і ефективність</h3>
    <p class="hint">Тривалість (год) — стовпці; ефективність (%) — лінія. Норма ефективності ≥85%.</p>
    <div class="chart-box"><canvas id="c_sleep"></canvas></div>
  </div>
  <div class="card">
    <h3>Фази сну</h3>
    <p class="hint">Глибокий · REM · легкий (год). Глибокий 13–20%, REM ~20–25% від ночі.</p>
    <div class="chart-box"><canvas id="c_phases"></canvas></div>
  </div>
  <div class="card">
    <h3>Пульс спокою та HRV</h3>
    <p class="hint">Нижчий пульс і вища HRV = краще відновлення. Стрибки пульсу = стрес/алкоголь/хвороба.</p>
    <div class="chart-box"><canvas id="c_heart"></canvas></div>
  </div>
  <div class="card">
    <h3>Активність: кроки/день</h3>
    <p class="hint">Орієнтир для серця й судин — від 7–8 тис. кроків.</p>
    <div class="chart-box"><canvas id="c_steps"></canvas></div>
  </div>
  <div class="card">
    <h3>Сатурація (SpO₂)</h3>
    <p class="hint">Норма ≥95%. Поодинокі заниження зазвичай артефакт.</p>
    <div class="chart-box"><canvas id="c_spo2"></canvas></div>
  </div>
  <div class="card">
    <h3>Відхилення температури тіла</h3>
    <p class="hint">Стрибок &gt;+0,5°C разом із пульсом може означати хворобу або фазу циклу.</p>
    <div class="chart-box"><canvas id="c_temp"></canvas></div>
  </div>
</div>

<footer>
  Згенеровано __GENERATED__. Щоб оновити дані: <code>python3 oura_export.py</code>, потім <code>python3 build_dashboard.py</code>.<br>
  Це інформаційний інструмент із твоїх власних даних, а не медичний діагноз. За тривожних симптомів — до лікаря.
</footer>
</div>

<script>
const D = __DATA_JSON__;
const muted="#8b98a9", line="#283242";
Chart.defaults.color=muted; Chart.defaults.font.family="-apple-system,Segoe UI,Inter,sans-serif";
Chart.defaults.font.size=11;
const grid={color:line,drawBorder:false}, noGrid={display:false};
function base(extra){return Object.assign({responsive:true,maintainAspectRatio:false,
  interaction:{mode:"index",intersect:false},
  plugins:{legend:{labels:{boxWidth:10,boxHeight:10,usePointStyle:true}}},
  scales:{x:{grid:noGrid,ticks:{maxTicksLimit:8,maxRotation:0}}}},extra||{});}

new Chart(c_scores,{type:"line",data:{labels:D.labels_main,datasets:[
  {label:"Готовність",data:D.ready,borderColor:"#FFD20E",backgroundColor:"#FFD20E",tension:.35,pointRadius:0,borderWidth:2,spanGaps:true},
  {label:"Сон",data:D.sleep,borderColor:"#5aa9ff",backgroundColor:"#5aa9ff",tension:.35,pointRadius:0,borderWidth:2,spanGaps:true},
  {label:"Активність",data:D.act,borderColor:"#3ecf8e",backgroundColor:"#3ecf8e",tension:.35,pointRadius:0,borderWidth:2,spanGaps:true}
]},options:base({scales:{x:{grid:noGrid,ticks:{maxTicksLimit:10,maxRotation:0}},y:{grid:grid,min:0,max:100}}})});

new Chart(c_sleep,{data:{labels:D.labels_main,datasets:[
  {type:"bar",label:"Тривалість, год",data:D.total_h,backgroundColor:"rgba(90,169,255,.45)",borderRadius:4,yAxisID:"y"},
  {type:"line",label:"Ефективність, %",data:D.eff,borderColor:"#FFD20E",pointRadius:0,borderWidth:2,tension:.35,spanGaps:true,yAxisID:"y1"}
]},options:base({scales:{x:{grid:noGrid,ticks:{maxTicksLimit:7,maxRotation:0}},
  y:{grid:grid,position:"left",title:{display:true,text:"год"},suggestedMin:4,suggestedMax:10},
  y1:{grid:noGrid,position:"right",min:70,max:100,title:{display:true,text:"%"}}}})});

new Chart(c_phases,{type:"bar",data:{labels:D.labels_main,datasets:[
  {label:"Глибокий",data:D.deep,backgroundColor:"#3a6ea5",stack:"s"},
  {label:"REM",data:D.rem,backgroundColor:"#b18cff",stack:"s"},
  {label:"Легкий",data:D.light,backgroundColor:"#33415c",stack:"s"}
]},options:base({scales:{x:{stacked:true,grid:noGrid,ticks:{maxTicksLimit:7,maxRotation:0}},
  y:{stacked:true,grid:grid,title:{display:true,text:"год"}}}})});

new Chart(c_heart,{type:"line",data:{labels:D.labels_main,datasets:[
  {label:"Пульс спокою, уд/хв",data:D.rhr,borderColor:"#f0656f",pointRadius:0,borderWidth:2,tension:.35,spanGaps:true,yAxisID:"y"},
  {label:"HRV, мс",data:D.hrv,borderColor:"#3ecf8e",pointRadius:0,borderWidth:2,tension:.35,spanGaps:true,yAxisID:"y1"}
]},options:base({scales:{x:{grid:noGrid,ticks:{maxTicksLimit:7,maxRotation:0}},
  y:{grid:grid,position:"left",title:{display:true,text:"уд/хв"}},
  y1:{grid:noGrid,position:"right",title:{display:true,text:"мс"}}}})});

new Chart(c_steps,{type:"bar",data:{labels:D.labels_main,datasets:[
  {label:"Кроки",data:D.steps,backgroundColor:"rgba(62,207,142,.5)",borderRadius:4}
]},options:base({plugins:{legend:{display:false}},scales:{x:{grid:noGrid,ticks:{maxTicksLimit:7,maxRotation:0}},y:{grid:grid}}})});

new Chart(c_spo2,{type:"line",data:{labels:D.labels_main,datasets:[
  {label:"SpO₂, %",data:D.spo2,borderColor:"#5aa9ff",pointRadius:0,borderWidth:2,tension:.35,spanGaps:true}
]},options:base({plugins:{legend:{display:false}},scales:{x:{grid:noGrid,ticks:{maxTicksLimit:7,maxRotation:0}},y:{grid:grid,min:90,max:100}}})});

new Chart(c_temp,{type:"line",data:{labels:D.labels_main,datasets:[
  {label:"Δ°C",data:D.temp,borderColor:"#f0b429",backgroundColor:"rgba(240,180,41,.15)",fill:true,pointRadius:0,borderWidth:2,tension:.35,spanGaps:true}
]},options:base({plugins:{legend:{display:false}},scales:{x:{grid:noGrid,ticks:{maxTicksLimit:7,maxRotation:0}},y:{grid:grid}}})});
</script>
</body>
</html>"""

html = (TEMPLATE
        .replace("__SUBTITLE__", subtitle)
        .replace("__KPIS__", kpi_html)
        .replace("__RECS__", rec_html)
        .replace("__GENERATED__", generated)
        .replace("__DATA_JSON__", json.dumps(payload, ensure_ascii=False)))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

# ---------- окремий data-bundle для сучасного index.html ----------
# ====================================================================
#  ЩОДЕННО / ПОТИЖНЕВО / СЛОВНИК
# ====================================================================
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]
MON = ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"]


def sev_score(v):
    if v is None:
        return "na"
    return "good" if v >= 85 else ("warn" if v >= 70 else "alert")


def gl(name, what, low, high, fix):
    return {"name": nbsp(name), "what": nbsp(what), "low": nbsp(low),
            "high": nbsp(high), "fix": nbsp(fix)}


# --- словник складових (contributors) ---
CONTRIB = {
    # СОН
    "total_sleep": gl("Загальна тривалість",
        "Скільки ти спала всього за ніч. Оптимум для дорослого — 7–9 год.",
        "Недосип. Навіть одна-дві короткі ночі знижують HRV, концентрацію та імунітет.",
        "Достатньо сну — фундамент відновлення й готовності наступного дня.",
        "Зсунь відбій на 20–40 хв раніше; став сну в пріоритет так само, як зустрічі."),
    "efficiency": gl("Ефективність сну",
        "Відсоток часу в ліжку, який ти реально проспала. Норма ≥85%, відмінно ≥90%.",
        "Ти довго засинаєш або часто прокидаєшся — сон «дірявий».",
        "Сон щільний і безперервний — ознака якісного відпочинку.",
        "Лягай, лише коли сонна; прохолода 18–19°C; без екранів і кофеїну ввечері."),
    "restfulness": gl("Спокій сну",
        "Наскільки сон був безперервним: рухи, мікропробудження, неспокій.",
        "Сон неспокійний. Часті причини: стрес, алкоголь, тепло, пізня їжа.",
        "Тіло лежало спокійно — глибоке відновлення відбулося.",
        "Прохолодна тиха спальня; без алкоголю та важкої їжі за 3 год до сну."),
    "rem_sleep": gl("REM-сон",
        "Фаза сновидінь: пам'ять, навчання, емоційна регуляція. Норма ~20–25% ночі.",
        "Мало REM. Страждають пам'ять і емоційне відновлення.",
        "Достатньо REM — мозок добре переробив день і емоції.",
        "Більше REM у другій половині ночі → потрібна повна тривалість сну; алкоголь різко ріже REM."),
    "deep_sleep": gl("Глибокий сон",
        "Найвідновніша фаза: фізичне відновлення, імунітет, гормон росту. Норма 13–20% ночі.",
        "Мало глибокого сну — тіло відновилось фізично не повністю.",
        "Достатньо глибокого сну — чудово для тіла й імунітету.",
        "Сталий режим, прохолода, фізнавантаження вдень (але не пізно), без алкоголю."),
    "latency": gl("Час засинання",
        "Скільки хвилин ти засинала. Здоровий діапазон ~15–20 хв.",
        "Дуже швидко (<5 хв) часто = недосип; дуже довго (>20–25) = перезбудження чи стрес.",
        "Збалансований час засинання — нервова система в нормі.",
        "Ритуал розслаблення перед сном, тепла ванна, без екранів і думання про справи."),
    "timing": gl("Час сну (циркадний)",
        "Чи спала ти у злагоді з біоритмом. «Опівнічна точка» сну в нормі між ~24:00 і 03:00.",
        "Ти лягаєш надто пізно або надто рано для свого ритму — гормони збиваються.",
        "Час сну в гармонії з біологічним годинником.",
        "Тримай сталий час відбою; ранкове світло допомагає закріпити ритм."),
    # ГОТОВНІСТЬ
    "previous_night": gl("Минула ніч",
        "Як добре ти спала цієї ночі — найбільший внесок у сьогоднішню готовність.",
        "Погана ніч тягне готовність донизу — сьогодні бережи ресурс.",
        "Якісна ніч — організм готовий до навантаження.",
        "Дивись складові сну нижче, щоб зрозуміти, що саме просіло."),
    "sleep_balance": gl("Баланс сну (2 тижні)",
        "Чи вистачає тобі сну сукупно за останні два тижні.",
        "Накопичений недосип — «борг» по сну зростає.",
        "Сну вистачає в довшій перспективі — добра база.",
        "Кілька ночей по 8+ год поспіль допоможуть закрити борг."),
    "sleep_regularity": gl("Регулярність сну",
        "Наскільки сталий твій графік сну день у день.",
        "Графік «гуляє» — один із найсильніших ударів по готовності й HRV.",
        "Сталий ритм сну — потужний важіль здоров'я, ти його тримаєш.",
        "Цілься у вікно відбою й підйому в межах ±30 хв щодня, навіть у вихідні."),
    "previous_day_activity": gl("Активність учора",
        "Чи дало вчорашнє навантаження належний стимул — не перебір і не недобір.",
        "Або перевантаження вчора, або, навпаки, надто пасивний день.",
        "Вчорашнє навантаження було збалансованим.",
        "Чергуй важкі й легкі дні; після інтенсиву — день на відновлення."),
    "activity_balance": gl("Баланс активності",
        "Чи збалансоване твоє навантаження за останні дні/тижні загалом.",
        "Дисбаланс: чи перетренованість, чи затяжна пасивність.",
        "Активність у здоровому балансі.",
        "Тримай регулярний помірний рух замість рідких ривків."),
    "recovery_index": gl("Індекс відновлення",
        "Як швидко пульс знизився до спокою на початку ночі — маркер нічного відновлення.",
        "Пульс знижувався повільно: пізня їжа, алкоголь, стрес чи пізнє тренування.",
        "Пульс швидко впав до спокою — тіло ефективно відновлювалось.",
        "Не їж і не тренуйся пізно; алкоголь особливо гальмує нічне відновлення."),
    "resting_heart_rate": gl("Пульс спокою",
        "Найнижчий пульс уві сні. Нижчий і стабільний — краще.",
        "Підвищений пульс: навантаження, алкоголь, зневоднення, стрес або початок хвороби.",
        "Низький стабільний пульс — серце добре відновлене.",
        "Гідратація, без алкоголю ввечері, спокій перед сном; придивись, що змінилось."),
    "hrv_balance": gl("Баланс HRV",
        "Твоя варіабельність пульсу відносно особистого базового рівня за 2 тижні.",
        "HRV нижча за норму — накопичений стрес або недовідновлення.",
        "HRV на рівні або вище норми — нервова система добре адаптується.",
        "Пріоритет — сон і зниження стресу; дихальні практики піднімають HRV."),
    "body_temperature": gl("Температура тіла",
        "Відхилення нічної температури від твоєї норми.",
        "Підвищення: можлива хвороба, сильний недосон, алкоголь або фаза циклу (овуляція/лютеїнова).",
        "Температура стабільна — жодних ознак перевантаження чи хвороби.",
        "Якщо тримається кілька днів із вищим пульсом — дай собі відновитись і спостерігай."),
    # АКТИВНІСТЬ
    "meet_daily_targets": gl("Денні цілі",
        "Чи добираєш щоденну ціль активності (рух/калорії) — і не надто рідко, і не надто часто на межі.",
        "Кілька днів поспіль ціль не закрита — рухаєшся замало.",
        "Ти стабільно добираєш денну ціль активності.",
        "Почни з 2–3 коротких прогулянок по 10–15 хв — вони закривають ціль непомітно."),
    "stay_active": gl("Загальна активність",
        "Рівень руху протягом дня — наскільки мало сидиш.",
        "Багато сидіння. Тривала нерухомість шкодить судинам незалежно від тренувань.",
        "Хороший фоновий рівень руху протягом дня.",
        "Вставай щогодини; ходи під час дзвінків; сходи замість ліфта."),
    "move_every_hour": gl("Рух щогодини",
        "Чи не залишаєшся надто довго без руху протягом дня.",
        "Довгі періоди без руху — тіло «застоюється».",
        "Ти регулярно розминаєшся протягом дня.",
        "Постав нагадування щогодини на 2–3 хв розминки чи кілька кроків."),
    "training_frequency": gl("Частота тренувань",
        "Наскільки регулярно ти тренуєшся (кілька разів на тиждень).",
        "Тренувань замало для стабільного прогресу серця й м'язів.",
        "Регулярність тренувань на доброму рівні.",
        "Цілься в 3–4 сесії на тиждень, навіть коротких; регулярність > інтенсивність."),
    "training_volume": gl("Обсяг тренувань",
        "Сумарне тренувальне навантаження за тиждень.",
        "Загальний обсяг навантаження низький.",
        "Хороший тижневий обсяг навантаження.",
        "Нарощуй обсяг поступово (~10% на тиждень), щоб не перетренуватись."),
}

# --- словник верхнього рівня (вкладка «Словник») ---
METRICS = [
    ("Готовність", "Holistic-оцінка (0–100), чи готове тіло до навантаження сьогодні. Зводить сон, відновлення, пульс спокою, HRV і температуру. ≥85 — оптимум, 70–84 — норма, <70 — час відновлюватись."),
    ("Сон (скор)", "Якість і кількість сну за ніч (0–100). Складається з тривалості, ефективності, фаз (глибокий/REM), спокою, часу засинання й циркадного таймінгу."),
    ("Активність", "Денна активність і баланс навантаження (0–100): чи добираєш рух, чи не засиджуєшся, чи достатньо тренуєшся і чи даєш собі відновитись."),
    ("HRV (варіабельність пульсу)", "Різниця інтервалів між ударами серця уві сні. Вища HRV = краще відновлення й адаптивність нервової системи. Дуже індивідуальна — дивись на свій тренд, не на чужі цифри."),
    ("Пульс спокою", "Найнижчий пульс уві сні. Нижчий і стабільний — ознака відновленого серця. Стрибки = стрес, алкоголь, хвороба, зневоднення."),
    ("Частота дихання", "Скільки вдихів за хвилину уві сні. Дуже стабільна; стрибок +1–2 може супроводжувати застуду, алкоголь чи стрес."),
    ("Температура тіла", "Відхилення від твоєї нічної норми (а не абсолютне значення). Корисна для раннього виявлення хвороби й відстеження фаз циклу."),
    ("Сатурація (SpO₂)", "Насиченість крові киснем уві сні. Норма ≥95%. Поодинокі заниження зазвичай артефакт вимірювання."),
    ("Фази сну", "Глибокий (фізичне відновлення), REM (пам'ять/емоції), легкий (перехідний). Здорова ніч: глибокий 13–20%, REM ~20–25%."),
    ("Резильєнтність", "Здатність тіла протистояти стресу й відновлюватись — від «обмеженої» до «виняткової». Зростає від стабільного сну, відновлення й помірної активності."),
    ("Судинний вік", "Орієнтовний «вік» твоїх судин за швидкістю пульсової хвилі. Нижчий за паспортний — добрий знак для серцево-судинної системи."),
]

# --- збірка детальних днів ---
sc_by = {parse_day(r["day"]): (r.get("contributors") or {}) for r in d_sleep}
rc_by = {parse_day(r["day"]): (r.get("contributors") or {}) for r in d_ready}
ac_by = {parse_day(r["day"]): (r.get("contributors") or {}) for r in d_act}
SLEEP_ORD = ["total_sleep", "efficiency", "restfulness", "rem_sleep", "deep_sleep", "latency", "timing"]
READY_ORD = ["previous_night", "sleep_balance", "sleep_regularity", "previous_day_activity",
             "activity_balance", "recovery_index", "resting_heart_rate", "hrv_balance", "body_temperature"]
ACT_ORD = ["meet_daily_targets", "stay_active", "move_every_hour", "training_frequency",
           "training_volume", "recovery_time"]


def hhmm(iso_str):
    if not iso_str:
        return None
    try:
        t = datetime.fromisoformat(iso_str)
        return f"{t.hour:02d}:{t.minute:02d}"
    except Exception:
        return None


def day_verdict(rv):
    if rv is None:
        return "Немає даних готовності за цей день."
    if rv >= 85:
        return "Чудовий день для навантаження — тіло добре відновлене."
    if rv >= 70:
        return "Робочий день: помірне навантаження ок, але не перевантажуйся."
    return "День для відновлення: легше тренування, більше сну, менше стимуляторів."


# додаткові показники для щоденної картки (як у застосунку Oura)
stress_by = {parse_day(r["day"]): r for r in d_stress}
resil_by = {parse_day(r["day"]): r.get("level") for r in d_resil}
act_full = {parse_day(r["day"]): r for r in d_act}
cva_by = {parse_day(r["day"]): r for r in d_cva}
bdi_by = {parse_day(r["day"]): (r.get("breathing_disturbance_index")) for r in d_spo2}
temp_trend = by_day(d_ready, "temperature_trend_deviation")

days_detail = []
for d in all_days:
    rv, sv, av = ready_score.get(d), sleep_score.get(d), act_score.get(d)
    nb = night.get(d, {})
    sd = stress_by.get(d, {})
    af = act_full.get(d, {})
    cv = cva_by.get(d, {})
    notes = []
    for cat, m in (("sleep", sc_by.get(d, {})), ("readiness", rc_by.get(d, {})), ("activity", ac_by.get(d, {}))):
        for k, v in m.items():
            if isinstance(v, (int, float)) and v < 70 and k in CONTRIB:
                notes.append({"sev": "alert" if v < 55 else "warn",
                              "title": CONTRIB[k]["name"],
                              "text": CONTRIB[k]["fix"], "score": v})
    notes.sort(key=lambda x: x["score"])
    notes = notes[:5]
    if not notes and rv and rv >= 85:
        notes = [{"sev": "good", "title": "Збалансований день",
                  "text": nbsp("Усі основні складові в нормі. Тримай поточний режим."), "score": 100}]
    days_detail.append({
        "day": iso(d), "wd": WD[d.weekday()],
        "scores": {"readiness": rv, "sleep": sv, "activity": av},
        "verdict": nbsp(day_verdict(rv)),
        "sc": {
            "sleep": [{"k": k, "v": sc_by.get(d, {}).get(k)} for k in SLEEP_ORD if sc_by.get(d, {}).get(k) is not None],
            "readiness": [{"k": k, "v": rc_by.get(d, {}).get(k)} for k in READY_ORD if rc_by.get(d, {}).get(k) is not None],
            "activity": [{"k": k, "v": ac_by.get(d, {}).get(k)} for k in ACT_ORD if ac_by.get(d, {}).get(k) is not None],
        },
        "vitals": {
            "total_h": round(nb["total_h"], 1) if nb.get("total_h") else None,
            "efficiency": nb.get("efficiency"), "hrv": nb.get("hrv"), "rhr": nb.get("rhr"),
            "breath": round(nb["breath"], 1) if nb.get("breath") else None,
            "deep_h": round(nb["deep_h"], 1) if nb.get("deep_h") is not None else None,
            "rem_h": round(nb["rem_h"], 1) if nb.get("rem_h") is not None else None,
            "light_h": round(nb["light_h"], 1) if nb.get("light_h") is not None else None,
            "bedtime": hhmm(nb.get("bedtime")), "wake": hhmm(nb.get("wake")),
            "temp": temp_dev.get(d), "spo2": round(spo2[d], 1) if spo2.get(d) else None,
            "steps": steps.get(d), "active_cal": active_cal.get(d),
            "restless": nb.get("restless"), "avg_hr": nb.get("avg_hr"),
            # стрес
            "stress_high": sd.get("stress_high"), "recovery_high": sd.get("recovery_high"),
            "day_summary": sd.get("day_summary"),
            # активність (повна, як у Oura)
            "total_cal": af.get("total_calories"), "target_cal": af.get("target_calories"),
            "walk_m": af.get("equivalent_walking_distance"), "sedentary": af.get("sedentary_time"),
            "high_act": af.get("high_activity_time"), "med_act": af.get("medium_activity_time"),
            "resting": af.get("resting_time"), "inactivity": af.get("inactivity_alerts"),
            # відновлення / температура / серце
            "resilience": resil_by.get(d), "vascular_age": cv.get("vascular_age"),
            "pwv": cv.get("pulse_wave_velocity"), "bdi": bdi_by.get(d),
            "temp_trend": temp_trend.get(d),
        },
        "insights": notes,
    })
days_detail.reverse()  # найновіші зверху

# --- тижневі агрегати ---
from collections import defaultdict
wk = defaultdict(list)
for d in all_days:
    wk[d.isocalendar()[:2]] = wk[d.isocalendar()[:2]] + [d]


def wk_avg(days, dct):
    return mean([dct.get(x) for x in days])


week_keys = sorted(wk.keys())
week_avgs = {k: wk_avg(wk[k], ready_score) for k in week_keys}
weeks_detail = []
for i, key in enumerate(sorted(week_keys, reverse=True)):
    days = sorted(wk[key])
    a = {
        "readiness": wk_avg(days, ready_score), "sleep": wk_avg(days, sleep_score),
        "activity": wk_avg(days, act_score), "total_h": wk_avg(days, n_total),
        "eff": wk_avg(days, n_eff), "rhr": wk_avg(days, n_rhr), "hrv": wk_avg(days, n_hrv),
    }
    rv_days = [(x, ready_score.get(x)) for x in days if ready_score.get(x) is not None]
    best = max(rv_days, key=lambda t: t[1]) if rv_days else (None, None)
    worst = min(rv_days, key=lambda t: t[1]) if rv_days else (None, None)
    d0, d1 = days[0], days[-1]
    label = f"Тиждень {key[1]}"
    rng = f"{d0.day} {MON[d0.month-1]} – {d1.day} {MON[d1.month-1]}"
    # тижневий висновок
    wins = []
    if a["readiness"] is not None:
        base = baseline(ready_score)
        if a["readiness"] >= 85:
            wins.append(("good", f"Сильний тиждень: середня готовність {a['readiness']:.0f}."))
        elif base and a["readiness"] < base - 5:
            wins.append(("warn", f"Готовність {a['readiness']:.0f} — нижче твого звичного. Більше сну й відновлення."))
        else:
            wins.append(("warn", f"Готовність {a['readiness']:.0f} — робочий рівень."))
    if a["total_h"] is not None and a["total_h"] < 7:
        wins.append(("warn", f"Сон у середньому {a['total_h']:.1f} год — замало, цілься в 7–9."))
    if a["activity"] is not None and a["activity"] >= 85:
        wins.append(("good", f"Активність {a['activity']:.0f} — чудовий тонус."))
    weeks_detail.append({
        "label": label, "range": rng, "n": len(days),
        "avg": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in a.items()},
        "best": {"day": iso(best[0]) if best[0] else None, "wd": WD[best[0].weekday()] if best[0] else "", "score": best[1]},
        "worst": {"day": iso(worst[0]) if worst[0] else None, "wd": WD[worst[0].weekday()] if worst[0] else "", "score": worst[1]},
        "insight": [{"sev": s, "text": nbsp(t)} for s, t in wins],
    })

bundle = {
    "meta": {
        "date_from": date_from, "date_to": date_to, "days": len(all_days),
        "ring": ring.get("hardware_type", ""), "age": age, "sex": sex,
        "vascular_age": vasc_last, "resilience": resil_ua,
        "workouts": n_workouts, "generated": generated,
    },
    "kpis": kpis,
    "recs": recs,
    "series": payload,
    "days": days_detail,
    "weeks": weeks_detail,
    "glossary": {"contrib": CONTRIB, "metrics": [{"name": nbsp(n), "desc": nbsp(d)} for n, d in METRICS]},
}
with open(os.path.join(HERE, "dashboard_data.json"), "w", encoding="utf-8") as f:
    json.dump(bundle, f, ensure_ascii=False)

# як .js — щоб index.html відкривався подвійним кліком (file://) без сервера
with open(os.path.join(HERE, "dashboard_data.js"), "w", encoding="utf-8") as f:
    f.write("window.DASH = " + json.dumps(bundle, ensure_ascii=False) + ";")

print(f"✅ Дашборд: {OUT}")
print(f"✅ Data-bundle: dashboard_data.json")
print(f"   Рекомендацій: {len(recs)}  ·  днів даних: {len(all_days)}")
