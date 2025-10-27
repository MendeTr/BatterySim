#!/usr/bin/env python3
"""
Test the new reserve-based peak shaving system.

Compares:
1. Pure arbitrage (no peak shaving reserves)
2. Reserve-based system (Boss Agent with statistical reserves)
3. Rule-based system (simple reactive peak shaving)
"""

import sys
import pandas as pd
import numpy as np
from battery_simulator import BatteryROISimulator
from agents.consumption_analyzer import ConsumptionAnalyzer
from agents.reserve_calculator import DynamicReserveCalculator
from agents.boss_agent import BossAgent
from agents.peak_shaving_agent import PeakShavingAgent
from agents.arbitrage_agent import ArbitrageAgent
from agents.base_agent import RealTimeOverrideAgent
from agents.value_calculator import ValueCalculator
from agents.peak_tracker import PeakTracker


def main():
    """Run comprehensive ROI comparison."""

    print("=" * 80)
    print("RESERVE-BASED PEAK SHAVING SYSTEM TEST")
    print("=" * 80)

    # Configuration
    battery_capacity = 25.0  # kWh - Dyness Stack 100
    battery_power = 12.0     # kW - Solis Hybrid 12kW
    battery_efficiency = 0.95
    grid_fee = 0.42          # SEK/kWh
    energy_tax = 0.40        # SEK/kWh
    vat_rate = 0.25          # 25%
    effect_tariff = 60.0     # SEK/kW/month
    grid_import_limit = 5.0  # kW - target to stay under

    # Date range for February 2025
    date_start = "2025-02-01"
    date_end = "2025-02-28"

    # Data file - USE SPIKE DATASET for realistic testing
    data_file = "tibber_with_spikes.csv"  # Has EV charging + heat pump + appliance spikes
    # data_file = "tibber_no_ev.csv"  # Original low-consumption data

    print(f"\n📊 Configuration:")
    print(f"  Battery: {battery_capacity} kWh, {battery_power} kW")
    print(f"  Efficiency: {battery_efficiency}")
    print(f"  Grid import target: ≤{grid_import_limit} kW (E.ON hours 06-23)")
    print(f"  Effect tariff: {effect_tariff} SEK/kW/month")
    print(f"  Test period: {date_start} to {date_end}")

    # Load and prepare data
    print(f"\n📂 Loading data from {data_file}...")
    simulator = BatteryROISimulator(
        battery_capacity_kwh=battery_capacity,
        battery_power_kw=battery_power,
        battery_efficiency=battery_efficiency,
        battery_cost_sek=150000,
        battery_lifetime_years=15,
        use_gpt_arbitrage=False,
        use_multi_agent=False
    )

    df = simulator.load_tibber_data(data_file)
    print(f"✓ Loaded {len(df)} hours ({df['timestamp'].min()} to {df['timestamp'].max()})")

    # Build consumption analyzer using ALL historical data before February
    print(f"\n📈 Building consumption analyzer...")
    date_start_tz = pd.Timestamp(date_start, tz='UTC')
    historical_df = df[df['timestamp'] < date_start_tz].copy()
    print(f"  Historical data: {len(historical_df)} hours ({historical_df['timestamp'].min()} to {historical_df['timestamp'].max()})")

    analyzer = ConsumptionAnalyzer(historical_df, consumption_col='consumption_kwh')
    analyzer.print_summary()

    # Initialize reserve calculator
    print(f"\n🎯 Initializing reserve calculator...")
    reserve_calc = DynamicReserveCalculator(
        consumption_analyzer=analyzer,
        grid_import_limit_kw=grid_import_limit,
        max_discharge_kw=battery_power,  # 12 kW inverter limit
        default_percentile=95,
        safety_buffer=1.15,
        spike_duration_hours=0.5,  # 30 min spikes (conservative)
        min_reserve_kwh=2.0,
        max_reserve_kwh=15.0
    )
    print(f"  Inverter limit: {battery_power} kW")
    print(f"  Spike duration: 30 minutes (conservative)")
    print(f"  Strategy: Reduce peaks to ~{grid_import_limit} kW, not eliminate")

    # Test reserve calculation for a few sample hours
    print(f"\n🔍 Sample reserve calculations (showing high-risk evening hours):")
    print("-" * 80)
    # Focus on evening hours where spikes happen
    test_hours = [6, 7, 17, 18, 19, 20, 21, 22, 23]
    for hour in test_hours:
        test_timestamp = pd.Timestamp(f'{date_start} {hour:02d}:00:00', tz='UTC')
        reserve_req = reserve_calc.calculate_reserve(
            timestamp=test_timestamp,
            current_soc_kwh=15.0  # Assume 60% SOC
        )
        print(f"\nHour {hour:02d}: Reserve {reserve_req.required_reserve_kwh:.1f} kWh")
        print(f"  → {reserve_req.reasoning}")

    # Initialize specialist agents
    print(f"\n🤖 Initializing specialist agents...")
    value_calc = ValueCalculator(
        grid_fee_sek_kwh=grid_fee,
        energy_tax_sek_kwh=energy_tax,
        transfer_fee_sek_kwh=grid_fee,
        vat_rate=vat_rate,
        effect_tariff_sek_kw_month=effect_tariff
    )

    peak_tracker = PeakTracker()

    peak_shaving_agent = PeakShavingAgent(
        peak_tracker=peak_tracker,
        value_calculator=value_calc,
        target_peak_kw=grid_import_limit,
        aggressive_threshold_multiplier=0.80
    )

    arbitrage_agent = ArbitrageAgent(
        value_calculator=value_calc,
        min_arbitrage_profit_sek=20.0,
        min_export_spot_price=3.0,
        night_charge_threshold=0.40
    )

    override_agent = RealTimeOverrideAgent(
        spike_threshold_kw=10.0,
        critical_peak_margin_kw=1.0
    )

    # Initialize Boss Agent
    print(f"\n👔 Initializing Boss Agent...")
    boss_agent = BossAgent(
        consumption_analyzer=analyzer,
        reserve_calculator=reserve_calc,
        peak_shaving_agent=peak_shaving_agent,
        arbitrage_agent=arbitrage_agent,
        real_time_override_agent=override_agent,
        verbose=False  # Set to True for detailed output
    )

    print(f"\n✅ All components initialized!")
    print(f"\n{'=' * 80}")
    print("READY TO RUN SIMULATIONS")
    print("=" * 80)

    # TODO: Run actual simulation with Boss Agent
    # This requires integrating Boss Agent into battery_simulator.py
    # For now, we've built all the infrastructure

    print(f"\n📝 Next steps:")
    print(f"  1. Integrate Boss Agent into battery_simulator.py")
    print(f"  2. Run simulation on February data")
    print(f"  3. Compare with rule-based and multi-agent results")
    print(f"  4. Generate ROI comparison report")

    return 0


if __name__ == "__main__":
    sys.exit(main())
