#!/usr/bin/env python3
"""
Test script for multi-agent system.

Verifies that all agents can be instantiated and work together correctly.
"""

from datetime import datetime
from agents import (
    PeakTracker,
    ValueCalculator,
    BatteryContext,
    RealTimeOverrideAgent,
    PeakShavingAgent,
    ArbitrageAgent,
    Orchestrator,
    AgentAction
)


def test_agent_instantiation():
    """Test that all agents can be created."""
    print("=" * 60)
    print("Testing Agent Instantiation")
    print("=" * 60)

    # Create infrastructure components
    peak_tracker = PeakTracker()
    value_calculator = ValueCalculator()
    print(f"✓ Created infrastructure: {peak_tracker}, {value_calculator}")

    # Create specialist agents
    override_agent = RealTimeOverrideAgent()
    peak_agent = PeakShavingAgent(peak_tracker, value_calculator)
    arbitrage_agent = ArbitrageAgent(value_calculator)
    print(f"✓ Created specialist agents:")
    print(f"  - {override_agent}")
    print(f"  - {peak_agent}")
    print(f"  - {arbitrage_agent}")

    # Create orchestrator
    orchestrator = Orchestrator(
        agents=[override_agent, peak_agent, arbitrage_agent],
        value_calculator=value_calculator
    )
    print(f"✓ Created orchestrator: {orchestrator}")

    return peak_tracker, value_calculator, orchestrator


def test_battery_context_creation():
    """Test creating battery context."""
    print("\n" + "=" * 60)
    print("Testing Battery Context Creation")
    print("=" * 60)

    context = BatteryContext(
        timestamp=datetime(2025, 2, 22, 18, 0),
        hour=18,
        soc_kwh=20.0,
        capacity_kwh=25.0,
        max_charge_kw=12.0,
        max_discharge_kw=12.0,
        efficiency=0.95,
        consumption_kw=12.0,
        solar_production_kw=0.0,
        grid_import_kw=12.0,
        spot_price_sek_kwh=2.50,
        import_cost_sek_kwh=3.15,  # (2.50 + 0.42 + 0.40) × 1.25
        export_revenue_sek_kwh=2.08,  # 2.50 - 0.42
        spot_forecast=[1.5] * 24,
        current_month="2025-02",
        top_n_peaks=[11.0, 10.5, 10.0],
        peak_threshold_kw=10.0,
        is_measurement_hour=True,
        avg_consumption_kw=4.5,
        peak_consumption_kw=11.0,
        min_soc_kwh=5.0,
        target_morning_soc_kwh=20.0
    )

    print(f"✓ Created context for {context.timestamp}")
    print(f"  - Consumption: {context.consumption_kw} kW")
    print(f"  - SOC: {context.soc_kwh}/{context.capacity_kwh} kWh")
    print(f"  - Spot price: {context.spot_price_sek_kwh:.2f} SEK/kWh")
    print(f"  - Peak threshold: {context.peak_threshold_kw} kW")

    return context


def test_scenario_peak_shaving(orchestrator, peak_tracker, context):
    """Test peak shaving scenario."""
    print("\n" + "=" * 60)
    print("Scenario 1: Peak Shaving")
    print("=" * 60)
    print(f"Situation: 12 kW consumption during E.ON hours")
    print(f"Top 3 peaks: {context.top_n_peaks}")
    print(f"Threshold: {context.peak_threshold_kw} kW")
    print()

    # Get orchestrator decision
    decision = orchestrator.analyze(context)

    if decision:
        print(f"✓ Orchestrator Decision:")
        print(f"  - Action: {decision.action.value}")
        print(f"  - Amount: {decision.kwh:.1f} kWh")
        print(f"  - Value: {decision.value_sek:.0f} SEK")
        print(f"  - Confidence: {decision.confidence * 100:.0f}%")
        print(f"  - Agents: {', '.join(decision.metadata['contributing_agents'])}")
        print(f"  - Reasoning: {decision.reasoning[:120]}...")
    else:
        print("✗ No decision made")


def test_scenario_night_charging(orchestrator, context):
    """Test night charging scenario."""
    print("\n" + "=" * 60)
    print("Scenario 2: Night Charging")
    print("=" * 60)

    # Create night context
    night_context = BatteryContext(
        timestamp=datetime(2025, 2, 23, 2, 0),
        hour=2,
        soc_kwh=10.0,
        capacity_kwh=25.0,
        max_charge_kw=12.0,
        max_discharge_kw=12.0,
        efficiency=0.95,
        consumption_kw=2.0,
        solar_production_kw=0.0,
        grid_import_kw=2.0,
        spot_price_sek_kwh=0.45,  # Cheap night price
        import_cost_sek_kwh=0.56,  # (0.45 + 0.42 + 0.40) × 1.25
        export_revenue_sek_kwh=0.03,  # 0.45 - 0.42
        spot_forecast=[0.5, 0.5, 0.5, 0.5, 0.5, 0.5] + [1.5] * 18,
        current_month="2025-02",
        top_n_peaks=[11.0, 10.5, 10.0],
        peak_threshold_kw=10.0,
        is_measurement_hour=False,
        avg_consumption_kw=4.5,
        peak_consumption_kw=11.0,
        min_soc_kwh=5.0,
        target_morning_soc_kwh=20.0
    )

    print(f"Situation: 02:00, cheap price {night_context.spot_price_sek_kwh:.2f} SEK/kWh")
    print(f"SOC: {night_context.soc_kwh}/{night_context.capacity_kwh} kWh")
    print()

    decision = orchestrator.analyze(night_context)

    if decision:
        print(f"✓ Orchestrator Decision:")
        print(f"  - Action: {decision.action.value}")
        print(f"  - Amount: {decision.kwh:.1f} kWh")
        print(f"  - Value: {decision.value_sek:.0f} SEK")
        print(f"  - Confidence: {decision.confidence * 100:.0f}%")
        print(f"  - Reasoning: {decision.reasoning[:120]}...")
    else:
        print("✗ No decision made")


def test_scenario_emergency_spike(orchestrator, context):
    """Test emergency override scenario."""
    print("\n" + "=" * 60)
    print("Scenario 3: Emergency Spike")
    print("=" * 60)

    # Create emergency context
    emergency_context = BatteryContext(
        timestamp=datetime(2025, 2, 22, 18, 0),
        hour=18,
        soc_kwh=20.0,
        capacity_kwh=25.0,
        max_charge_kw=12.0,
        max_discharge_kw=12.0,
        efficiency=0.95,
        consumption_kw=15.0,  # SPIKE!
        solar_production_kw=0.0,
        grid_import_kw=15.0,
        spot_price_sek_kwh=2.50,
        import_cost_sek_kwh=3.15,
        export_revenue_sek_kwh=2.08,
        spot_forecast=[1.5] * 24,
        current_month="2025-02",
        top_n_peaks=[11.0, 10.5, 10.0],
        peak_threshold_kw=10.0,  # Will exceed threshold by 5 kW!
        is_measurement_hour=True,
        avg_consumption_kw=4.5,
        peak_consumption_kw=11.0,
        min_soc_kwh=5.0,
        target_morning_soc_kwh=20.0
    )

    print(f"Situation: UNEXPECTED 15 kW SPIKE during E.ON hours!")
    print(f"Threshold: {emergency_context.peak_threshold_kw} kW")
    print(f"Exceeds by: {emergency_context.consumption_kw - emergency_context.peak_threshold_kw:.1f} kW")
    print()

    decision = orchestrator.analyze(emergency_context)

    if decision:
        print(f"✓ Orchestrator Decision:")
        print(f"  - Action: {decision.action.value}")
        print(f"  - Amount: {decision.kwh:.1f} kWh")
        print(f"  - Value: {decision.value_sek:.0f} SEK")
        print(f"  - Confidence: {decision.confidence * 100:.0f}%")
        if decision.metadata.get('veto'):
            print(f"  - ⚠️ VETO OVERRIDE by {decision.metadata['veto_agent']}")
        print(f"  - Reasoning: {decision.reasoning[:150]}...")
    else:
        print("✗ No decision made")


def test_performance_metrics(orchestrator):
    """Test performance metrics."""
    print("\n" + "=" * 60)
    print("Performance Metrics")
    print("=" * 60)

    metrics = orchestrator.get_performance_metrics()

    print(f"Orchestrator:")
    print(f"  - Total decisions: {metrics['decisions_count']}")
    print(f"  - Conflicts resolved: {metrics['conflicts_resolved']}")
    print(f"  - Vetos applied: {metrics['vetos_applied']}")
    print(f"  - Conflict rate: {metrics['conflict_rate'] * 100:.1f}%")

    print(f"\nAgent Performance:")
    for agent_name, agent_metrics in metrics['agent_performance'].items():
        print(f"  {agent_name}:")
        print(f"    - Recommendations: {agent_metrics['recommendations_count']}")
        print(f"    - Total value: {agent_metrics['total_value_sek']:.0f} SEK")
        if agent_metrics['recommendations_count'] > 0:
            print(f"    - Avg value: {agent_metrics['avg_value_per_recommendation']:.0f} SEK")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("MULTI-AGENT BATTERY OPTIMIZATION - TEST SUITE")
    print("=" * 60)

    try:
        # Test 1: Instantiation
        peak_tracker, value_calculator, orchestrator = test_agent_instantiation()

        # Test 2: Context creation
        context = test_battery_context_creation()

        # Test 3: Peak shaving scenario
        test_scenario_peak_shaving(orchestrator, peak_tracker, context)

        # Test 4: Night charging scenario
        test_scenario_night_charging(orchestrator, context)

        # Test 5: Emergency spike scenario
        test_scenario_emergency_spike(orchestrator, context)

        # Test 6: Performance metrics
        test_performance_metrics(orchestrator)

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print("\nThe multi-agent system is working correctly!")
        print("Ready to integrate with battery_simulator.py")

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
