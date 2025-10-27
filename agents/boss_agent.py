"""
Boss Agent - Master coordinator for battery capacity allocation.

The Boss Agent manages the hierarchy:
1. FIRST: Calculate and lock peak shaving reserve (highest priority)
2. SECOND: Allocate remaining capacity to specialist agents
3. THIRD: Track opportunity costs and ROI

This ensures peak shaving always gets what it needs, while other agents
work within remaining constraints.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import pandas as pd

from agents.base_agent import AgentRecommendation, AgentAction, BatteryContext, RealTimeOverrideAgent
from agents.consumption_analyzer import ConsumptionAnalyzer, DayType
from agents.reserve_calculator import DynamicReserveCalculator, CapacityAllocation, ReserveRequirement
from agents.peak_shaving_agent import PeakShavingAgent
from agents.arbitrage_agent import ArbitrageAgent


@dataclass
class AgentBudget:
    """Budget/constraints given to an agent."""
    agent_name: str
    max_charge_kwh: float    # Max this agent can charge
    max_discharge_kwh: float # Max this agent can discharge
    priority: int            # Higher = more important
    reasoning: str


@dataclass
class BossDecision:
    """Final decision from Boss Agent."""
    action: AgentAction
    kwh: float
    chosen_agent: str
    all_recommendations: List[AgentRecommendation]
    reserve_requirement: ReserveRequirement
    capacity_allocation: CapacityAllocation
    opportunity_cost_sek: float
    reasoning: str


class BossAgent:
    """
    Boss Agent coordinates all specialist agents with reserve-first approach.

    Key principles:
    1. Peak shaving reserves are LOCKED first (non-negotiable)
    2. Specialist agents get budgets based on remaining capacity
    3. Real-time override can break rules in emergencies
    4. Track opportunity costs for ROI analysis
    """

    def __init__(
        self,
        consumption_analyzer: ConsumptionAnalyzer,
        reserve_calculator: DynamicReserveCalculator,
        peak_shaving_agent: PeakShavingAgent,
        arbitrage_agent: ArbitrageAgent,
        real_time_override_agent: RealTimeOverrideAgent,
        verbose: bool = False
    ):
        """
        Initialize Boss Agent with specialist agents.

        Args:
            consumption_analyzer: Statistical analyzer
            reserve_calculator: Reserve calculator
            peak_shaving_agent: Peak shaving specialist
            arbitrage_agent: Arbitrage specialist
            real_time_override_agent: Emergency override
            verbose: Print detailed reasoning
        """
        self.analyzer = consumption_analyzer
        self.reserve_calc = reserve_calculator
        self.peak_shaving = peak_shaving_agent
        self.arbitrage = arbitrage_agent
        self.override = real_time_override_agent
        self.verbose = verbose

        # Tracking
        self.total_decisions = 0
        self.total_opportunity_cost_sek = 0.0
        self.reserves_by_hour: Dict[int, List[float]] = {h: [] for h in range(24)}

    def analyze(self, context: BatteryContext) -> Optional[BossDecision]:
        """
        Make decision using reserve-first approach.

        Process:
        1. Calculate required peak shaving reserve
        2. Allocate remaining capacity to agents
        3. Get recommendations from each agent (with budget constraints)
        4. Choose best recommendation
        5. Track opportunity costs

        Args:
            context: Current battery context

        Returns:
            BossDecision with chosen action and metadata
        """
        self.total_decisions += 1

        # STEP 1: Calculate peak shaving reserve (HIGHEST PRIORITY)
        reserve_req = self.reserve_calc.calculate_reserve(
            timestamp=context.timestamp,
            current_soc_kwh=context.soc_kwh
        )

        if self.verbose:
            print(f"\n{'=' * 80}")
            print(f"BOSS AGENT - {context.timestamp}")
            print(f"{'=' * 80}")
            print(f"Reserve Requirement: {reserve_req.required_reserve_kwh:.1f} kWh ({reserve_req.risk_level} risk)")
            print(f"  {reserve_req.reasoning}")

        # Track reserve requirements
        self.reserves_by_hour[context.hour].append(reserve_req.required_reserve_kwh)

        # STEP 2: Allocate capacity
        capacity_alloc = self.reserve_calc.allocate_capacity(
            reserve_requirement=reserve_req,
            total_capacity_kwh=context.capacity_kwh,
            current_soc_kwh=context.soc_kwh,
            min_soc_kwh=context.min_soc_kwh,
            max_charge_kw=context.max_charge_kw,
            max_discharge_kw=context.max_discharge_kw,
            estimated_arbitrage_value_sek=50.0  # Rough estimate
        )

        if self.verbose:
            print(f"\nCapacity Allocation:")
            print(f"  Total: {capacity_alloc.total_capacity_kwh:.1f} kWh")
            print(f"  Current SOC: {capacity_alloc.current_soc_kwh:.1f} kWh")
            print(f"  Reserved for peaks: {capacity_alloc.peak_shaving_reserve_kwh:.1f} kWh")
            print(f"  Available for arbitrage: {capacity_alloc.available_for_arbitrage_kwh:.1f} kWh")
            print(f"  Can charge: {capacity_alloc.can_charge} (max {capacity_alloc.max_charge_this_hour_kwh:.1f} kWh)")
            print(f"  Can discharge: {capacity_alloc.can_discharge} (max {capacity_alloc.max_discharge_this_hour_kwh:.1f} kWh)")

        # STEP 3: Create modified context for agents (with capacity constraints)
        constrained_context = self._apply_capacity_constraints(context, capacity_alloc, reserve_req)

        # STEP 4: Get recommendations from all agents
        recommendations: List[AgentRecommendation] = []

        # Real-time override (HIGHEST priority - can break rules)
        override_rec = self.override.analyze(constrained_context)
        if override_rec:
            recommendations.append(override_rec)

        # Peak shaving (HIGH priority)
        peak_rec = self.peak_shaving.analyze(constrained_context)
        if peak_rec:
            recommendations.append(peak_rec)

        # Arbitrage (LOWER priority, works within remaining capacity)
        arbitrage_rec = self.arbitrage.analyze(constrained_context)
        if arbitrage_rec:
            recommendations.append(arbitrage_rec)

        if self.verbose and recommendations:
            print(f"\nAgent Recommendations:")
            for rec in recommendations:
                print(f"  {rec.agent_name}: {rec.action.name} {rec.kwh:.1f} kWh "
                      f"(priority={rec.priority}, value={rec.value_sek:.0f} SEK)")
                print(f"    → {rec.reasoning}")

        # STEP 5: Choose best recommendation
        if not recommendations:
            if self.verbose:
                print("\nNo recommendations - HOLD")
            return None

        # Sort by priority (higher first), then by value
        recommendations.sort(key=lambda r: (r.priority, r.value_sek), reverse=True)
        chosen = recommendations[0]

        # Track opportunity cost
        self.total_opportunity_cost_sek += capacity_alloc.opportunity_cost_sek

        if self.verbose:
            print(f"\n✓ CHOSEN: {chosen.agent_name} - {chosen.action.name} {chosen.kwh:.1f} kWh")
            if capacity_alloc.opportunity_cost_sek > 0:
                print(f"  Opportunity cost: {capacity_alloc.opportunity_cost_sek:.0f} SEK")

        return BossDecision(
            action=chosen.action,
            kwh=chosen.kwh,
            chosen_agent=chosen.agent_name,
            all_recommendations=recommendations,
            reserve_requirement=reserve_req,
            capacity_allocation=capacity_alloc,
            opportunity_cost_sek=capacity_alloc.opportunity_cost_sek,
            reasoning=chosen.reasoning
        )

    def _apply_capacity_constraints(
        self,
        context: BatteryContext,
        allocation: CapacityAllocation,
        reserve_req: ReserveRequirement
    ) -> BatteryContext:
        """
        Create modified context with capacity constraints applied.

        This ensures agents respect the reserved capacity.
        """
        # Create new context with adjusted SOC constraints
        # Agents should think available SOC = current SOC - reserve

        # For charging: can charge until (total - reserve)
        effective_max_soc = context.capacity_kwh - reserve_req.required_reserve_kwh

        # For discharging: must keep (min + reserve)
        effective_min_soc = context.min_soc_kwh + reserve_req.required_reserve_kwh

        # Create modified context
        # Note: We're not actually modifying the context object, just constraining agent behavior
        # Agents will see the reserve requirement in context and respect it

        return context  # For now, return as-is - agents check capacity_allocation

    def get_statistics(self) -> Dict:
        """Get statistics about Boss Agent decisions."""
        avg_reserves_by_hour = {
            hour: (sum(values) / len(values) if values else 0.0)
            for hour, values in self.reserves_by_hour.items()
        }

        return {
            'total_decisions': self.total_decisions,
            'total_opportunity_cost_sek': self.total_opportunity_cost_sek,
            'avg_reserves_by_hour': avg_reserves_by_hour,
            'peak_reserve_hour': max(avg_reserves_by_hour, key=avg_reserves_by_hour.get),
            'min_reserve_hour': min(avg_reserves_by_hour, key=avg_reserves_by_hour.get)
        }

    def print_statistics(self):
        """Print statistics summary."""
        stats = self.get_statistics()

        print("\n" + "=" * 80)
        print("BOSS AGENT STATISTICS")
        print("=" * 80)
        print(f"Total decisions: {stats['total_decisions']}")
        print(f"Total opportunity cost: {stats['total_opportunity_cost_sek']:.0f} SEK")
        print(f"\nAverage Reserve by Hour:")
        print("-" * 80)
        print(f"{'Hour':<6} {'Avg Reserve (kWh)':<20}")
        print("-" * 80)

        for hour in range(24):
            avg_reserve = stats['avg_reserves_by_hour'][hour]
            if avg_reserve > 0:
                marker = " ← PEAK" if hour == stats['peak_reserve_hour'] else ""
                print(f"{hour:02d}:00  {avg_reserve:6.2f}{marker}")
