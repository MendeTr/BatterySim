"""
Dynamic reserve calculator for peak shaving.

Calculates how much battery capacity to reserve for peak shaving based on:
- Statistical analysis of consumption patterns
- Risk tolerance settings
- Time of day and day type
- Current battery state
"""

from typing import Optional
import pandas as pd
from agents.consumption_analyzer import (
    ConsumptionAnalyzer, ConsumptionStats, ReserveRequirement,
    CapacityAllocation, DayType
)


class DynamicReserveCalculator:
    """
    Calculates dynamic battery reserves for peak shaving.

    The reserve is sized to handle unexpected consumption spikes based on
    historical percentile analysis rather than trying to predict exact values.
    """

    def __init__(
        self,
        consumption_analyzer: ConsumptionAnalyzer,
        grid_import_limit_kw: float = 5.0,
        max_discharge_kw: float = 12.0,
        default_percentile: int = 95,
        safety_buffer: float = 1.15,
        spike_duration_hours: float = 0.5,
        min_reserve_kwh: float = 2.0,
        max_reserve_kwh: float = 15.0
    ):
        """
        Initialize reserve calculator.

        Args:
            consumption_analyzer: Analyzer with historical consumption stats
            grid_import_limit_kw: Target grid import limit (Swedish effect tariff optimization)
            max_discharge_kw: Max battery discharge power (inverter limit, typically 12 kW)
            default_percentile: Default risk percentile (90, 95, or 99)
            safety_buffer: Safety multiplier (1.1-1.2) for discharge limits
            spike_duration_hours: Assumed spike duration (0.5 = 30 min, conservative)
            min_reserve_kwh: Minimum reserve to always maintain
            max_reserve_kwh: Maximum reserve (cap at reasonable level)
        """
        self.analyzer = consumption_analyzer
        self.grid_import_limit_kw = grid_import_limit_kw
        self.max_discharge_kw = max_discharge_kw
        self.default_percentile = default_percentile
        self.safety_buffer = safety_buffer
        self.spike_duration_hours = spike_duration_hours
        self.min_reserve_kwh = min_reserve_kwh
        self.max_reserve_kwh = max_reserve_kwh

    def calculate_reserve(
        self,
        timestamp: pd.Timestamp,
        current_soc_kwh: float,
        percentile_override: Optional[int] = None
    ) -> ReserveRequirement:
        """
        Calculate required battery reserve for peak shaving.

        Args:
            timestamp: Current timestamp
            current_soc_kwh: Current battery state of charge
            percentile_override: Override default percentile

        Returns:
            ReserveRequirement with calculated reserve and metadata
        """
        hour = timestamp.hour
        is_weekend = timestamp.dayofweek in [5, 6]
        day_type = DayType.WEEKEND if is_weekend else DayType.WEEKDAY

        # Get consumption statistics
        stats = self.analyzer.get_stats(hour, day_type)

        if not stats:
            # No data available, use conservative default
            return self._create_fallback_reserve(timestamp, hour, day_type)

        # Determine which percentile to use
        if percentile_override:
            percentile = percentile_override
        else:
            percentile = self.analyzer.get_recommended_percentile(hour, day_type, self.default_percentile)

        # Get expected peak at chosen percentile
        expected_peak_kw = stats.get_percentile(percentile)

        # Calculate reduction needed to hit target
        # Goal: reduce peak to acceptable level (5-6 kW), not eliminate entirely
        reduction_needed_kw = max(0, expected_peak_kw - self.grid_import_limit_kw)

        # Limit by inverter max discharge power
        # Can't discharge more than inverter allows (typically 12 kW)
        actual_reduction_kw = min(reduction_needed_kw, self.max_discharge_kw)

        # Calculate energy reserve needed
        # Key insight: Spikes are usually SHORT (not entire hour)
        # Reserve = power × spike_duration
        # Example: 12 kW for 30 min (0.5 hr) = 6 kWh
        raw_reserve_kwh = actual_reduction_kw * self.spike_duration_hours

        # Apply safety buffer (account for discharge inefficiency, prediction error)
        required_reserve_kwh = raw_reserve_kwh * self.safety_buffer

        # Clamp to min/max bounds
        required_reserve_kwh = max(self.min_reserve_kwh, min(self.max_reserve_kwh, required_reserve_kwh))

        # Get risk level
        risk_level = self.analyzer.get_risk_level(hour, day_type)

        # Calculate confidence based on sample size and variability
        confidence = self._calculate_confidence(stats, percentile)

        # Build reasoning string
        reasoning = self._build_reasoning(
            hour, day_type, percentile, expected_peak_kw,
            raw_reserve_kwh, required_reserve_kwh, risk_level, stats
        )

        return ReserveRequirement(
            timestamp=timestamp,
            hour=hour,
            day_type=day_type,
            expected_peak_kw=expected_peak_kw,
            grid_import_limit_kw=self.grid_import_limit_kw,
            raw_reserve_kwh=raw_reserve_kwh,
            safety_buffer=self.safety_buffer,
            required_reserve_kwh=required_reserve_kwh,
            percentile_used=percentile,
            confidence=confidence,
            risk_level=risk_level,
            reasoning=reasoning,
            consumption_stats=stats
        )

    def allocate_capacity(
        self,
        reserve_requirement: ReserveRequirement,
        total_capacity_kwh: float,
        current_soc_kwh: float,
        min_soc_kwh: float,
        max_charge_kw: float,
        max_discharge_kw: float,
        estimated_arbitrage_value_sek: float = 0.0
    ) -> CapacityAllocation:
        """
        Allocate battery capacity between peak shaving reserve and other uses.

        Args:
            reserve_requirement: Required reserve for peak shaving
            total_capacity_kwh: Total battery capacity
            current_soc_kwh: Current state of charge
            min_soc_kwh: Technical minimum SOC
            max_charge_kw: Max charge power
            max_discharge_kw: Max discharge power
            estimated_arbitrage_value_sek: Estimated arbitrage opportunity value

        Returns:
            CapacityAllocation showing how capacity is split
        """
        required_reserve = reserve_requirement.required_reserve_kwh

        # Calculate available capacity for arbitrage
        # Available = Current SOC - Technical Min - Peak Shaving Reserve
        available_for_arbitrage = max(0, current_soc_kwh - min_soc_kwh - required_reserve)

        # Determine if we can charge/discharge
        can_charge = current_soc_kwh < total_capacity_kwh
        can_discharge = current_soc_kwh > (min_soc_kwh + required_reserve)

        # Calculate max charge/discharge this hour
        max_charge_this_hour = min(
            max_charge_kw,
            total_capacity_kwh - current_soc_kwh
        ) if can_charge else 0.0

        max_discharge_this_hour = min(
            max_discharge_kw,
            current_soc_kwh - min_soc_kwh - required_reserve
        ) if can_discharge else 0.0

        # Calculate opportunity cost
        # If we have less available capacity than ideal, we lose arbitrage opportunities
        opportunity_cost = 0.0
        if available_for_arbitrage < (total_capacity_kwh * 0.5):
            # We're constraining arbitrage by more than 50%
            opportunity_cost = estimated_arbitrage_value_sek * 0.5

        return CapacityAllocation(
            total_capacity_kwh=total_capacity_kwh,
            current_soc_kwh=current_soc_kwh,
            peak_shaving_reserve_kwh=required_reserve,
            available_for_arbitrage_kwh=available_for_arbitrage,
            minimum_soc_kwh=min_soc_kwh,
            can_charge=can_charge,
            can_discharge=can_discharge,
            max_charge_this_hour_kwh=max_charge_this_hour,
            max_discharge_this_hour_kwh=max_discharge_this_hour,
            opportunity_cost_sek=opportunity_cost
        )

    def _calculate_confidence(self, stats: ConsumptionStats, percentile: int) -> float:
        """
        Calculate confidence level in reserve calculation.

        Based on:
        - Sample size (more samples = higher confidence)
        - Variability (lower CV = higher confidence)
        - Percentile chosen (lower percentile = lower confidence)
        """
        # Sample size factor (0.5-1.0)
        sample_factor = min(1.0, stats.sample_count / 30.0)  # Full confidence at 30+ samples

        # Variability factor (0.5-1.0)
        cv = stats.std_kw / stats.mean_kw if stats.mean_kw > 0 else 2.0
        variability_factor = max(0.5, 1.0 - (cv - 0.5) / 2.0)  # Lower for high CV

        # Percentile factor
        percentile_factor = {
            90: 0.8,
            95: 0.9,
            99: 1.0
        }.get(percentile, 0.85)

        return sample_factor * variability_factor * percentile_factor

    def _build_reasoning(
        self,
        hour: int,
        day_type: DayType,
        percentile: int,
        expected_peak_kw: float,
        raw_reserve_kwh: float,
        final_reserve_kwh: float,
        risk_level: str,
        stats: ConsumptionStats
    ) -> str:
        """Build human-readable reasoning string."""
        reduction_kw = min(expected_peak_kw - self.grid_import_limit_kw, self.max_discharge_kw)
        resulting_peak = expected_peak_kw - reduction_kw

        return (
            f"Hour {hour:02d}:00 {day_type.value}: {risk_level.upper()} risk. "
            f"Historical P{percentile}={expected_peak_kw:.1f} kW. "
            f"Discharge {reduction_kw:.1f} kW for {self.spike_duration_hours*60:.0f} min → "
            f"reduce to ~{resulting_peak:.1f} kW. "
            f"Reserve {final_reserve_kwh:.1f} kWh ({raw_reserve_kwh:.1f} + {(self.safety_buffer - 1.0) * 100:.0f}% buffer)."
        )

    def _create_fallback_reserve(
        self,
        timestamp: pd.Timestamp,
        hour: int,
        day_type: DayType
    ) -> ReserveRequirement:
        """Create conservative fallback reserve when no data available."""
        # Conservative assumption: expect 8 kW peak
        expected_peak_kw = 8.0
        raw_reserve_kwh = max(0, expected_peak_kw - self.grid_import_limit_kw)
        required_reserve_kwh = raw_reserve_kwh * self.safety_buffer

        # Create minimal stats
        stats = ConsumptionStats(
            hour=hour,
            day_type=day_type,
            time_of_day=self.analyzer._get_time_of_day(hour),
            sample_count=0,
            mean_kw=2.0,
            median_kw=1.5,
            std_kw=2.0,
            min_kw=0.0,
            max_kw=10.0,
            p50_kw=1.5,
            p75_kw=3.0,
            p90_kw=5.0,
            p95_kw=7.0,
            p99_kw=9.0
        )

        return ReserveRequirement(
            timestamp=timestamp,
            hour=hour,
            day_type=day_type,
            expected_peak_kw=expected_peak_kw,
            grid_import_limit_kw=self.grid_import_limit_kw,
            raw_reserve_kwh=raw_reserve_kwh,
            safety_buffer=self.safety_buffer,
            required_reserve_kwh=required_reserve_kwh,
            percentile_used=95,
            confidence=0.5,
            risk_level="high",
            reasoning=f"No historical data for hour {hour:02d}. Using conservative fallback reserve.",
            consumption_stats=stats
        )
