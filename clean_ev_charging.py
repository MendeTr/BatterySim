#!/usr/bin/env python3
"""
Script to remove Tesla daytime charging from historical Tibber data.

This adjusts historical consumption to reflect future behavior where Tesla
will only charge at night (00:00-06:00) due to effect tariff.

Usage:
    python clean_ev_charging.py input.csv output.csv [--ev-power 11.0] [--threshold 8.0]
"""

import pandas as pd
import argparse
import sys
from datetime import datetime

def clean_ev_charging(input_file, output_file, ev_power=11.0, threshold=8.0, dry_run=False):
    """
    Remove estimated Tesla charging from daytime hours (06:00-23:00).

    Args:
        input_file: Path to input CSV file
        output_file: Path to output CSV file
        ev_power: Estimated EV charging power in kW (default: 11.0)
        threshold: Consumption threshold to detect EV charging (default: 8.0 kW)
        dry_run: If True, only show what would be changed without saving
    """
    print(f"📂 Reading data from: {input_file}")

    # Read the CSV file
    df = pd.read_csv(input_file)

    # Detect timestamp column (could be 'timestamp', 'timestamp_local', or 'timestamp_utc')
    timestamp_col = None
    for col in ['timestamp_local', 'timestamp', 'timestamp_utc']:
        if col in df.columns:
            timestamp_col = col
            break

    if timestamp_col is None:
        raise ValueError("No timestamp column found in CSV. Expected 'timestamp', 'timestamp_local', or 'timestamp_utc'")

    # Detect consumption column (could be 'consumption_kwh' or 'load_kwh')
    consumption_col = None
    for col in ['consumption_kwh', 'load_kwh']:
        if col in df.columns:
            consumption_col = col
            break

    if consumption_col is None:
        raise ValueError("No consumption column found in CSV. Expected 'consumption_kwh' or 'load_kwh'")

    print(f"📋 Using columns: timestamp='{timestamp_col}', consumption='{consumption_col}'")

    # Parse timestamp (handle timezones)
    df['timestamp'] = pd.to_datetime(df[timestamp_col], utc=True)
    df['timestamp'] = df['timestamp'].dt.tz_convert('Europe/Stockholm')  # Convert to local time
    df['consumption_kwh'] = df[consumption_col]
    df['hour'] = df['timestamp'].dt.hour
    df['date'] = df['timestamp'].dt.date

    print(f"📊 Total records: {len(df)}")
    print(f"📅 Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    # Identify E.ON measurement hours (06:00-23:00)
    eon_hours = (df['hour'] >= 6) & (df['hour'] <= 23)

    # Identify likely EV charging hours (consumption > threshold during E.ON hours)
    ev_charging_mask = eon_hours & (df['consumption_kwh'] > threshold)

    ev_charging_count = ev_charging_mask.sum()
    total_ev_energy = df.loc[ev_charging_mask, 'consumption_kwh'].sum()

    print(f"\n🔍 Analysis:")
    print(f"  E.ON measurement hours (06-23): {eon_hours.sum()} hours")
    print(f"  Hours with consumption >{threshold} kW during E.ON hours: {ev_charging_count} hours")
    print(f"  Total energy in these hours: {total_ev_energy:.1f} kWh")

    if ev_charging_count == 0:
        print("\n✅ No EV charging detected during E.ON hours. Data already clean!")
        if not dry_run:
            df.to_csv(output_file, index=False)
            print(f"💾 Saved unchanged data to: {output_file}")
        return df

    # Show examples of detected EV charging
    print(f"\n📋 Examples of detected EV charging hours:")
    ev_examples = df[ev_charging_mask].head(10)
    for _, row in ev_examples.iterrows():
        print(f"  {row['timestamp']}: {row['consumption_kwh']:.2f} kW")

    if ev_charging_count > 10:
        print(f"  ... and {ev_charging_count - 10} more hours")

    # Calculate adjustment
    df_cleaned = df.copy()

    # For hours with suspected EV charging, subtract estimated EV power
    # But don't go below a reasonable household baseline (2 kW)
    HOUSEHOLD_BASELINE = 2.0

    df_cleaned.loc[ev_charging_mask, 'consumption_kwh'] = (
        df_cleaned.loc[ev_charging_mask, 'consumption_kwh'] - ev_power
    ).clip(lower=HOUSEHOLD_BASELINE)

    # Calculate statistics
    total_adjusted = (df['consumption_kwh'] - df_cleaned['consumption_kwh']).sum()

    print(f"\n📉 Adjustments:")
    print(f"  Total consumption BEFORE: {df['consumption_kwh'].sum():.1f} kWh")
    print(f"  Total consumption AFTER:  {df_cleaned['consumption_kwh'].sum():.1f} kWh")
    print(f"  Total removed: {total_adjusted:.1f} kWh")
    print(f"  Average reduction: {total_adjusted / ev_charging_count:.1f} kWh per hour")

    # Show peak changes
    print(f"\n📈 Peak changes (E.ON hours only):")
    eon_mask = (df['hour'] >= 6) & (df['hour'] <= 23)

    monthly_peaks_before = df[eon_mask].groupby(df[eon_mask]['timestamp'].dt.to_period('M'))['consumption_kwh'].max()
    monthly_peaks_after = df_cleaned[eon_mask].groupby(df_cleaned[eon_mask]['timestamp'].dt.to_period('M'))['consumption_kwh'].max()

    for month in monthly_peaks_before.index:
        before = monthly_peaks_before[month]
        after = monthly_peaks_after[month]
        reduction = before - after
        print(f"  {month}: {before:.1f} kW → {after:.1f} kW (↓{reduction:.1f} kW, {reduction/before*100:.0f}%)")

    # Show daily consumption distribution
    print(f"\n📊 Daily consumption distribution:")
    daily_before = df.groupby('date')['consumption_kwh'].sum()
    daily_after = df_cleaned.groupby('date')['consumption_kwh'].sum()

    print(f"  Average daily consumption:")
    print(f"    Before: {daily_before.mean():.1f} kWh/day (std: {daily_before.std():.1f})")
    print(f"    After:  {daily_after.mean():.1f} kWh/day (std: {daily_after.std():.1f})")

    # Identify days with largest changes
    daily_changes = daily_before - daily_after
    top_changed_days = daily_changes.nlargest(5)

    print(f"\n📅 Days with largest adjustments:")
    for date, change in top_changed_days.items():
        before = daily_before[date]
        after = daily_after[date]
        print(f"  {date}: {before:.1f} kWh → {after:.1f} kWh (↓{change:.1f} kWh, {change/before*100:.0f}%)")

    if dry_run:
        print(f"\n🔍 DRY RUN: No files modified")
        print(f"   Run without --dry-run to save changes to: {output_file}")
    else:
        # Save cleaned data - update the original column
        df_cleaned[consumption_col] = df_cleaned['consumption_kwh']

        # Drop temporary columns
        columns_to_drop = ['hour', 'date', 'consumption_kwh', 'timestamp']
        # Only drop columns that exist and aren't original
        columns_to_drop = [col for col in columns_to_drop if col in df_cleaned.columns and col != consumption_col and col != timestamp_col]
        df_cleaned.drop(columns=columns_to_drop, inplace=True)

        df_cleaned.to_csv(output_file, index=False)
        print(f"\n✅ Cleaned data saved to: {output_file}")
        print(f"💡 You can now use this file for more realistic simulations!")

    return df_cleaned


def main():
    parser = argparse.ArgumentParser(
        description='Remove Tesla daytime charging from historical Tibber data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes without saving
  python clean_ev_charging.py tibber_data.csv tibber_data_cleaned.csv --dry-run

  # Clean data with default settings (11 kW EV, 8 kW threshold)
  python clean_ev_charging.py tibber_data.csv tibber_data_cleaned.csv

  # Custom EV power and threshold
  python clean_ev_charging.py tibber_data.csv tibber_data_cleaned.csv --ev-power 7.4 --threshold 6.0
        """
    )

    parser.add_argument('input_file', help='Input CSV file with Tibber data')
    parser.add_argument('output_file', help='Output CSV file for cleaned data')
    parser.add_argument('--ev-power', type=float, default=11.0,
                       help='Estimated EV charging power in kW (default: 11.0)')
    parser.add_argument('--threshold', type=float, default=8.0,
                       help='Consumption threshold to detect EV charging in kW (default: 8.0)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be changed without saving')

    args = parser.parse_args()

    try:
        clean_ev_charging(
            args.input_file,
            args.output_file,
            ev_power=args.ev_power,
            threshold=args.threshold,
            dry_run=args.dry_run
        )
    except FileNotFoundError:
        print(f"❌ Error: File not found: {args.input_file}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
