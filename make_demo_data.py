#!/usr/bin/env python3
"""
Демо-дані для дашборда — щоб подивитися, як усе виглядає, ще не маючи кільця.

Генерує вигаданий, але правдоподібний набір даних за пів року: сон, готовність,
активність, стрес, стійкість, цикл. Жодного стосунку до реальних людей.

Запуск:
    python3 make_demo_data.py          # створить теку data/ з демо-даними
    python3 make_demo_data.py --force  # перезапише наявні дані (обережно!)
    python3 make_demo_data.py --days 90

Далі, як завжди:
    python3 build_dashboard.py && python3 serve.py
"""

import argparse
import json
import math
import os
import random
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

RNG = random.Random(20260921)  # фіксоване зерно — дані відтворювані


def uid(prefix, i):
    return f"{prefix}-demo-{i:04d}-0000-0000-000000000000"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def iso_z(d, hour, minute=0):
    return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00.000+00:00"


def build(days: int):
    today = date.today()
    start = today - timedelta(days=days - 1)
    all_days = [start + timedelta(days=i) for i in range(days)]

    # --- цикл: період кожні ~29 днів, з невеликим розкидом ---
    period_starts = []
    d = start + timedelta(days=RNG.randint(2, 8))
    while d <= today:
        period_starts.append(d)
        d = d + timedelta(days=RNG.choice([27, 28, 29, 29, 30, 31]))
    # Зсуваємо так, щоб «сьогодні» припадало приблизно на 18-й день циклу:
    # тоді на графіку видно і фолікулярну фазу, і підйом температури в лютеїновій.
    if period_starts:
        shift = (today - timedelta(days=17) - period_starts[-1]).days
        period_starts = [p + timedelta(days=shift) for p in period_starts]
        period_starts = [p for p in period_starts if p >= start - timedelta(days=5)]

    def cycle_day(day):
        past = [p for p in period_starts if p <= day]
        return (day - past[-1]).days + 1 if past else None

    def temp_shift(day):
        """Лютеїнова фаза тепліша — це те, що видно на температурній кривій."""
        cd = cycle_day(day)
        if cd is None:
            return 0.0
        ov = 15
        if cd <= 5:
            return -0.10
        if cd < ov - 1:
            return -0.15
        if cd <= ov + 1:
            return 0.05
        return 0.30

    out = {k: [] for k in (
        "daily_sleep", "daily_readiness", "daily_activity", "daily_spo2",
        "daily_stress", "daily_resilience", "daily_cardiovascular_age",
        "sleep", "workout", "enhanced_tag")}

    for i, day in enumerate(all_days):
        weekend = day.weekday() >= 5
        season = math.sin(i / 34.0)  # повільна хвиля — «форма» за місяці
        noise = RNG.gauss(0, 1)

        # --- сон ---
        total_sleep = int(clamp(
            7.1 * 3600 + season * 1100 + (1500 if weekend else 0) + noise * 1600,
            4.4 * 3600, 9.3 * 3600))
        deep = int(total_sleep * clamp(RNG.gauss(0.19, 0.035), 0.10, 0.28))
        rem = int(total_sleep * clamp(RNG.gauss(0.22, 0.04), 0.11, 0.32))
        light = total_sleep - deep - rem
        awake = int(clamp(RNG.gauss(2100, 700), 500, 4600))
        time_in_bed = total_sleep + awake
        efficiency = int(clamp(round(total_sleep / time_in_bed * 100), 72, 98))
        latency = int(clamp(RNG.gauss(760, 380), 120, 2400))

        hrv = int(clamp(RNG.gauss(52, 9) + season * 5 - temp_shift(day) * 18, 20, 96))
        rhr = round(clamp(RNG.gauss(57, 3.4) - season * 1.4 + temp_shift(day) * 5, 47, 72), 1)
        lowest_hr = int(clamp(rhr - RNG.uniform(2, 5), 42, 68))
        breath = round(clamp(RNG.gauss(14.6, 0.8), 12.2, 17.4), 2)

        sleep_score = int(clamp(
            58 + (total_sleep - 6.4 * 3600) / 220 + (efficiency - 85) * 0.8 + noise * 3,
            41, 97))

        bed_start = datetime.combine(day - timedelta(days=1), datetime.min.time()) \
            + timedelta(hours=22, minutes=RNG.randint(0, 110))
        bed_end = bed_start + timedelta(seconds=time_in_bed)

        out["daily_sleep"].append({
            "id": uid("ds", i),
            "contributors": {
                "deep_sleep": int(clamp(deep / 3600 * 62 + 24, 20, 100)),
                "efficiency": int(clamp(efficiency + 4, 30, 100)),
                "latency": int(clamp(102 - latency / 26, 25, 100)),
                "rem_sleep": int(clamp(rem / 3600 * 58 + 26, 20, 100)),
                "restfulness": int(clamp(RNG.gauss(74, 13), 28, 100)),
                "timing": int(clamp(RNG.gauss(85, 14), 30, 100)),
                "total_sleep": int(clamp(total_sleep / 3600 * 12.4, 25, 100)),
            },
            "day": day.isoformat(),
            "score": sleep_score,
            "timestamp": iso_z(day, 0),
        })

        # --- готовність ---
        tdev = round(temp_shift(day) + RNG.gauss(0, 0.09), 2)
        ready_score = int(clamp(
            sleep_score * 0.55 + hrv * 0.32 + 14 - abs(tdev) * 16 + noise * 2.2, 40, 96))
        out["daily_readiness"].append({
            "id": uid("dr", i),
            "contributors": {
                "activity_balance": int(clamp(RNG.gauss(83, 12), 35, 100)),
                "body_temperature": int(clamp(100 - abs(tdev) * 52, 25, 100)),
                "hrv_balance": int(clamp(RNG.gauss(76, 15), 25, 100)),
                "previous_day_activity": int(clamp(RNG.gauss(87, 11), 40, 100)),
                "previous_night": int(clamp(sleep_score + RNG.gauss(0, 5), 35, 100)),
                "recovery_index": int(clamp(RNG.gauss(72, 19), 20, 100)),
                "resting_heart_rate": int(clamp(104 - (rhr - 50) * 3.1, 25, 100)),
                "sleep_balance": int(clamp(RNG.gauss(80, 13), 30, 100)),
                "sleep_regularity": int(clamp(RNG.gauss(74, 16), 25, 100)),
            },
            "day": day.isoformat(),
            "score": ready_score,
            "temperature_deviation": tdev,
            "temperature_trend_deviation": round(tdev * 0.7, 2),
            "timestamp": iso_z(day, 0),
        })

        # --- активність ---
        steps = int(clamp(RNG.gauss(8600 if not weekend else 6400, 2900), 1400, 21000))
        active_cal = int(steps * RNG.uniform(0.040, 0.058))
        out["daily_activity"].append({
            "id": uid("da", i),
            "active_calories": active_cal,
            "average_met_minutes": round(RNG.uniform(1.2, 1.9), 4),
            "contributors": {
                "meet_daily_targets": int(clamp(steps / 110, 20, 100)),
                "move_every_hour": int(clamp(RNG.gauss(88, 12), 35, 100)),
                "recovery_time": int(clamp(RNG.gauss(90, 12), 40, 100)),
                "stay_active": int(clamp(steps / 108, 20, 100)),
                "training_frequency": int(clamp(RNG.gauss(70, 20), 15, 100)),
                "training_volume": int(clamp(RNG.gauss(76, 17), 20, 100)),
            },
            "day": day.isoformat(),
            "equivalent_walking_distance": int(steps * RNG.uniform(0.62, 0.74)),
            "high_activity_met_minutes": int(clamp(RNG.gauss(24, 20), 0, 120)),
            "high_activity_time": int(clamp(RNG.gauss(900, 700), 0, 4200)),
            "inactivity_alerts": RNG.randint(0, 4),
            "low_activity_met_minutes": int(clamp(RNG.gauss(150, 45), 30, 300)),
            "low_activity_time": int(clamp(RNG.gauss(16000, 4000), 4000, 30000)),
            "medium_activity_met_minutes": int(clamp(RNG.gauss(90, 50), 0, 280)),
            "medium_activity_time": int(clamp(RNG.gauss(3400, 1800), 0, 11000)),
            "meters_to_target": RNG.choice([0, 0, 0, 1200, 2600, 4100]),
            "non_wear_time": int(clamp(RNG.gauss(1500, 1400), 0, 9000)),
            "resting_time": int(clamp(RNG.gauss(31000, 5000), 16000, 46000)),
            "score": int(clamp(steps / 108 + RNG.gauss(4, 6), 30, 98)),
            "sedentary_met_minutes": int(clamp(RNG.gauss(9, 4), 1, 26)),
            "sedentary_time": int(clamp(RNG.gauss(29000, 6000), 12000, 48000)),
            "steps": steps,
            "target_calories": 450,
            "target_meters": 9000,
            "timestamp": iso_z(day, 4),
            "total_calories": active_cal + int(RNG.gauss(1480, 90)),
        })

        # --- стрес ---
        stress_high = int(clamp(RNG.gauss(7000, 4200) + temp_shift(day) * 6000, 0, 27000))
        out["daily_stress"].append({
            "id": uid("dst", i),
            "day": day.isoformat(),
            "day_summary": RNG.choice(["restored", "normal", "normal", "stressful"]),
            "recovery_high": int(clamp(RNG.gauss(12000, 5000), 0, 34000)),
            "stress_high": stress_high,
        })

        # --- стійкість ---
        out["daily_resilience"].append({
            "id": uid("dre", i),
            "day": day.isoformat(),
            "contributors": {
                "sleep_recovery": round(clamp(RNG.gauss(70, 16), 18, 99), 1),
                "daytime_recovery": round(clamp(RNG.gauss(64, 18), 15, 99), 1),
                "stress": round(clamp(RNG.gauss(58, 17), 12, 96), 1),
            },
            "level": RNG.choice(["adequate", "solid", "solid", "strong", "strong"]),
        })

        # --- кисень і судинний вік ---
        out["daily_spo2"].append({
            "id": uid("dsp", i),
            "breathing_disturbance_index": RNG.randint(1, 9),
            "day": day.isoformat(),
            "spo2_percentage": {"average": round(clamp(RNG.gauss(96.4, 0.7), 93.4, 99.2), 2)},
        })
        if i % 7 == 3:
            out["daily_cardiovascular_age"].append({
                "id": uid("dcv", i),
                "day": day.isoformat(),
                "pulse_wave_velocity": round(RNG.uniform(5.9, 7.4), 3),
                "vascular_age": RNG.randint(26, 31),
            })

        # --- детальний сон ---
        out["sleep"].append({
            "id": uid("sl", i),
            "average_breath": breath,
            "average_heart_rate": round(rhr + RNG.uniform(0.4, 2.2), 1),
            "average_hrv": hrv,
            "awake_time": awake,
            "bedtime_end": bed_end.strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
            "bedtime_start": bed_start.strftime("%Y-%m-%dT%H:%M:%S.000+00:00"),
            "day": day.isoformat(),
            "deep_sleep_duration": deep,
            "efficiency": efficiency,
            "latency": latency,
            "light_sleep_duration": light,
            "low_battery_alert": False,
            "lowest_heart_rate": lowest_hr,
            "period": 0,
            "readiness_score_delta": RNG.randint(-6, 6),
            "rem_sleep_duration": rem,
            "restless_periods": RNG.randint(6, 34),
            "sleep_algorithm_version": "v2",
            "sleep_score_delta": RNG.randint(-6, 6),
            "time_in_bed": time_in_bed,
            "total_sleep_duration": total_sleep,
            "type": "long_sleep",
            "ring_id": None,
        })

        # --- тренування ---
        if RNG.random() < (0.5 if weekend else 0.3):
            act = RNG.choice(["walking", "running", "yoga", "strength_training",
                              "cycling", "swimming", "pilates"])
            h = RNG.randint(8, 19)
            dur = RNG.randint(25, 80)
            st = datetime.combine(day, datetime.min.time()) + timedelta(hours=h)
            out["workout"].append({
                "id": uid("wo", i),
                "activity": act,
                "calories": round(dur * RNG.uniform(4.2, 9.5), 1),
                "day": day.isoformat(),
                "distance": None,
                "end_datetime": (st + timedelta(minutes=dur)).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "intensity": RNG.choice(["easy", "moderate", "moderate", "hard"]),
                "label": None,
                "source": "manual",
                "start_datetime": st.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            })

    # --- теги менструації (на них тримається вкладка «Цикл») ---
    for n, ps in enumerate(period_starts):
        for k in range(RNG.randint(3, 5)):
            d2 = ps + timedelta(days=k)
            if d2 > today:
                break
            out["enhanced_tag"].append({
                "id": uid("tg", n * 10 + k),
                "tag_type_code": "tag_generic_period",
                "start_time": iso_z(d2, 9),
                "end_time": None,
                "start_day": d2.isoformat(),
                "end_day": None,
                "comment": None,
                "custom_name": None,
            })

    out["personal_info"] = {
        "id": "demo-user",
        "age": 34,
        "weight": 62.0,
        "height": 1.68,
        "biological_sex": "female",
        "email": "demo@example.com",
    }
    out["ring_configuration"] = [{
        "id": "demo-ring",
        "color": "stealth",
        "design": "heritage",
        "firmware_version": "2.9.44",
        "hardware_type": "gen4",
        "set_up_at": iso_z(start - timedelta(days=40), 12),
        "size": 8,
    }]
    return out


def main():
    ap = argparse.ArgumentParser(description="Демо-дані для дашборда Oura")
    ap.add_argument("--days", type=int, default=180, help="скільки днів згенерувати")
    ap.add_argument("--force", action="store_true", help="перезаписати наявні дані")
    a = ap.parse_args()

    if os.path.isdir(DATA) and os.listdir(DATA) and not a.force:
        sys.exit(
            "У теці data/ вже щось лежить, і я не хочу це затерти.\n"
            "Якщо там твої справжні дані з кільця - не запускай цей скрипт.\n"
            "Якщо це не шкода втратити, додай --force."
        )

    os.makedirs(DATA, exist_ok=True)
    demo = build(max(30, a.days))
    for name, rows in demo.items():
        with open(os.path.join(DATA, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)

    print(f"Готово: демо-дані за {a.days} днів лежать у data/")
    print("Далі:  python3 build_dashboard.py  і  python3 serve.py")
    print("Коли захочеш свої справжні дані - видали теку data/ і зроби python3 oura_export.py")


if __name__ == "__main__":
    main()
