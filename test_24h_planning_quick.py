#!/usr/bin/env python3
"""
Quick test to verify 24h planning is working.
Tests just a few days to see if plan creation happens at hour 13.
"""

import sys
import pandas as pd
from battery_simulator import BatteryROISimulator

def main():
    print("=" * 80)
    print("24H PLANNING QUICK TEST")
    print("=" * 80)

    # Configuration
    battery_capacity = 25.0  # kWh
    battery_power = 12.0     # kW
    battery_efficiency = 0.95
    grid_fee = 0.42
    energy_tax = 0.40
    vat_rate = 0.25
    effect_tariff = 60.0

    # Initialize simulator
    sim = BatteryROISimulator(
        battery_capacity_kwh=battery_capacity,
        battery_power_kw=battery_power,
        battery_efficiency=battery_efficiency,
        battery_cost_sek=150000,
        battery_lifetime_years=15,
        use_boss_agent=True
    )

    # Load data
    df = sim.load_tibber_data("tibber_last12m_with_prod.csv")

    # Use only a few days of data for quick test
    test_start = pd.Timestamp('2025-02-01', tz='UTC')
    test_end = pd.Timestamp('2025-02-05', tz='UTC')  # Just 5 days

    historical_df = df[df['timestamp'] < test_start].copy()
    test_df = df[(df['timestamp'] >= test_start) & (df['timestamp'] < test_end)].copy()

    print(f"\n📊 Data:")
    print(f"  Historical: {len(historical_df)} hours")
    print(f"  Test: {len(test_df)} hours ({test_start} to {test_end})")

    # Initialize Boss Agent
    sim._initialize_boss_agent_system(historical_df)
    sim.boss_agent.verbose = True  # Enable verbose to see 24h planning messages

    print(f"\n✅ Boss Agent initialized")
    print(f"  24h planning enabled: {sim.boss_agent.enable_24h_planning}")
    print(f"  Optimizer exists: {sim.boss_agent.optimizer is not None}")
    print(f"  Plan created hour: {sim.boss_agent.plan_created_hour}")

    print(f"\n🔄 Running simulation...")
    print(f"Looking for 24h plan creation at hour 13 on each day...")
    print("=" * 80)

    # Run simulation
    df_result, results = sim.simulate_battery_operation(
        test_df,
        grid_fee_sek_kwh=grid_fee,
        energy_tax_sek_kwh=energy_tax,
        vat_rate=vat_rate,
        effect_tariff_sek_kw_month=effect_tariff,
        enable_arbitrage=True
    )

    print("\n" + "=" * 80)
    print("✅ Test complete!")
    print(f"  Net cost: {results['net_cost_sek']:.0f} SEK")
    print(f"  Peak reduction: {results['peak_import_without_battery_kw'] - results['peak_import_with_battery_kw']:.2f} kW")

    return 0


if __name__ == "__main__":
    sys.exit(main())
