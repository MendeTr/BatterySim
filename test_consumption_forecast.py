#!/usr/bin/env python3
"""Test consumption forecast logic."""

import pandas as pd

# Load data
df = pd.read_csv('tibber_no_ev.csv')
df['timestamp'] = pd.to_datetime(df['timestamp_local'], utc=True).dt.tz_localize(None)

# Filter to February
feb_mask = (df['timestamp'].dt.year == 2025) & (df['timestamp'].dt.month == 2)
feb_data = df[feb_mask]

print(f"February 2025: {len(feb_data)} hours")
print(f"\nConsumption by hour of day (Feb only):")
for hour in range(24):
    hour_data = feb_data[feb_data['timestamp'].dt.hour == hour]['load_kwh']
    if len(hour_data) > 0:
        print(f"  Hour {hour:02d}: mean={hour_data.mean():.2f} kW, max={hour_data.max():.2f} kW, count={len(hour_data)}")

# Now check what historical data would show at the START of February
print(f"\n\nHistorical patterns (Oct 2024 - Jan 2025) before Feb 1:")
pre_feb = df[df['timestamp'] < pd.Timestamp('2025-02-01')]
print(f"Historical hours: {len(pre_feb)}")
print(f"\nConsumption by hour of day (historical):")
for hour in [6, 7, 8, 18, 19, 20]:
    hour_data = pre_feb[pre_feb['timestamp'].dt.hour == hour]['load_kwh']
    if len(hour_data) > 0:
        print(f"  Hour {hour:02d}: mean={hour_data.mean():.2f} kW, max={hour_data.max():.2f} kW")
