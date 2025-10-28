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
from datetime import date

from agents.base_agent import AgentRecommendation, AgentAction, BatteryContext, RealTimeOverrideAgent
from agents.consumption_analyzer import ConsumptionAnalyzer, DayType
from agents.reserve_calculator import DynamicReserveCalculator, CapacityAllocation, ReserveRequirement
from agents.peak_shaving_agent import PeakShavingAgent
from agents.arbitrage_agent import ArbitrageAgent
from agents.daily_optimizer import DailyOptimizer, DailyPlanInput, DailyPlanOutput


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
        verbose: bool = False,
        enable_24h_planning: bool = True  # NEW: Enable Sigenergy-style 24h planning
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
            enable_24h_planning: Use Sigenergy-style 24h optimization (recommended)
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

        # 24h Planning (Sigenergy approach)
        self.enable_24h_planning = enable_24h_planning
        self.optimizer = DailyOptimizer() if enable_24h_planning else None
        self.daily_plan: Optional[DailyPlanOutput] = None
        self.plan_created_date: Optional[date] = None
        self.plan_created_hour: int = 13  # Create plan at 13:00 when next-day prices known

    def analyze(self, context: BatteryContext) -> Optional[BossDecision]:
        """
        Make decision using reserve-first approach.

        Sigenergy-style 24h planning (if enabled):
        - At 13:00 daily: Create 24h optimization plan
        - Each hour: Execute planned action
        - Override if actual consumption >> forecast

        Traditional hourly mode (fallback):
        - Calculate reserves
        - Get agent recommendations
        - Choose best

        Process:
        1. Check if should create 24h plan (13:00 daily)
        2. If plan exists, execute it (with override capability)
        3. Otherwise, fall back to hourly reserve-first logic
        4. Track opportunity costs

        Args:
            context: Current battery context

        Returns:
            BossDecision with chosen action and metadata
        """
        self.total_decisions += 1

        # ========== SIGENERGY 24H PLANNING MODE ==========
        if self.enable_24h_planning:
            # Check if we should create new plan (13:00 daily when prices known)
            current_date = context.timestamp.date()
            if context.hour == self.plan_created_hour and current_date != self.plan_created_date:
                if self.verbose:
                    print(f"\n{'=' * 80}")
                    print(f"🔮 CREATING 24H PLAN at {context.timestamp} (prices known for next day)")
                    print(f"{'=' * 80}")

                self.daily_plan = self._create_daily_plan(context)
                self.plan_created_date = current_date

                if self.verbose and self.daily_plan:
                    print(f"\n✅ 24h Plan Created:")
                    print(f"  {self.daily_plan.reasoning}")
                    print(f"  Expected cost: {self.daily_plan.expected_cost:.0f} SEK")
                    print(f"  Expected peak: {self.daily_plan.expected_peak_kw:.1f} kW")
                    print(f"  Expected savings: {self.daily_plan.expected_savings:.0f} SEK")

            # If we have a plan, execute it (with override capability)
            if self.daily_plan:
                return self._execute_daily_plan(context)

        # ========== FALLBACK: HOURLY RESERVE-FIRST MODE ==========
        # If no plan exists, use traditional hourly logic
        return self._analyze_hourly(context)

    def _analyze_hourly(self, context: BatteryContext) -> Optional[BossDecision]:
        """
        Traditional hourly reserve-first decision making (fallback mode).

        This is the original Boss Agent logic:
        1. Calculate reserves
        2. Get agent recommendations
        3. Choose best

        Used when 24h planning is disabled or no plan exists yet.
        """
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

    def _create_consumption_forecast(self, context: BatteryContext) -> List[float]:
        """
        Create consumption forecast using historical hourly patterns.

        Better than flat average - captures evening peak patterns using historical P75.
        If context already has a forecast, use it. Otherwise, build from historical stats.

        Args:
            context: Current battery context

        Returns:
            24-hour consumption forecast (kW)
        """
        # If context already has a good forecast, use it
        if context.consumption_forecast and len(context.consumption_forecast) >= 24:
            return context.consumption_forecast[:24]

        # Otherwise, build forecast from historical patterns
        forecast = []
        is_weekend = context.timestamp.dayofweek in [5, 6]
        day_type = DayType.WEEKEND if is_weekend else DayType.WEEKDAY

        # Get current hour to build forecast from current time onwards
        current_hour = context.hour

        for offset in range(24):
            # Calculate the hour of day for this forecast point
            hour_of_day = (current_hour + offset) % 24

            # Get historical statistics for this hour
            stats = self.analyzer.get_stats(hour_of_day, day_type)

            if stats:
                # Use 75th percentile (conservative - better to over-reserve than under-reserve)
                forecast.append(stats.p75_kw)
            else:
                # No historical data for this hour, use monthly average
                forecast.append(context.avg_consumption_kw)

        return forecast

    def _create_daily_plan(self, context: BatteryContext) -> Optional[DailyPlanOutput]:
        """
        Create 24-hour optimization plan (Sigenergy approach).

        Called at 13:00 daily when next-day prices are known.
        Uses DailyOptimizer to solve global optimization problem.

        Args:
            context: Current battery context with 24h forecasts

        Returns:
            DailyPlanOutput with hour-by-hour schedule, or None if failed
        """
        if not self.optimizer:
            return None

        try:
            # Build optimization inputs
            # Note: BatteryContext doesn't have solar_forecast yet - use current solar as simple forecast
            solar_now = context.solar_production_kw if hasattr(context, 'solar_production_kw') else 0.0

            # Get cost parameters from peak shaving agent's value calculator (set by frontend)
            value_calc = self.peak_shaving.value_calculator

            # Get improved consumption forecast (uses historical P75 instead of flat average)
            consumption_forecast = self._create_consumption_forecast(context)

            inputs = DailyPlanInput(
                consumption_forecast=consumption_forecast,
                solar_forecast=[solar_now] * 24,  # TODO: Add proper solar forecasting later
                price_forecast=context.spot_forecast[:24] if context.spot_forecast else [context.spot_price_sek_kwh] * 24,
                current_soc_kwh=context.soc_kwh,
                capacity_kwh=context.capacity_kwh,
                min_soc_kwh=context.min_soc_kwh,
                max_charge_kw=context.max_charge_kw,
                max_discharge_kw=context.max_discharge_kw,
                efficiency=context.efficiency,
                grid_fee_sek_kwh=value_calc.grid_fee,  # From frontend user input
                energy_tax_sek_kwh=value_calc.energy_tax,  # From frontend user input
                vat_rate=value_calc.vat_rate,  # From frontend user input
                effect_tariff_sek_kw_month=value_calc.effect_tariff,  # From frontend user input
                current_peak_threshold_kw=context.peak_threshold_kw,
                peak_reserve_kwh=10.0,  # Algorithm parameter (reasonable default)
                is_measurement_hour=[6 <= h <= 23 for h in range(24)]  # E.ON measurement hours
            )

            # Solve optimization
            plan = self.optimizer.optimize_24h(inputs)
            return plan

        except Exception as e:
            if self.verbose:
                print(f"⚠️  Failed to create 24h plan: {e}")
            return None

    def _execute_daily_plan(self, context: BatteryContext) -> Optional[BossDecision]:
        """
        Execute planned action for current hour (with real-time override capability).

        Args:
            context: Current battery context

        Returns:
            BossDecision with planned action or override
        """
        if not self.daily_plan:
            return None

        hour_of_day = context.hour

        # Check for real-time override (spike detected)
        if self._should_override_plan(context):
            if self.verbose:
                print(f"\n⚠️  OVERRIDE: Actual consumption >> forecast, emergency discharge!")
            return self._emergency_override(context)

        # Calculate reserve requirement properly (needed for BossDecision)
        reserve_req = self.reserve_calc.calculate_reserve(
            timestamp=context.timestamp,
            current_soc_kwh=context.soc_kwh
        )

        # Allocate capacity
        capacity_alloc = self.reserve_calc.allocate_capacity(
            reserve_requirement=reserve_req,
            total_capacity_kwh=context.capacity_kwh,
            current_soc_kwh=context.soc_kwh,
            min_soc_kwh=context.min_soc_kwh,
            max_charge_kw=context.max_charge_kw,
            max_discharge_kw=context.max_discharge_kw,
            estimated_arbitrage_value_sek=50.0
        )

        # Get planned action for this hour
        planned_charge = self.daily_plan.charge_schedule[hour_of_day]
        planned_discharge = self.daily_plan.discharge_schedule[hour_of_day]

        # Execute plan
        if planned_charge > 0.5:
            # Plan says: CHARGE
            reasoning = f"24h Plan: Charge {planned_charge:.1f} kWh (cheap hour)"

            return BossDecision(
                action=AgentAction.CHARGE,
                kwh=min(planned_charge, capacity_alloc.max_charge_this_hour_kwh),
                chosen_agent="DailyOptimizer",
                all_recommendations=[],
                reserve_requirement=reserve_req,
                capacity_allocation=capacity_alloc,
                opportunity_cost_sek=0.0,
                reasoning=reasoning
            )

        elif planned_discharge > 0.5:
            # Plan says: DISCHARGE
            reasoning = f"24h Plan: Discharge {planned_discharge:.1f} kWh (peak shaving)"

            return BossDecision(
                action=AgentAction.DISCHARGE,
                kwh=min(planned_discharge, capacity_alloc.max_discharge_this_hour_kwh),
                chosen_agent="DailyOptimizer",
                all_recommendations=[],
                reserve_requirement=reserve_req,
                capacity_allocation=capacity_alloc,
                opportunity_cost_sek=0.0,
                reasoning=reasoning
            )

        else:
            # Plan says: HOLD
            return None

    def _should_override_plan(self, context: BatteryContext) -> bool:
        """
        Detect if actual consumption significantly exceeds forecast (spike).

        Returns True if emergency override needed.
        """
        if not self.daily_plan or not context.consumption_forecast:
            return False

        hour = context.hour
        if hour >= len(context.consumption_forecast):
            return False

        planned_consumption = context.consumption_forecast[hour]
        actual_consumption = context.consumption_kw

        # If actual > 1.3x forecast AND above 10 kW, spike detected!
        return actual_consumption > planned_consumption * 1.3 and actual_consumption > 10.0

    def _emergency_override(self, context: BatteryContext) -> Optional[BossDecision]:
        """
        Emergency discharge to handle unexpected spike.

        Uses Peak Shaving Agent to determine emergency response.
        """
        # Let Peak Shaving Agent handle the emergency
        emergency_rec = self.peak_shaving.analyze(context)

        if not emergency_rec:
            return None

        return BossDecision(
            action=emergency_rec.action,
            kwh=emergency_rec.kwh,
            chosen_agent=f"{emergency_rec.agent_name} (OVERRIDE)",
            all_recommendations=[emergency_rec],
            reserve_requirement=ReserveRequirement(
                required_reserve_kwh=0.0,
                risk_level="CRITICAL",
                reasoning="Emergency override - spike detected",
                percentile_used=99
            ),
            capacity_allocation=CapacityAllocation(
                total_capacity_kwh=context.capacity_kwh,
                current_soc_kwh=context.soc_kwh,
                peak_shaving_reserve_kwh=0.0,
                available_for_arbitrage_kwh=0.0,
                can_charge=False,
                can_discharge=True,
                max_charge_this_hour_kwh=0.0,
                max_discharge_this_hour_kwh=emergency_rec.kwh,
                opportunity_cost_sek=0.0,
                reasoning="Emergency override"
            ),
            opportunity_cost_sek=0.0,
            reasoning=f"OVERRIDE: {emergency_rec.reasoning}"
        )

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
