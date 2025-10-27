#!/usr/bin/env python3
"""Check consumption during E.ON measurement hours (06:00-23:00)."""

import pandas as pd
from agents.consumption_analyzer import ConsumptionAnalyzer, DayType

# Load data
df = pd.read_csv('tibber_no_ev.csv')
df['timestamp'] = pd.to_datetime(df['timestamp_local'], utc=True).dt.tz_localize(None)

# Get historical data before Feb
historical = df[df['timestamp'] < pd.Timestamp('2025-02-01')].copy()

# Create analyzer
analyzer = ConsumptionAnalyzer(historical, 'load_kwh')

print('\n' + '='*80)
print('CONSUMPTION ANALYSIS - E.ON MEASUREMENT HOURS ONLY (06:00-23:00)')
print('='*80)
print('\nWEEKDAY HOURS:')
print('-'*80)
print(f"Hour   Mean    P90     P95     P99     Max     Risk")
print('-'*80)

for hour in range(6, 24):  # E.ON hours
    stats = analyzer.get_stats(hour, DayType.WEEKDAY)
    risk = analyzer.get_risk_level(hour, DayType.WEEKDAY)
    if stats:
        marker = " ← P95 > 5 kW!" if stats.p95_kw > 5.0 else ""
        print(f"{hour:02d}:00  {stats.mean_kw:5.2f}   {stats.p90_kw:5.2f}   {stats.p95_kw:5.2f}   {stats.p99_kw:5.2f}   {stats.max_kw:5.2f}   {risk:<8}{marker}")

print('\nWEEKEND HOURS:')
print('-'*80)
print(f"Hour   Mean    P90     P95     P99     Max     Risk")
print('-'*80)

for hour in range(6, 24):  # E.ON hours
    stats = analyzer.get_stats(hour, DayType.WEEKEND)
    risk = analyzer.get_risk_level(hour, DayType.WEEKEND)
    if stats:
        marker = " ← P95 > 5 kW!" if stats.p95_kw > 5.0 else ""
        print(f"{hour:02d}:00  {stats.mean_kw:5.2f}   {stats.p90_kw:5.2f}   {stats.p95_kw:5.2f}   {stats.p99_kw:5.2f}   {stats.max_kw:5.2f}   {risk:<8}{marker}")

print('\n' + '='*80)
print('SUMMARY')
print('='*80)

# Find all E.ON hours with P95 > 5.0
high_hours = []
for hour in range(6, 24):
    for day_type in [DayType.WEEKDAY, DayType.WEEKEND]:
        stats = analyzer.get_stats(hour, day_type)
        if stats and stats.p95_kw > 5.0:
            high_hours.append((hour, day_type, stats.p95_kw))

if high_hours:
    print(f"\nHours requiring peak shaving (P95 > 5.0 kW):")
    for hour, day_type, p95 in high_hours:
        print(f"  Hour {hour:02d}:00 {day_type.value}: P95 = {p95:.2f} kW")
else:
    print("\n⚠️  NO E.ON hours have P95 > 5.0 kW!")
    print("This means historical patterns don't show regular high peaks during measurement hours.")
    print("The 8-12 kW spikes happen at NIGHT (00-05, 23) when E.ON doesn't measure!")
