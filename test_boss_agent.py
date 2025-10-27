#!/usr/bin/env python3
"""
Test Boss Agent (reserve-based) system on spike dataset.

Compares:
1. No battery (baseline)
2. Rule-based peak shaving
3. Boss Agent (reserve-based with statistical analysis)
"""

import sys
from battery_simulator import BatteryROISimulator


def main():
    """Run comparison test."""

    print("=" * 80)
    print("BOSS AGENT (RESERVE-BASED) COMPARISON TEST")
    print("=" * 80)

    # Configuration
    battery_capacity = 25.0
    battery_power = 12.0
    battery_efficiency = 0.95
    grid_fee = 0.42
    energy_tax = 0.40
    vat_rate = 0.25
    effect_tariff = 60.0

    # Use REAL user data (no artificial spikes)
    data_file = "tibber_last12m_with_prod.csv"

    print(f"\n📊 Configuration:")
    print(f"  Battery: {battery_capacity} kWh, {battery_power} kW")
    print(f"  Dataset: {data_file} (REAL user data, no artificial spikes)")
    print(f"  Effect tariff: {effect_tariff} SEK/kW/month")

    # Test 1: Boss Agent (Reserve-based)
    print(f"\n" + "=" * 80)
    print("TEST 1: BOSS AGENT (RESERVE-BASED)")
    print("=" * 80)

    simulator_boss = BatteryROISimulator(
        battery_capacity_kwh=battery_capacity,
        battery_power_kw=battery_power,
        battery_efficiency=battery_efficiency,
        battery_cost_sek=150000,
        battery_lifetime_years=15,
        use_gpt_arbitrage=False,
        use_multi_agent=False,
        use_boss_agent=True  # Enable Boss Agent
    )

    df = simulator_boss.load_tibber_data(data_file)
    print(f"✓ Loaded {len(df)} hours")

    # For Boss Agent, we need to initialize with ONLY historical data (not test period)
    # This prevents data leakage - the agent shouldn't "learn" from the future
    print(f"\n📈 Preparing historical data for Boss Agent...")
    import pandas as pd
    # Use February 2025 as test month - train on all data before Feb 2025
    test_start = pd.Timestamp('2025-02-01', tz='UTC')
    historical_df = df[df['timestamp'] < test_start].copy()
    print(f"  Historical: {len(historical_df)} hours ({historical_df['timestamp'].min()} to {historical_df['timestamp'].max()})")
    print(f"  Test period: {test_start} onwards")

    # Initialize Boss Agent with historical data ONLY
    simulator_boss._initialize_boss_agent_system(historical_df)
    print(f"✓ Boss Agent trained on historical data")

    print(f"\n🔄 Running Boss Agent simulation on full year...")
    df_boss, results_boss = simulator_boss.simulate_battery_operation(
        df,
        grid_fee_sek_kwh=grid_fee,
        energy_tax_sek_kwh=energy_tax,
        vat_rate=vat_rate,
        effect_tariff_sek_kw_month=effect_tariff,
        enable_arbitrage=True
    )

    print(f"\n✅ Boss Agent simulation complete!")
    print(f"\n📈 Results with Boss Agent:")
    print(f"  Total cost: {results_boss['total_cost_sek']:.0f} SEK")
    print(f"  Export revenue: {results_boss['export_revenue_sek']:.0f} SEK")
    print(f"  Net cost: {results_boss['net_cost_sek']:.0f} SEK")
    print(f"  Peak shaving savings: {results_boss['peak_shaving_savings_sek']:.0f} SEK")
    print(f"  Peak WITHOUT battery: {results_boss['peak_import_without_battery_kw']:.2f} kW")
    print(f"  Peak WITH battery: {results_boss['peak_import_with_battery_kw']:.2f} kW")
    peak_reduction = results_boss['peak_import_without_battery_kw'] - results_boss['peak_import_with_battery_kw']
    print(f"  Peak reduction: {peak_reduction:.2f} kW")

    # Test 2: Rule-based (for comparison)
    print(f"\n" + "=" * 80)
    print("TEST 2: RULE-BASED (FOR COMPARISON)")
    print("=" * 80)

    simulator_rule = BatteryROISimulator(
        battery_capacity_kwh=battery_capacity,
        battery_power_kw=battery_power,
        battery_efficiency=battery_efficiency,
        battery_cost_sek=150000,
        battery_lifetime_years=15,
        use_gpt_arbitrage=False,
        use_multi_agent=False,
        use_boss_agent=False
    )

    df2 = simulator_rule.load_tibber_data(data_file)

    print(f"\n🔄 Running rule-based simulation...")
    df_rule, results_rule = simulator_rule.simulate_battery_operation(
        df2,
        grid_fee_sek_kwh=grid_fee,
        energy_tax_sek_kwh=energy_tax,
        vat_rate=vat_rate,
        effect_tariff_sek_kw_month=effect_tariff,
        enable_arbitrage=True
    )

    print(f"\n✅ Rule-based simulation complete!")
    print(f"\n📈 Results with rule-based:")
    print(f"  Total cost: {results_rule['total_cost_sek']:.0f} SEK")
    print(f"  Export revenue: {results_rule['export_revenue_sek']:.0f} SEK")
    print(f"  Net cost: {results_rule['net_cost_sek']:.0f} SEK")
    print(f"  Peak shaving savings: {results_rule['peak_shaving_savings_sek']:.0f} SEK")
    print(f"  Peak WITHOUT battery: {results_rule['peak_import_without_battery_kw']:.2f} kW")
    print(f"  Peak WITH battery: {results_rule['peak_import_with_battery_kw']:.2f} kW")
    peak_reduction_rule = results_rule['peak_import_without_battery_kw'] - results_rule['peak_import_with_battery_kw']
    print(f"  Peak reduction: {peak_reduction_rule:.2f} kW")

    # Comparison
    print(f"\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)
    print(f"\nBaseline (no battery):")
    print(f"  Peak: {results_boss['peak_import_without_battery_kw']:.2f} kW")
    print(f"  Effect tariff cost: {results_boss['peak_import_without_battery_kw'] * effect_tariff:.0f} SEK/month")

    print(f"\nRule-based system:")
    print(f"  Peak: {results_rule['peak_import_with_battery_kw']:.2f} kW")
    print(f"  Peak reduction: {peak_reduction_rule:.2f} kW")
    print(f"  Net cost: {results_rule['net_cost_sek']:.0f} SEK")

    print(f"\nBoss Agent (reserve-based):")
    print(f"  Peak: {results_boss['peak_import_with_battery_kw']:.2f} kW")
    print(f"  Peak reduction: {peak_reduction:.2f} kW")
    print(f"  Net cost: {results_boss['net_cost_sek']:.0f} SEK")

    cost_diff = results_rule['net_cost_sek'] - results_boss['net_cost_sek']
    peak_diff = results_rule['peak_import_with_battery_kw'] - results_boss['peak_import_with_battery_kw']

    print(f"\nBoss Agent vs Rule-based:")
    print(f"  Cost difference: {cost_diff:.0f} SEK (positive = Boss Agent saves more)")
    print(f"  Peak difference: {peak_diff:.2f} kW (positive = Boss Agent reduces more)")

    if peak_diff > 0:
        print(f"  ✓ Boss Agent achieves {peak_diff:.2f} kW better peak reduction!")
    elif peak_diff < 0:
        print(f"  ✗ Rule-based achieves {abs(peak_diff):.2f} kW better peak reduction")
    else:
        print(f"  = Both achieve same peak reduction")

    return 0


if __name__ == "__main__":
    sys.exit(main())
