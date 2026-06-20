#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерує next_week_plan.js (план на тиждень) з реальних кореляцій/трендів Oura.
Детерміновано, локально, без ключів. Запускається щопонеділка (launchd) або вручну.

Запуск: python3 coach_plan.py
"""
import json
import os
import subprocess
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
MON = ["січня", "лютого", "березня", "квітня", "травня", "червня",
       "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]


def fmt(d):
    return f"{d.day} {MON[d.month - 1]}"


def nbsp(s):
    import re
    return re.sub(r"(^|[\s(])([А-Яа-яІіЇїЄєҐґA-Za-z0-9]{1,2})\s+",
                  lambda m: m.group(1) + m.group(2) + " ", s)


# 1. статистика
stats = json.loads(subprocess.run([sys.executable, os.path.join(HERE, "coach_analyze.py")],
                                  capture_output=True, text=True, check=True).stdout)
lw = stats["trends"]["last_week"]
pw = stats["trends"]["prev_week"]
corr = stats["correlations"]
wd = stats["weekday"]
se = stats["stress_effect"]

# цикл (з готового dashboard_data.json)
try:
    cyc = json.load(open(os.path.join(HERE, "dashboard_data.json"))).get("cycle", {})
except Exception:
    cyc = {}


def delta_word(cur, prev, good_up=True, unit="", nd=0):
    if cur is None or prev is None:
        return ""
    d = cur - prev
    if abs(d) < (abs(prev) * 0.02 + 1e-9):
        return f"тримається ({cur:.{nd}f}{unit})"
    up = d > 0
    word = "зросла" if up else "впала"
    return f"{word} ({prev:.{nd}f}→{cur:.{nd}f}{unit})"


def r(key):
    c = corr.get(key)
    return c["r"] if c else None


# 2. підсумок тижня
parts = []
parts.append(f"Готовність {delta_word(lw['readiness'], pw['readiness'])}, "
             f"пульс спокою {delta_word(lw['rhr'], pw['rhr'], good_up=False)}, "
             f"HRV {delta_word(lw['hrv'], pw['hrv'])}.")
parts.append(f"Сон у середньому {lw['total_h']:.1f} год; активність {delta_word(lw['activity'], pw['activity'])}.")
stress_min = round((lw['stress'] or 0) / 60)
stress_min_prev = round((pw['stress'] or 0) / 60)
parts.append(f"Денний стрес {stress_min} хв за день (тижнем раніше {stress_min_prev}).")
summary = " ".join(parts)

# 3. закономірності (з реальних r)
patterns = []
if r("stress→next_hrv") is not None and r("stress→next_hrv") <= -0.3:
    hrv_s = se["next_hrv"]["after_stressful"]; hrv_c = se["next_hrv"]["after_calm"]
    rd_s = se["next_readiness"]["after_stressful"]; rd_c = se["next_readiness"]["after_calm"]
    drop = round((1 - hrv_s / hrv_c) * 100) if hrv_c else 0
    patterns.append({"sev": "alert", "title": "Стрес удень — головний важіль",
        "text": f"Після стресових днів наступного ранку готовність у середньому {rd_c - rd_s:.1f} бала нижча, "
                f"а HRV на {drop}% менша ({hrv_s:.0f} проти {hrv_c:.0f}). Кореляція r = {r('stress→next_hrv')} — "
                f"найсильніший зв'язок у твоїх даних."})
if r("total_h→readiness_same") is not None and r("total_h→readiness_same") >= 0.3:
    patterns.append({"sev": "good", "title": "Більше сну — вища готовність",
        "text": f"Тривалість сну стабільно тягне готовність угору (r = {r('total_h→readiness_same')}). "
                f"Це твій найсильніший позитивний важіль; робочий мінімум — 7.5 год."})
if r("bedtime→deep_same") is not None and r("bedtime→deep_same") <= -0.2:
    patterns.append({"sev": "warn", "title": "Раніший відбій — більше глибокого сну",
        "text": f"Що пізніше лягаєш — то менше глибокої фази (r = {r('bedtime→deep_same')}). "
                f"Вікно відбою впливає на фізичне відновлення напряму."})
# слабкі дні
worst_rd = min(wd.items(), key=lambda kv: kv[1]["readiness"] if kv[1]["readiness"] else 99)
worst_sl = min(wd.items(), key=lambda kv: kv[1]["sleep"] if kv[1]["sleep"] else 99)
peak_st = max(wd.items(), key=lambda kv: kv[1]["stress"] if kv[1]["stress"] else -1)
patterns.append({"sev": "warn", "title": "Слабкі дні тижня",
    "text": f"Найнижча готовність — {worst_rd[0]} ({worst_rd[1]['readiness']:.0f}). "
            f"Найгірший сон — {worst_sl[0]} ({worst_sl[1]['sleep']:.0f}). "
            f"Пік стресу — {peak_st[0]}. Сюди варто прикласти увагу."})

# закономірність по циклу
CYC_NOTE = {
    "luteal": ("warn", "Ти в лютеїновій фазі — це впливає на тиждень",
               "Очікувано нижча HRV і вищий пульс спокою — це гормони, не втрата форми. Не лякайся «гірших» цифр; пріоритет — відновлення."),
    "menstrual": ("warn", "Менструальна фаза — дай собі легші дні",
                  "Енергія й готовність зазвичай нижчі на початку циклу. Це нормально; ніжний рух краще за інтенсив."),
    "follicular": ("good", "Фолікулярна фаза — твоє вікно енергії",
                   "HRV і готовність зазвичай найвищі. Хороший тиждень, щоб планувати інтенсивні тренування й складні задачі."),
    "ovulation": ("good", "Овуляторне вікно — енергія на піку",
                  "Можна тримати навантаження; на силових слідкуй за технікою (зв'язки трохи розслабленіші)."),
}
if cyc.get("tracked") and cyc.get("phase") in CYC_NOTE:
    sv, ti, tx = CYC_NOTE[cyc["phase"]]
    ps = cyc.get("phase_stats", {})
    extra = ""
    if cyc["phase"] == "luteal" and ps.get("luteal", {}).get("hrv") and ps.get("follicular", {}).get("hrv"):
        extra = f" У тебе HRV у лютеїновій ~{ps['luteal']['hrv']} проти ~{ps['follicular']['hrv']} у фолікулярній."
    patterns.append({"sev": sv, "title": ti,
        "text": f"День циклу {cyc['cur_day']}, наступні місячні ~через {cyc['days_to_next']} дн.{extra} {tx}"})

# 4. план
plan = []
n = 1
if r("stress→next_hrv") is not None and r("stress→next_hrv") <= -0.3:
    plan.append({"n": n, "icon": "🧘", "title": f"Стрес-гігієна у пікові дні ({peak_st[0]})",
        "why": "Стресовий день коштує тобі балів готовності й HRV наступного ранку — це твій найвпливовіший зв'язок.",
        "how": f"Дві паузи по 5 хв ({peak_st[0]} — твій пік): дихання 4-7-8 або коротка прогулянка, плюс одна ввечері."}); n += 1
if (lw["total_h"] or 0) < 7.7:
    plan.append({"n": n, "icon": "😴", "title": "Тримати сон не менше 7.5 години",
        "why": "Найсильніший позитивний зв'язок із готовністю у твоїх даних.",
        "how": "Відбій не пізніше 23:15; екран геть за годину до сну; спальня 18–19°C."}); n += 1
plan.append({"n": n, "icon": "⏰", "title": f"Витягнути {worst_sl[0]}",
    "why": f"{worst_sl[0]} — твій найгірший сон, що псує старт наступного дня.",
    "how": f"У {worst_sl[0]} лягай раніше (до 23:00); без кави після обіду напередодні."}); n += 1
if lw["activity"] is not None and pw["activity"] is not None and lw["activity"] < pw["activity"] - 5:
    plan.append({"n": n, "icon": "🏃", "title": "Повернути рух",
        "why": f"Активність {delta_word(lw['activity'], pw['activity'])}, а готовність висока — є ресурс.",
        "how": "3 прогулянки по 25–30 хв або 2 легкі тренування; не пізніше 19:00."}); n += 1

# дія за фазою циклу
CYC_PLAN = {
    "luteal": ("🌙", "Підлаштуватися під лютеїнову фазу",
               "Гормони знижують HRV і піднімають пульс — це норма.",
               "Більше сну, нижча інтенсивність у другій половині тижня, менше кофеїну й алкоголю. Силу/інтенсив постав на початок тижня."),
    "menstrual": ("🩸", "Легший старт у менструальну фазу",
                  "Енергія й готовність зазвичай нижчі в перші дні.",
                  "Перші 1–2 дні — ходьба, йога, розтяжка замість інтенсиву. Тепло, залізо в їжі, відпочинок без провини."),
    "follicular": ("🌱", "Скористатися фолікулярним вікном",
                   "Зараз твій пік енергії та найкраща переносимість навантаження.",
                   "Заплануй найважчі тренування й найскладніші задачі саме на цей тиждень."),
    "ovulation": ("✨", "Овуляторне вікно — енергія висока",
                  "Можна тримати навантаження, але зв'язки трохи розслабленіші.",
                  "Інтенсив ок; на силових слідкуй за технікою, добре розминайся, гідратація."),
}
if cyc.get("tracked") and cyc.get("phase") in CYC_PLAN:
    ic, ti, wy, hw = CYC_PLAN[cyc["phase"]]
    plan.append({"n": n, "icon": ic, "title": ti, "why": wy, "how": hw}); n += 1

# 5. ціль
goal_rd = round((lw["readiness"] or 85)) + 1
goal_hrv = round((lw["hrv"] or 38)) + 2
goal = (f"Середня готовність ≥ {goal_rd} і HRV ≥ {goal_hrv} наступного тижня — "
        f"насамперед через менший денний стрес ({peak_st[0]}).")

today = date.today()
plan_obj = {
    "generated": today.strftime("%Y-%m-%d %H:%M"),
    "week_reviewed": f"{fmt(today - timedelta(days=7))} – {fmt(today - timedelta(days=1))}",
    "next_week": f"{fmt(today)} – {fmt(today + timedelta(days=6))}",
    "by": "Дані-двигун на твоїх кореляціях Oura · оновлюється щопонеділка",
    "summary": nbsp(summary),
    "patterns": [{"sev": p["sev"], "title": nbsp(p["title"]), "text": nbsp(p["text"])} for p in patterns],
    "plan": [{"n": a["n"], "icon": a["icon"], "title": nbsp(a["title"]),
              "why": nbsp(a["why"]), "how": nbsp(a["how"])} for a in plan],
    "goal": nbsp(goal),
}

with open(os.path.join(HERE, "next_week_plan.js"), "w", encoding="utf-8") as f:
    f.write("window.PLAN = " + json.dumps(plan_obj, ensure_ascii=False, indent=2) + ";")
with open(os.path.join(HERE, "next_week_plan.json"), "w", encoding="utf-8") as f:
    json.dump(plan_obj, f, ensure_ascii=False, indent=2)

print(f"✅ План оновлено: {plan_obj['week_reviewed']} → {plan_obj['next_week']}")
print(f"   Закономірностей: {len(patterns)} · дій: {len(plan)}")
