#!/usr/bin/env python3
"""
Create a modified dataset with realistic consumption spikes.

Adds:
- EV charging events (11-22 kW, 2-4 hours duration)
- Heat pump winter spikes (5-8 kW during cold hours)
- Random appliance combinations (3-5 kW)

This simulates realistic peak shaving scenarios.
"""

import pandas as pd
import numpy as np
import sys

def add_ev_charging_events(df, num_events=15, charge_power_kw=11, duration_hours=3):
    """
    Add EV charging events to the dataset.

    Args:
        df: DataFrame with consumption data
        num_events: Number of charging events per month
        charge_power_kw: Charging power (kW) - typical home charger is 11 kW
        duration_hours: Hours per charging session
    """
    df = df.copy()

    # Group by month
    df['year_month'] = df['timestamp'].dt.to_period('M')

    for month in df['year_month'].unique():
        month_mask = df['year_month'] == month
        month_indices = df[month_mask].index.tolist()

        if len(month_indices) < duration_hours * num_events:
            continue

        # Add charging events
        for _ in range(num_events):
            # Random start time during E.ON hours (to create peaks that matter)
            # Focus on evening hours (17-22) when people typically charge
            evening_hours = df[month_mask & (df['timestamp'].dt.hour >= 17) & (df['timestamp'].dt.hour <= 22)]

            if len(evening_hours) == 0:
                continue

            start_idx = np.random.choice(evening_hours.index)

            # Add charging load for duration_hours
            for hour_offset in range(duration_hours):
                idx = start_idx + hour_offset
                if idx in df.index:
                    # Add EV charging to existing consumption
                    df.loc[idx, 'load_kwh'] += charge_power_kw

    df.drop(columns=['year_month'], inplace=True)
    return df


def add_heat_pump_spikes(df, avg_winter_power_kw=6, spike_power_kw=8):
    """
    Add heat pump consumption spikes during winter months.

    Args:
        df: DataFrame with consumption data
        avg_winter_power_kw: Average heat pump power during winter
        spike_power_kw: Spike power during very cold hours
    """
    df = df.copy()

    # Winter months: November - March
    winter_months = [11, 12, 1, 2, 3]

    for idx, row in df.iterrows():
        month = row['timestamp'].month
        hour = row['timestamp'].hour

        if month in winter_months:
            # Heat pump runs more during night and morning (heating before wake-up)
            if 4 <= hour <= 8:  # Morning heating
                # 30% chance of high spike
                if np.random.random() < 0.3:
                    df.loc[idx, 'load_kwh'] += spike_power_kw
                else:
                    df.loc[idx, 'load_kwh'] += avg_winter_power_kw
            elif 17 <= hour <= 23:  # Evening heating
                # 20% chance of high spike
                if np.random.random() < 0.2:
                    df.loc[idx, 'load_kwh'] += spike_power_kw
                else:
                    df.loc[idx, 'load_kwh'] += avg_winter_power_kw * 0.7
            else:
                # Background heating during day
                df.loc[idx, 'load_kwh'] += avg_winter_power_kw * 0.3

    return df


def add_appliance_spikes(df, spike_probability=0.05, spike_power_kw=4):
    """
    Add random appliance combination spikes (oven + dishwasher + washing machine, etc).

    Args:
        df: DataFrame with consumption data
        spike_probability: Probability of spike per hour
        spike_power_kw: Additional power during spike
    """
    df = df.copy()

    # More likely during E.ON hours (when people are home)
    for idx, row in df.iterrows():
        hour = row['timestamp'].hour

        if 6 <= hour <= 23:  # E.ON hours
            # Higher probability during meal times
            if hour in [7, 8, 18, 19, 20]:  # Breakfast and dinner
                prob = spike_probability * 3
            else:
                prob = spike_probability

            if np.random.random() < prob:
                # Random spike between 2-5 kW
                spike = np.random.uniform(2, spike_power_kw)
                df.loc[idx, 'load_kwh'] += spike

    return df


def main():
    """Create spike dataset."""

    print("=" * 80)
    print("CREATING SPIKE DATASET FOR TESTING")
    print("=" * 80)

    # Configuration
    input_file = "tibber_no_ev.csv"
    output_file = "tibber_with_spikes.csv"

    # Spike parameters
    ev_events_per_month = 15  # ~every other day
    ev_power_kw = 11          # 11 kW home charger
    ev_duration_hours = 3     # 3 hours per charge session

    heat_pump_avg_kw = 6      # Average heat pump winter consumption
    heat_pump_spike_kw = 8    # Heat pump spike during very cold hours

    appliance_spike_prob = 0.08  # 8% chance per hour during E.ON hours
    appliance_spike_kw = 4       # Up to 4 kW additional

    print(f"\n📂 Loading {input_file}...")
    df = pd.read_csv(input_file)
    df['timestamp'] = pd.to_datetime(df['timestamp_local'], utc=True).dt.tz_localize(None)

    print(f"✓ Loaded {len(df)} hours")
    print(f"\nOriginal consumption stats:")
    print(f"  Mean: {df['load_kwh'].mean():.2f} kW")
    print(f"  P95: {df['load_kwh'].quantile(0.95):.2f} kW")
    print(f"  P99: {df['load_kwh'].quantile(0.99):.2f} kW")
    print(f"  Max: {df['load_kwh'].max():.2f} kW")

    # Add spikes
    print(f"\n🔌 Adding EV charging events...")
    print(f"  Events per month: {ev_events_per_month}")
    print(f"  Charging power: {ev_power_kw} kW")
    print(f"  Duration: {ev_duration_hours} hours")
    df = add_ev_charging_events(df, ev_events_per_month, ev_power_kw, ev_duration_hours)

    print(f"\n🔥 Adding heat pump winter spikes...")
    print(f"  Average winter power: {heat_pump_avg_kw} kW")
    print(f"  Spike power: {heat_pump_spike_kw} kW")
    print(f"  Winter months: Nov-Mar")
    df = add_heat_pump_spikes(df, heat_pump_avg_kw, heat_pump_spike_kw)

    print(f"\n🏠 Adding random appliance spikes...")
    print(f"  Spike probability: {appliance_spike_prob*100:.1f}% per hour")
    print(f"  Spike power: up to {appliance_spike_kw} kW")
    df = add_appliance_spikes(df, appliance_spike_prob, appliance_spike_kw)

    # Calculate new stats
    print(f"\n📊 Modified consumption stats:")
    print(f"  Mean: {df['load_kwh'].mean():.2f} kW")
    print(f"  P95: {df['load_kwh'].quantile(0.95):.2f} kW")
    print(f"  P99: {df['load_kwh'].quantile(0.99):.2f} kW")
    print(f"  Max: {df['load_kwh'].max():.2f} kW")

    # Show February stats specifically
    feb_mask = (df['timestamp'] >= pd.Timestamp('2025-02-01')) & (df['timestamp'] < pd.Timestamp('2025-03-01'))
    feb_data = df[feb_mask]
    feb_eon = feb_data[(feb_data['timestamp'].dt.hour >= 6) & (feb_data['timestamp'].dt.hour <= 23)]

    print(f"\n📅 February 2025 (E.ON hours 06-23):")
    top3 = feb_eon.nlargest(3, 'load_kwh')
    avg_peak = top3['load_kwh'].mean()

    print(f"  Top 3 peaks: {top3['load_kwh'].values[0]:.2f}, {top3['load_kwh'].values[1]:.2f}, {top3['load_kwh'].values[2]:.2f} kW")
    print(f"  Average: {avg_peak:.2f} kW")
    print(f"  Effect tariff cost: {avg_peak * 60:.0f} SEK/month")
    print(f"  Timestamps:")
    for idx, row in top3.iterrows():
        print(f"    {row['timestamp']:%Y-%m-%d %H:%M}: {row['load_kwh']:.2f} kW")

    # Save
    print(f"\n💾 Saving to {output_file}...")
    # Drop the temporary timestamp column we added (keep original columns)
    df = df.drop(columns=['timestamp'])
    df.to_csv(output_file, index=False)
    print(f"✓ Saved {len(df)} hours")

    print("\n" + "=" * 80)
    print("✅ SPIKE DATASET CREATED SUCCESSFULLY")
    print("=" * 80)
    print(f"\nUse this file for testing:")
    print(f"  data_file = '{output_file}'")

    return 0


if __name__ == "__main__":
    sys.exit(main())
