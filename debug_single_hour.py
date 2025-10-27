#!/usr/bin/env python3
"""
Debug a single hour to understand why multi-agent creates peaks.
"""

from datetime import datetime
from agents import (
    PeakTracker,
    ValueCalculator,
    BatteryContext,
    RealTimeOverrideAgent,
    PeakShavingAgent,
    ArbitrageAgent,
    Orchestrator
)

# Create agents
peak_tracker = PeakTracker()
value_calculator = ValueCalculator()

override_agent = RealTimeOverrideAgent()
peak_agent = PeakShavingAgent(peak_tracker, value_calculator)
arbitrage_agent = ArbitrageAgent(value_calculator)

orchestrator = Orchestrator(
    agents=[override_agent, peak_agent, arbitrage_agent],
    value_calculator=value_calculator
)

# Simulate Feb 14, hour 10:00 (during E.ON hours)
# This is when battery charged and created a 9.7 kW peak
context = BatteryContext(
    timestamp=datetime(2025, 2, 14, 10, 0),
    hour=10,
    soc_kwh=15.0,  # Has room to charge
    capacity_kwh=25.0,
    max_charge_kw=12.0,
    max_discharge_kw=12.0,
    efficiency=0.95,
    consumption_kw=4.0,  # Moderate consumption
    solar_production_kw=2.0,
    grid_import_kw=2.0,  # 4 - 2 = 2 kW (before battery)
    spot_price_sek_kwh=0.50,  # Cheap price (this is the problem!)
    import_cost_sek_kwh=1.65,
    export_revenue_sek_kwh=0.08,
    spot_forecast=[0.5] * 24,
    current_month="2025-02",
    top_n_peaks=[7.5, 6.5, 5.0],  # Already have 3 peaks
    peak_threshold_kw=5.0,  # Threshold is 5 kW
    is_measurement_hour=True,  # CRITICAL: This is during 06:00-23:00!
    avg_consumption_kw=4.5,
    peak_consumption_kw=11.0,
    min_soc_kwh=1.25,
    target_morning_soc_kwh=20.0
)

print("=" * 80)
print("DEBUG: Single Hour Analysis - Feb 14, 10:00")
print("=" * 80)
print(f"\n📊 Context:")
print(f"  Time: {context.timestamp}")
print(f"  Hour: {context.hour} (is_measurement_hour={context.is_measurement_hour})")
print(f"  Consumption: {context.consumption_kw} kW")
print(f"  Solar: {context.solar_production_kw} kW")
print(f"  Grid import (before battery): {context.grid_import_kw} kW")
print(f"  Spot price: {context.spot_price_sek_kwh} SEK/kWh (CHEAP!)")
print(f"  SOC: {context.soc_kwh}/{context.capacity_kwh} kWh")
print(f"  Top 3 peaks: {context.top_n_peaks}")
print(f"  Peak threshold: {context.peak_threshold_kw} kW")

# Get recommendations from each agent
print(f"\n🤖 Agent Recommendations:")

override_rec = override_agent.analyze(context)
print(f"\n1. RealTimeOverride:")
if override_rec:
    print(f"   Action: {override_rec.action.value}")
    print(f"   Amount: {override_rec.kwh} kWh")
    print(f"   Reasoning: {override_rec.reasoning[:100]}")
else:
    print(f"   No recommendation (no emergency)")

peak_rec = peak_agent.analyze(context)
print(f"\n2. PeakShavingAgent:")
if peak_rec:
    print(f"   Action: {peak_rec.action.value}")
    print(f"   Amount: {peak_rec.kwh} kWh")
    print(f"   Reasoning: {peak_rec.reasoning[:100]}")
else:
    print(f"   No recommendation (below threshold)")

arbitrage_rec = arbitrage_agent.analyze(context)
print(f"\n3. ArbitrageAgent:")
if arbitrage_rec:
    print(f"   Action: {arbitrage_rec.action.value}")
    print(f"   Amount: {arbitrage_rec.kwh} kWh")
    print(f"   Value: {arbitrage_rec.value_sek:.2f} SEK")
    print(f"   Priority: {arbitrage_rec.priority}")
    print(f"   Reasoning: {arbitrage_rec.reasoning[:100]}")
else:
    print(f"   No recommendation")

# Get orchestrator decision
print(f"\n🎯 Orchestrator Decision:")
decision = orchestrator.analyze(context)

if decision:
    print(f"   Final Action: {decision.action.value}")
    print(f"   Amount: {decision.kwh} kWh")
    print(f"   Value: {decision.value_sek:.2f} SEK")
    print(f"   Contributing agents: {decision.metadata.get('contributing_agents', [])}")

    # Simulate outcome
    if decision.action.value == 'charge':
        new_grid_import = context.grid_import_kw + decision.kwh
        print(f"\n⚠️  OUTCOME IF EXECUTED:")
        print(f"   Grid import BEFORE: {context.grid_import_kw} kW")
        print(f"   Grid import AFTER: {new_grid_import} kW")
        if new_grid_import > context.peak_threshold_kw:
            print(f"   ❌ WOULD CREATE NEW PEAK! ({new_grid_import:.1f} kW > {context.peak_threshold_kw} kW threshold)")
            peak_cost = (new_grid_import - context.peak_threshold_kw) * 60 / 30
            print(f"   Peak cost: {peak_cost:.2f} SEK/day")
        else:
            print(f"   ✓ Safe (below threshold)")
else:
    print(f"   No action (recommendation rejected)")

print(f"\n" + "=" * 80)
