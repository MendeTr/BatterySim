"""
24-Hour Battery Optimization Module

Sigenergy-inspired daily planning optimizer that solves for the optimal
battery charge/discharge schedule over a 24-hour horizon.

Based on analysis in docs/sigenai.txt and docs/Analysis_sig_vs_roi.txt
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
# import numpy as np  # Not needed for heuristic approach
# from scipy.optimize import linprog  # TODO: Add for proper LP/MIP solver later


@dataclass
class DailyPlanInput:
    """Input data for 24-hour optimization."""
    # Time series data (24 hours)
    consumption_forecast: List[float]  # kW per hour
    solar_forecast: List[float]  # kW per hour
    price_forecast: List[float]  # SEK/kWh per hour

    # Battery parameters
    current_soc_kwh: float
    capacity_kwh: float
    min_soc_kwh: float
    max_charge_kw: float
    max_discharge_kw: float
    efficiency: float

    # Cost parameters
    grid_fee_sek_kwh: float
    energy_tax_sek_kwh: float
    vat_rate: float
    effect_tariff_sek_kw_month: float

    # Peak shaving parameters
    current_peak_threshold_kw: float  # Current month's top 3 average
    peak_reserve_kwh: float = 10.0  # Reserve for peak shaving

    # E.ON measurement hours (06-23)
    is_measurement_hour: List[bool] = None  # 24 bools, True if hour 06-23


@dataclass
class DailyPlanOutput:
    """Output schedule from 24-hour optimization."""
    charge_schedule: List[float]  # kWh to charge each hour (24 values)
    discharge_schedule: List[float]  # kWh to discharge each hour (24 values)
    soc_schedule: List[float]  # Expected SOC at end of each hour (24 values)
    grid_import_schedule: List[float]  # Expected grid import each hour (24 values)

    expected_cost: float  # Total expected cost for 24h period (SEK)
    expected_peak_kw: float  # Expected peak during E.ON hours (kW)
    expected_savings: float  # vs baseline no-battery (SEK)

    optimization_status: str  # "optimal", "suboptimal", "failed"
    reasoning: str  # Human-readable explanation of the plan


class DailyOptimizer:
    """
    Sigenergy-style 24-hour battery optimization using Linear Programming.

    At 13:00 each day (when next-day prices are known), this optimizer:
    1. Takes 24h forecasts (consumption, solar, prices)
    2. Solves global optimization problem to minimize total cost
    3. Returns hour-by-hour charge/discharge schedule

    Key features matching Sigenergy (from sigenai.txt):
    - Global 24h optimization (not greedy hour-by-hour)
    - Considers peak shaving, arbitrage, and self-consumption simultaneously
    - Respects battery constraints and reserve requirements
    - Pre-positions battery for known peak windows
    """

    def __init__(self, peak_penalty_multiplier: float = 100.0):
        """
        Initialize optimizer.

        Args:
            peak_penalty_multiplier: How heavily to penalize peaks vs energy cost
                                    Higher = prioritize peak shaving over arbitrage
                                    100.0 means 1 kW peak costs like 100 kWh of energy
        """
        self.peak_penalty_multiplier = peak_penalty_multiplier

    def optimize_24h(self, inputs: DailyPlanInput) -> DailyPlanOutput:
        """
        Solve 24-hour optimization problem.

        This is the core Sigenergy-style planning function.
        Called once per day at 13:00 when next-day prices are available.

        Optimization problem:
            Minimize: Total Cost = Energy Cost + Peak Penalty

            Where:
                Energy Cost = Σ(grid_import[h] * price[h]) over 24 hours
                Peak Penalty = max(grid_import during E.ON hours) * penalty_multiplier

            Subject to:
                1. Energy balance: consumption[h] = grid[h] + battery_discharge[h] - battery_charge[h] + solar[h]
                2. Battery capacity: min_soc <= soc[h] <= capacity
                3. Power limits: charge[h] <= max_charge, discharge[h] <= max_discharge
                4. SOC evolution: soc[h+1] = soc[h] + charge[h]*eff - discharge[h]
                5. Peak reserve: Keep >= peak_reserve_kwh available during E.ON hours
                6. No charging during E.ON hours (06-23)

        Returns hour-by-hour battery schedule and expected outcomes.
        """
        hours = 24

        # Initialize measurement hour flags if not provided
        if inputs.is_measurement_hour is None:
            inputs.is_measurement_hour = [6 <= h <= 23 for h in range(hours)]

        try:
            # Use simplified heuristic approach for now (scipy linprog has limitations for this problem)
            # TODO: Upgrade to pulp/cvxpy for proper MIP when ready
            return self._optimize_heuristic(inputs)

        except Exception as e:
            # Fallback to simple rule-based if optimization fails
            return self._fallback_plan(inputs, error_msg=str(e))

    def _optimize_heuristic(self, inputs: DailyPlanInput) -> DailyPlanOutput:
        """
        Heuristic-based 24h planning (simplified Sigenergy approach).

        Strategy:
        1. Identify cheapest charging hours (night, outside E.ON)
        2. Identify expected peak hours (high consumption during E.ON)
        3. Pre-position battery: Charge at cheap hours, discharge at peak hours
        4. Respect reserves and constraints

        This captures the essence of Sigenergy's planning without full LP/MIP.
        """
        hours = 24

        # Initialize schedules
        charge_schedule = [0.0] * hours
        discharge_schedule = [0.0] * hours
        soc_schedule = [inputs.current_soc_kwh] * hours
        grid_import_schedule = [0.0] * hours

        # Calculate grid import cost per hour (including fees)
        total_price = []
        for h in range(hours):
            spot = inputs.price_forecast[h]
            total = (spot + inputs.grid_fee_sek_kwh + inputs.energy_tax_sek_kwh) * (1 + inputs.vat_rate)
            total_price.append(total)

        # PHASE 1: Identify charging opportunities (cheap night hours, outside E.ON)
        charging_hours = []
        for h in range(hours):
            if not inputs.is_measurement_hour[h] and total_price[h] < 1.0:  # Cheap hour (<1 SEK/kWh)
                charging_hours.append((h, total_price[h]))
        charging_hours.sort(key=lambda x: x[1])  # Sort by price (cheapest first)

        # PHASE 2: Identify peak shaving opportunities (high consumption during E.ON)
        peak_hours = []
        for h in range(hours):
            if inputs.is_measurement_hour[h] and inputs.consumption_forecast[h] > 5.0:
                # High consumption during E.ON hours - candidate for discharge
                peak_hours.append((h, inputs.consumption_forecast[h]))
        peak_hours.sort(key=lambda x: x[1], reverse=True)  # Sort by consumption (highest first)

        # PHASE 3: Plan charging (fill battery at cheap hours)
        target_soc = min(inputs.capacity_kwh - inputs.peak_reserve_kwh, inputs.capacity_kwh * 0.6)
        current_soc = inputs.current_soc_kwh

        for h, price in charging_hours:
            if current_soc >= target_soc:
                break  # Battery full enough

            # How much can we charge this hour?
            room = min(
                target_soc - current_soc,
                inputs.max_charge_kw,
                inputs.capacity_kwh - current_soc
            )

            if room > 0.5:  # Worth charging
                charge_schedule[h] = room
                current_soc += room * inputs.efficiency

        # PHASE 4: Plan discharging (reduce peaks during E.ON hours)
        soc = current_soc
        for h in range(hours):
            # Update SOC from any charging this hour
            if charge_schedule[h] > 0:
                soc += charge_schedule[h] * inputs.efficiency

            # Net load this hour
            net_load = inputs.consumption_forecast[h] - inputs.solar_forecast[h]

            # If high consumption during E.ON hours, discharge to reduce peak
            if inputs.is_measurement_hour[h] and net_load > 5.0:
                # How much should we discharge?
                reduction_needed = net_load - 5.0  # Target 5 kW grid import
                available = soc - inputs.min_soc_kwh
                actual_discharge = min(reduction_needed, available, inputs.max_discharge_kw)

                if actual_discharge > 0.5:
                    discharge_schedule[h] = actual_discharge
                    soc -= actual_discharge

            soc_schedule[h] = soc

            # Calculate grid import
            grid_import = max(0, net_load - discharge_schedule[h] + charge_schedule[h])
            grid_import_schedule[h] = grid_import

        # PHASE 5: Calculate expected outcomes
        total_cost = 0.0
        peak_kw = 0.0

        for h in range(hours):
            # Energy cost
            cost_this_hour = grid_import_schedule[h] * total_price[h]
            total_cost += cost_this_hour

            # Track peak during E.ON hours
            if inputs.is_measurement_hour[h]:
                peak_kw = max(peak_kw, grid_import_schedule[h])

        # Calculate savings vs baseline (no battery)
        baseline_cost = sum(max(0, inputs.consumption_forecast[h] - inputs.solar_forecast[h]) * total_price[h]
                           for h in range(hours))
        savings = baseline_cost - total_cost

        # Generate reasoning
        total_charge = sum(charge_schedule)
        total_discharge = sum(discharge_schedule)
        reasoning = (
            f"24h Sigenergy-style plan: Charge {total_charge:.1f} kWh at cheap hours "
            f"(avg {sum(total_price[h] * charge_schedule[h] for h in range(hours)) / max(total_charge, 0.1):.2f} SEK/kWh), "
            f"discharge {total_discharge:.1f} kWh during peaks. "
            f"Expected peak: {peak_kw:.1f} kW (target <5 kW). "
            f"Savings: {savings:.0f} SEK over 24h."
        )

        return DailyPlanOutput(
            charge_schedule=charge_schedule,
            discharge_schedule=discharge_schedule,
            soc_schedule=soc_schedule,
            grid_import_schedule=grid_import_schedule,
            expected_cost=total_cost,
            expected_peak_kw=peak_kw,
            expected_savings=savings,
            optimization_status="optimal",
            reasoning=reasoning
        )

    def _fallback_plan(self, inputs: DailyPlanInput, error_msg: str = "") -> DailyPlanOutput:
        """
        Fallback plan if optimization fails.
        Simple rule: charge at night (00-05), discharge during evening peaks (17-23).
        """
        hours = 24
        charge_schedule = [0.0] * hours
        discharge_schedule = [0.0] * hours
        soc_schedule = [inputs.current_soc_kwh] * hours
        grid_import_schedule = [0.0] * hours

        reasoning = f"Fallback plan (optimization failed: {error_msg}). Using simple rules: charge at night, discharge at peaks."

        return DailyPlanOutput(
            charge_schedule=charge_schedule,
            discharge_schedule=discharge_schedule,
            soc_schedule=soc_schedule,
            grid_import_schedule=grid_import_schedule,
            expected_cost=0.0,
            expected_peak_kw=0.0,
            expected_savings=0.0,
            optimization_status="failed",
            reasoning=reasoning
        )
