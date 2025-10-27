#!/usr/bin/env python3
"""
Test script for multi-agent battery simulation on February 2025 data.

Compares multi-agent system vs rule-based system.
"""

import sys
from battery_simulator import BatteryROISimulator

def main():
    """Run simulation on February 2025 data with multi-agent system."""

    print("=" * 80)
    print("MULTI-AGENT BATTERY SIMULATION TEST")
    print("Testing on February 2025 data")
    print("=" * 80)

    # Configuration
    battery_capacity = 25.0  # kWh - Dyness Stack 100
    battery_power = 12.0     # kW - Solis Hybrid 12kW
    battery_efficiency = 0.95
    battery_cost = 150000    # SEK
    battery_lifetime = 15    # years

    grid_fee = 0.42          # SEK/kWh
    energy_tax = 0.40        # SEK/kWh
    vat_rate = 0.25          # 25%
    effect_tariff = 60.0     # SEK/kW/month

    # Date range for February 2025
    date_start = "2025-02-01"
    date_end = "2025-02-28"

    # Data file (cleaned without daytime EV charging)
    data_file = "tibber_no_ev.csv"

    print(f"\n📊 Configuration:")
    print(f"  Battery: {battery_capacity} kWh, {battery_power} kW")
    print(f"  Efficiency: {battery_efficiency}")
    print(f"  Cost model: {grid_fee} SEK/kWh grid fee, {energy_tax} SEK/kWh energy tax")
    print(f"  Effect tariff: {effect_tariff} SEK/kW/month (top 3 peaks avg)")
    print(f"  Date range: {date_start} to {date_end}")
    print(f"  Data file: {data_file}")

    # Test 1: Multi-agent system
    print("\n" + "=" * 80)
    print("TEST 1: MULTI-AGENT SYSTEM")
    print("=" * 80)

    simulator_multi = BatteryROISimulator(
        battery_capacity_kwh=battery_capacity,
        battery_power_kw=battery_power,
        battery_efficiency=battery_efficiency,
        battery_cost_sek=battery_cost,
        battery_lifetime_years=battery_lifetime,
        use_gpt_arbitrage=False,
        use_multi_agent=True
    )

    # Load data
    df = simulator_multi.load_tibber_data(data_file)
    print(f"✓ Loaded {len(df)} hours of data")

    # Calculate baseline costs
    cost_without = simulator_multi.calculate_current_costs(
        df,
        grid_fee_sek_kwh=grid_fee,
        energy_tax_sek_kwh=energy_tax,
        vat_rate=vat_rate
    )

    print(f"\n💰 Baseline cost (no battery):")
    print(f"  Total cost: {cost_without['total_cost_sek']:.0f} SEK")

    # Run simulation with multi-agent
    print(f"\n🔄 Running multi-agent simulation...")
    df_multi, results_multi = simulator_multi.simulate_battery_operation(
        df,
        grid_fee_sek_kwh=grid_fee,
        energy_tax_sek_kwh=energy_tax,
        effect_tariff_sek_kw_month=effect_tariff,
        vat_rate=vat_rate,
        enable_arbitrage=True,
        effect_tariff_method='top3_average',
        date_range_start=date_start,
        date_range_end=date_end
    )

    print(f"\n✅ Multi-agent simulation complete!")
    print(f"\n📈 Results with multi-agent:")
    print(f"  Total cost: {results_multi['total_cost_sek']:.0f} SEK")
    print(f"  Export revenue: {results_multi['export_revenue_sek']:.0f} SEK")
    print(f"  Net cost: {results_multi['net_cost_sek']:.0f} SEK")
    print(f"  Peak shaving savings: {results_multi['effect_tariff_savings_sek']:.0f} SEK")
    print(f"  Peak WITHOUT battery: {results_multi['peak_import_without_battery_kw']:.2f} kW")
    print(f"  Peak WITH battery: {results_multi['peak_import_with_battery_kw']:.2f} kW")

    # Calculate savings
    baseline_cost = cost_without['total_cost_sek']
    # Calculate baseline for filtered period
    filtered_df = df_multi[df_multi['timestamp'] >= date_start]
    if 'total_cost_without_vat' in filtered_df.columns:
        filtered_baseline = filtered_df['total_cost_without_vat'].sum() * (1 + vat_rate)
    else:
        # Calculate from consumption and prices
        filtered_baseline = filtered_df['consumption_kwh'].sum() * ((grid_fee + energy_tax) * (1 + vat_rate)) + \
                           (filtered_df['consumption_kwh'] * filtered_df['spot_price_sek_kwh']).sum() * (1 + vat_rate)
    savings_multi = filtered_baseline - results_multi['net_cost_sek']

    print(f"\n💵 Savings:")
    print(f"  Monthly baseline cost: {filtered_baseline:.0f} SEK")
    print(f"  Monthly net cost with battery: {results_multi['net_cost_sek']:.0f} SEK")
    print(f"  Monthly savings: {savings_multi:.0f} SEK")
    print(f"  Annual savings (extrapolated): {savings_multi * 12:.0f} SEK")

    # Test 2: Rule-based system (for comparison)
    print("\n" + "=" * 80)
    print("TEST 2: RULE-BASED SYSTEM (for comparison)")
    print("=" * 80)

    simulator_rule = BatteryROISimulator(
        battery_capacity_kwh=battery_capacity,
        battery_power_kw=battery_power,
        battery_efficiency=battery_efficiency,
        battery_cost_sek=battery_cost,
        battery_lifetime_years=battery_lifetime,
        use_gpt_arbitrage=False,
        use_multi_agent=False
    )

    df2 = simulator_rule.load_tibber_data(data_file)

    print(f"🔄 Running rule-based simulation...")
    df_rule, results_rule = simulator_rule.simulate_battery_operation(
        df2,
        grid_fee_sek_kwh=grid_fee,
        energy_tax_sek_kwh=energy_tax,
        effect_tariff_sek_kw_month=effect_tariff,
        vat_rate=vat_rate,
        enable_arbitrage=True,
        effect_tariff_method='top3_average',
        date_range_start=date_start,
        date_range_end=date_end
    )

    print(f"\n✅ Rule-based simulation complete!")
    print(f"\n📈 Results with rule-based:")
    print(f"  Total cost: {results_rule['total_cost_sek']:.0f} SEK")
    print(f"  Export revenue: {results_rule['export_revenue_sek']:.0f} SEK")
    print(f"  Net cost: {results_rule['net_cost_sek']:.0f} SEK")
    print(f"  Peak shaving savings: {results_rule['effect_tariff_savings_sek']:.0f} SEK")
    print(f"  Peak WITHOUT battery: {results_rule['peak_import_without_battery_kw']:.2f} kW")
    print(f"  Peak WITH battery: {results_rule['peak_import_with_battery_kw']:.2f} kW")

    # Calculate baseline for filtered period
    filtered_df2 = df_rule[df_rule['timestamp'] >= date_start]
    if 'total_cost_without_vat' in filtered_df2.columns:
        filtered_baseline2 = filtered_df2['total_cost_without_vat'].sum() * (1 + vat_rate)
    else:
        filtered_baseline2 = filtered_df2['consumption_kwh'].sum() * ((grid_fee + energy_tax) * (1 + vat_rate)) + \
                            (filtered_df2['consumption_kwh'] * filtered_df2['spot_price_sek_kwh']).sum() * (1 + vat_rate)
    savings_rule = filtered_baseline2 - results_rule['net_cost_sek']

    print(f"\n💵 Savings:")
    print(f"  Monthly savings: {savings_rule:.0f} SEK")
    print(f"  Annual savings (extrapolated): {savings_rule * 12:.0f} SEK")

    # Comparison
    print("\n" + "=" * 80)
    print("COMPARISON: Multi-Agent vs Rule-Based")
    print("=" * 80)

    improvement = savings_multi - savings_rule
    improvement_pct = (improvement / savings_rule * 100) if savings_rule > 0 else 0

    print(f"\n📊 Monthly Savings:")
    print(f"  Multi-Agent: {savings_multi:.0f} SEK")
    print(f"  Rule-Based:  {savings_rule:.0f} SEK")
    print(f"  Improvement: {improvement:+.0f} SEK ({improvement_pct:+.1f}%)")

    print(f"\n📊 Annual Savings (extrapolated):")
    print(f"  Multi-Agent: {savings_multi * 12:.0f} SEK/year")
    print(f"  Rule-Based:  {savings_rule * 12:.0f} SEK/year")
    print(f"  Improvement: {improvement * 12:+.0f} SEK/year")

    print(f"\n📊 Peak Reduction:")
    print(f"  Multi-Agent: {results_multi['peak_import_without_battery_kw'] - results_multi['peak_import_with_battery_kw']:.2f} kW")
    print(f"  Rule-Based:  {results_rule['peak_import_without_battery_kw'] - results_rule['peak_import_with_battery_kw']:.2f} kW")

    # ROI Calculation
    print("\n" + "=" * 80)
    print("ROI ANALYSIS (Multi-Agent)")
    print("=" * 80)

    annual_savings = savings_multi * 12
    roi_years = battery_cost / annual_savings if annual_savings > 0 else float('inf')

    print(f"\n💰 Investment:")
    print(f"  Battery cost: {battery_cost:,.0f} SEK")
    print(f"  Annual savings: {annual_savings:,.0f} SEK/year")
    print(f"  Payback period: {roi_years:.1f} years")

    if roi_years < battery_lifetime:
        total_savings = annual_savings * battery_lifetime
        net_profit = total_savings - battery_cost
        print(f"\n✅ PROFITABLE!")
        print(f"  Total savings over {battery_lifetime} years: {total_savings:,.0f} SEK")
        print(f"  Net profit: {net_profit:,.0f} SEK")
    else:
        print(f"\n⚠️ WARNING: Payback period ({roi_years:.1f} years) exceeds battery lifetime ({battery_lifetime} years)")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

    return 0


if __name__ == '__main__':
    exit(main())
