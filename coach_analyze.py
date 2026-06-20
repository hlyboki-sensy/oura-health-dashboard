#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Рахує статистику й кореляції на даних Oura (з dashboard_data.json) →
друкує JSON, який Claude використовує, щоб скласти план на тиждень.

Детермінована математика тут; інтерпретація — на боці Claude.
Запуск: python3 coach_analyze.py
"""
import json
import os
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
B = json.load(open(os.path.join(HERE, "dashboard_data.json")))
days = list(reversed(B["days"]))  # хронологічно (старі → нові)


def bedtime_min(hhmm):
    if not hhmm:
        return None
    h, m = map(int, hhmm.split(":"))
    v = h * 60 + m
    return v + 24 * 60 if h < 12 else v  # після опівночі → +24год


# таблиця за датою
rows = {}
for d in days:
    v = d["vitals"]
    rows[d["day"]] = {
        "readiness": d["scores"]["readiness"], "sleep": d["scores"]["sleep"],
        "activity": d["scores"]["activity"], "total_h": v.get("total_h"),
        "deep_h": v.get("deep_h"), "rem_h": v.get("rem_h"), "eff": v.get("efficiency"),
        "hrv": v.get("hrv"), "rhr": v.get("rhr"), "breath": v.get("breath"),
        "steps": v.get("steps"), "stress": v.get("stress_high"), "recovery": v.get("recovery_high"),
        "bedtime": bedtime_min(v.get("bedtime")), "temp": v.get("temp"),
        "summary": v.get("day_summary"),
    }
dates = sorted(rows)


def col(name, dd):
    return [rows[x][name] for x in dd]


def pearson(xs, ys):
    pairs = [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None]
    n = len(pairs)
    if n < 8:
        return None
    sx = sum(a for a, _ in pairs); sy = sum(b for _, b in pairs)
    mx = sx / n; my = sy / n
    cov = sum((a - mx) * (b - my) for a, b in pairs)
    vx = sum((a - mx) ** 2 for a, _ in pairs); vy = sum((b - my) ** 2 for _, b in pairs)
    if vx == 0 or vy == 0:
        return None
    return {"r": round(cov / (vx * vy) ** 0.5, 2), "n": n}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


# ---- 1. тиждень vs попередній ----
last7 = dates[-7:]
prev7 = dates[-14:-7]
def block(dd):
    return {k: mean(col(k, dd)) for k in
            ["readiness", "sleep", "activity", "total_h", "hrv", "rhr", "steps", "stress"]}
trends = {"last_week": block(last7), "prev_week": block(prev7),
          "last_range": f"{last7[0]}…{last7[-1]}", "prev_range": f"{prev7[0]}…{prev7[-1]}"}

# ---- 2. кореляції (зсунуті, де треба «наступний день») ----
def shifted(name_today, name_next):
    xs, ys = [], []
    for i in range(len(dates) - 1):
        t = rows[dates[i]].get(name_today)
        nx = rows[dates[i + 1]].get(name_next)
        xs.append(t); ys.append(nx)
    return pearson(xs, ys)

def same(name_a, name_b):
    return pearson(col(name_a, dates), col(name_b, dates))

corr = {
    "bedtime→readiness_same":  same("bedtime", "readiness"),     # пізніше ліг → готовність тієї ночі
    "bedtime→deep_same":       same("bedtime", "deep_h"),
    "total_h→readiness_same":  same("total_h", "readiness"),
    "stress→next_hrv":         shifted("stress", "hrv"),         # стрес удень → HRV наступної ночі
    "stress→next_rhr":         shifted("stress", "rhr"),
    "stress→next_readiness":   shifted("stress", "readiness"),
    "steps→next_sleep":        shifted("steps", "sleep"),
    "steps→same_sleep":        same("steps", "sleep"),
    "activity→next_readiness": shifted("activity", "readiness"),
}

# ---- 3. патерн по днях тижня ----
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]
wd_acc = {i: {"readiness": [], "sleep": [], "steps": [], "stress": [], "bedtime": []} for i in range(7)}
for x in dates:
    wd = datetime.strptime(x, "%Y-%m-%d").weekday()
    for k in wd_acc[wd]:
        wd_acc[wd][k].append(rows[x][k])
weekday = {WD[i]: {k: mean(v) for k, v in wd_acc[i].items()} for i in range(7)}

# ---- 4. стресові vs спокійні дні: різниця в наступній ночі ----
def by_summary(metric_next):
    s_vals, n_vals = [], []
    for i in range(len(dates) - 1):
        summ = rows[dates[i]]["summary"]
        nxt = rows[dates[i + 1]].get(metric_next)
        if nxt is None:
            continue
        if summ == "stressful":
            s_vals.append(nxt)
        elif summ in ("normal", "restored"):
            n_vals.append(nxt)
    return {"after_stressful": mean(s_vals), "after_calm": mean(n_vals),
            "n_stressful": len(s_vals), "n_calm": len(n_vals)}

stress_effect = {"next_hrv": by_summary("hrv"), "next_rhr": by_summary("rhr"),
                 "next_readiness": by_summary("readiness")}

print(json.dumps({
    "days_total": len(dates), "trends": trends, "correlations": corr,
    "weekday": weekday, "stress_effect": stress_effect,
}, ensure_ascii=False, indent=2))
