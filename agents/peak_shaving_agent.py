"""
Peak Shaving Agent - Specialist agent for managing E.ON effect tariff.

This agent focuses on reducing the top-3 monthly peaks during
measurement hours (06:00-23:00) to minimize effect tariff costs.

Strategy:
1. Monitor current peaks vs threshold
2. Reserve battery capacity for potential peaks
3. Discharge proactively when consumption approaches threshold
4. Balance peak shaving with opportunity cost of battery usage
"""

from typing import Optional
from datetime import datetime
from .base_agent import BaseAgent, AgentRecommendation, AgentAction, BatteryContext
from .peak_tracker import PeakTracker
from .value_calculator import ValueCalculator


class PeakShavingAgent(BaseAgent):
    """
    Specialist agent for peak shaving optimization.

    Uses real-time peak tracking to make intelligent decisions about
    when to discharge battery to reduce effect tariff.
    """

    def __init__(
        self,
        peak_tracker: PeakTracker,
        value_calculator: ValueCalculator,
        target_peak_kw: float = 5.0,
        aggressive_threshold_multiplier: float = 0.9
    ):
        """
        Initialize peak shaving agent.

        Args:
            peak_tracker: Shared PeakTracker instance for monitoring peaks
            value_calculator: Shared ValueCalculator for economic analysis
            target_peak_kw: Target grid import level during E.ON hours
            aggressive_threshold_multiplier: When to act aggressively (0.9 = 90% of threshold)
        """
        super().__init__("PeakShavingAgent", enabled=True)
        self.peak_tracker = peak_tracker
        self.value_calculator = value_calculator
        self.target_peak_kw = target_peak_kw
        self.aggressive_threshold = aggressive_threshold_multiplier

    def analyze(self, context: BatteryContext) -> Optional[AgentRecommendation]:
        """
        Analyze whether to discharge for peak shaving.

        Decision logic:
        1. Only act during E.ON measurement hours (06:00-23:00)
        2. Check consumption forecast for upcoming peaks (PROACTIVE)
        3. Check if current consumption threatens peak threshold (REACTIVE)
        4. Calculate economic value of reducing peak
        5. Recommend discharge if value justifies battery usage
        """
        # Only act during E.ON measurement hours
        if not context.is_measurement_hour:
            return None

        # Get current month's peak situation
        month_key = context.current_month
        threshold_kw = context.peak_threshold_kw
        top_peaks = context.top_n_peaks

        # PROACTIVE: Check consumption forecast for upcoming peaks
        # This allows us to act BEFORE the peak happens
        # NOTE: For 24h planning mode, this will be used by the optimizer
        # For now, this code path is for backwards compatibility with hourly mode
        if context.consumption_forecast:
            # Look ahead at full forecast (up to 24 hours for proper planning)
            upcoming_hours = min(24, len(context.consumption_forecast))
            max_upcoming_consumption = max(context.consumption_forecast[:upcoming_hours]) if upcoming_hours > 0 else 0

            # If high consumption expected soon (> threshold * 0.9)
            if max_upcoming_consumption > threshold_kw * 0.9:
                # Proactively prepare to discharge
                # This is lower priority than reactive, but helps us get ahead of peaks
                expected_peak_reduction = max_upcoming_consumption - self.target_peak_kw
                available_discharge = context.soc_kwh - context.min_soc_kwh

                if expected_peak_reduction > 1.0 and available_discharge > expected_peak_reduction:
                    # We have enough battery to handle the upcoming peak
                    # Don't discharge yet, but signal readiness with metadata
                    # The orchestrator can use this to avoid charging decisions
                    pass  # For now, just let reactive logic handle it

        # Calculate potential peak from current consumption
        potential_peak_kw = context.grid_import_kw

        # Decision tree based on peak situation
        recommendation = None

        # Case 1: CRITICAL - About to exceed threshold (or already in top 3)
        if potential_peak_kw > threshold_kw or len(top_peaks) < 3:
            # How much do we need to discharge?
            target_grid_import = min(self.target_peak_kw, threshold_kw * self.aggressive_threshold)
            discharge_needed = max(0, potential_peak_kw - target_grid_import)

            # Can we discharge this much?
            available_discharge = context.soc_kwh - context.min_soc_kwh
            actual_discharge = min(discharge_needed, available_discharge, context.consumption_kw)

            if actual_discharge > 0.5:  # Worth it if > 0.5 kWh
                # Calculate value
                kw_reduction = min(actual_discharge, potential_peak_kw - self.target_peak_kw)
                is_in_top_n = potential_peak_kw > threshold_kw or len(top_peaks) < 3

                value = self.value_calculator.calculate_peak_shaving_value(
                    kw_reduction=kw_reduction,
                    is_in_top_n=is_in_top_n,
                    days_in_month=30
                )

                # Also add self-consumption value since we're covering consumption
                self_consumption_value = self.value_calculator.calculate_self_consumption_value(
                    spot_price=context.spot_price_sek_kwh,
                    kwh=actual_discharge,
                    battery_charge_cost=0.60,  # Typical night charging cost
                    include_vat=True
                )

                total_value = value + self_consumption_value

                priority = 1 if potential_peak_kw > threshold_kw * 1.1 else 2
                confidence = 0.95 if is_in_top_n else 0.80

                recommendation = AgentRecommendation(
                    agent_name=self.name,
                    action=AgentAction.DISCHARGE,
                    kwh=actual_discharge,
                    confidence=confidence,
                    value_sek=total_value,
                    priority=priority,
                    reasoning=(
                        f"Peak threat detected: {potential_peak_kw:.1f} kW consumption. "
                        f"Threshold: {threshold_kw:.1f} kW. "
                        f"Discharging {actual_discharge:.1f} kWh to reduce to {potential_peak_kw - actual_discharge:.1f} kW. "
                        f"Saves {value:.0f} SEK/day in peak costs + {self_consumption_value:.0f} SEK self-consumption."
                    ),
                    is_veto=False,
                    requires_immediate_action=(priority == 1),
                    metadata={
                        'peak_reduction_kw': kw_reduction,
                        'potential_peak_kw': potential_peak_kw,
                        'threshold_kw': threshold_kw,
                        'target_grid_import_kw': potential_peak_kw - actual_discharge,
                        'is_in_top_n': is_in_top_n,
                        'peak_value_sek': value,
                        'self_consumption_value_sek': self_consumption_value
                    }
                )

        # Case 2: PREVENTIVE - Consumption elevated but not critical yet
        elif potential_peak_kw > threshold_kw * self.aggressive_threshold:
            # Don't discharge yet, but signal high priority for this hour
            # Reserve battery capacity in case consumption increases further
            return None  # Don't act yet, just monitor

        # Case 3: SAFE - Consumption well below threshold
        else:
            return None  # No action needed

        if recommendation:
            self._record_recommendation(recommendation)

        return recommendation

    def explain_decision(self, context: BatteryContext, recommendation: AgentRecommendation) -> str:
        """
        Provide detailed explanation using GPT for natural language.

        This can be slower - used for UI display and debugging.
        """
        metadata = recommendation.metadata

        explanation = f"""
## Peak Shaving Decision

**Current Situation:**
- Time: {context.timestamp.strftime('%Y-%m-%d %H:%M')}
- Consumption: {context.consumption_kw:.1f} kW
- Grid Import (before battery): {metadata['potential_peak_kw']:.1f} kW
- Current Top 3 Peaks: {', '.join(f'{p:.1f} kW' for p in context.top_n_peaks[:3])}
- Peak Threshold: {metadata['threshold_kw']:.1f} kW

**Analysis:**
"""

        if metadata['is_in_top_n']:
            explanation += f"""
⚠️ **CRITICAL:** This consumption would enter the top 3 peaks for {context.current_month}.

**Impact on Effect Tariff:**
- Current top 3 average: {sum(context.top_n_peaks[:3])/len(context.top_n_peaks[:3]) if context.top_n_peaks else 0:.1f} kW
- If we do nothing: Peak increases by {metadata['peak_reduction_kw']:.1f} kW
- Monthly cost increase: {metadata['peak_reduction_kw'] * 60:.0f} SEK/month
- Daily cost: {metadata['peak_value_sek']:.0f} SEK/day
"""
        else:
            explanation += f"""
✓ Below top 3 threshold, but approaching limit.

**Preventive Action:**
- Consumption: {metadata['potential_peak_kw']:.1f} kW
- Threshold: {metadata['threshold_kw']:.1f} kW
- Margin: {metadata['threshold_kw'] - metadata['potential_peak_kw']:.1f} kW
"""

        explanation += f"""

**Recommended Action:**
- Discharge: {recommendation.kwh:.1f} kWh from battery
- Target grid import: {metadata['target_grid_import_kw']:.1f} kW
- Reduction: {metadata['peak_reduction_kw']:.1f} kW

**Economic Value:**
- Peak shaving value: {metadata['peak_value_sek']:.0f} SEK/day
- Self-consumption savings: {metadata['self_consumption_value_sek']:.0f} SEK
- **Total value: {recommendation.value_sek:.0f} SEK**

**Battery Impact:**
- Current SOC: {context.soc_kwh:.1f} kWh
- After discharge: {context.soc_kwh - recommendation.kwh:.1f} kWh
- Reserve maintained: {(context.soc_kwh - recommendation.kwh - context.min_soc_kwh):.1f} kWh above minimum

**Confidence:** {recommendation.confidence * 100:.0f}%
"""

        return explanation

    def should_reserve_capacity(self, context: BatteryContext, hours_ahead: int = 6) -> float:
        """
        Calculate how much battery capacity to reserve for peak shaving.

        This is used by other agents (arbitrage, solar) to know how much
        battery capacity they can use without interfering with peak shaving.

        Args:
            context: Current battery and market context
            hours_ahead: How many hours to look ahead

        Returns:
            kWh to reserve for peak shaving
        """
        # If not during E.ON hours, no need to reserve
        if not context.is_measurement_hour:
            return 0.0

        # Look at consumption patterns
        month_key = context.current_month
        threshold_kw = context.peak_threshold_kw

        # If we're close to threshold already, reserve capacity
        if context.consumption_kw > threshold_kw * 0.8:
            # Reserve enough to handle a 20% spike
            reserve_kwh = context.consumption_kw * 0.2
            return min(reserve_kwh, context.soc_kwh - context.min_soc_kwh)

        # If current consumption is high (> 6 kW), reserve some capacity
        if context.consumption_kw > 6.0:
            reserve_kwh = (context.consumption_kw - 5.0) * 1.5  # 1.5x buffer
            return min(reserve_kwh, context.soc_kwh - context.min_soc_kwh)

        # Otherwise, small reserve for unexpected spikes
        return 2.0  # 2 kWh buffer

    def __repr__(self):
        return (f"PeakShavingAgent(target={self.target_peak_kw}kW, "
                f"recommendations={self.recommendations_count}, "
                f"value={self.total_value_generated:.0f}SEK)")
