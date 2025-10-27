"""
Base Agent - Abstract interface for all specialist battery optimization agents.

This defines the contract that all specialist agents must implement:
- Peak Shaving Agent
- Arbitrage Agent
- Solar Agent
- Real-time Override Agent
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class AgentAction(Enum):
    """Types of actions an agent can recommend."""
    CHARGE = "charge"
    DISCHARGE = "discharge"
    HOLD = "hold"
    EXPORT = "export"


@dataclass
class AgentRecommendation:
    """
    Structured recommendation from a specialist agent.

    Each agent proposes actions with economic justification,
    allowing the orchestrator to make informed decisions.
    """
    agent_name: str
    action: AgentAction
    kwh: float  # Amount to charge/discharge
    confidence: float  # 0.0 to 1.0, how confident is this recommendation
    value_sek: float  # Expected economic value in SEK
    priority: int  # 1=critical, 2=high, 3=medium, 4=low
    reasoning: str  # Human-readable explanation

    # Optional constraint flags
    is_veto: bool = False  # If True, ignoring this could be catastrophic
    requires_immediate_action: bool = False  # Real-time override flag

    # Supporting data for orchestrator decision-making
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

        # Validate inputs
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")
        if self.priority not in [1, 2, 3, 4]:
            raise ValueError(f"Priority must be 1-4, got {self.priority}")


@dataclass
class BatteryContext:
    """
    Current state of the battery system and market conditions.

    This is passed to all agents so they have complete context
    for decision-making.
    """
    # Timestamp
    timestamp: datetime
    hour: int

    # Battery state
    soc_kwh: float  # Current state of charge
    capacity_kwh: float  # Total capacity
    max_charge_kw: float  # Max charge power
    max_discharge_kw: float  # Max discharge power
    efficiency: float  # Round-trip efficiency

    # Current conditions
    consumption_kw: float  # Current consumption
    solar_production_kw: float  # Current solar (0 if none)
    grid_import_kw: float  # Current grid import

    # Market prices
    spot_price_sek_kwh: float  # Current spot price
    import_cost_sek_kwh: float  # Full import cost (spot + fees + tax + VAT)
    export_revenue_sek_kwh: float  # Net export revenue (spot - transfer fee)

    # Forecasts (next 24 hours)
    spot_forecast: List[float]  # Spot price forecast
    consumption_forecast: List[float]  # Consumption forecast from historical patterns

    # Peak tracking
    current_month: str  # YYYY-MM format
    top_n_peaks: List[float]  # Current top N peaks this month
    peak_threshold_kw: float  # Threshold to enter top N
    is_measurement_hour: bool  # Is this during E.ON measurement hours?

    # Consumption patterns (for learning)
    avg_consumption_kw: float  # Average consumption this month
    peak_consumption_kw: float  # Peak consumption this month

    # Constraints
    min_soc_kwh: float  # Minimum SOC to maintain (backup reserve)
    target_morning_soc_kwh: float  # Target SOC at 06:00


class BaseAgent(ABC):
    """
    Abstract base class for all battery optimization agents.

    Each specialist agent focuses on one optimization domain:
    - Peak Shaving: Reduce effect tariff by managing top-3 peaks
    - Arbitrage: Profit from price spreads (charge low, export high)
    - Solar: Maximize solar self-consumption
    - Real-time Override: Emergency response to unexpected spikes
    """

    def __init__(self, name: str, enabled: bool = True):
        """
        Initialize base agent.

        Args:
            name: Agent identifier (e.g., "PeakShavingAgent")
            enabled: Whether this agent is active
        """
        self.name = name
        self.enabled = enabled
        self.recommendations_count = 0
        self.total_value_generated = 0.0

    @abstractmethod
    def analyze(self, context: BatteryContext) -> Optional[AgentRecommendation]:
        """
        Analyze current context and return recommendation.

        This is the main method each agent must implement.
        Should be FAST (< 100ms) for real-time operation.

        Args:
            context: Complete battery and market state

        Returns:
            AgentRecommendation if agent has a suggestion, None otherwise
        """
        pass

    @abstractmethod
    def explain_decision(self, context: BatteryContext, recommendation: AgentRecommendation) -> str:
        """
        Provide detailed explanation of recommendation.

        This can be slower (can call GPT for natural language explanation).
        Used for debugging, learning, and UI display.

        Args:
            context: Context used for decision
            recommendation: The recommendation made

        Returns:
            Human-readable explanation (markdown supported)
        """
        pass

    def get_performance_metrics(self) -> Dict[str, float]:
        """
        Get agent performance statistics.

        Returns:
            Dictionary with metrics like recommendations count, total value, etc.
        """
        return {
            'recommendations_count': self.recommendations_count,
            'total_value_sek': self.total_value_generated,
            'avg_value_per_recommendation': (
                self.total_value_generated / self.recommendations_count
                if self.recommendations_count > 0 else 0.0
            ),
            'enabled': self.enabled
        }

    def reset_metrics(self):
        """Reset performance tracking metrics."""
        self.recommendations_count = 0
        self.total_value_generated = 0.0

    def _record_recommendation(self, recommendation: AgentRecommendation):
        """Track recommendation for performance metrics."""
        self.recommendations_count += 1
        self.total_value_generated += recommendation.value_sek

    def __repr__(self):
        status = "enabled" if self.enabled else "disabled"
        return f"{self.name}({status}, recommendations={self.recommendations_count})"


class RealTimeOverrideAgent(BaseAgent):
    """
    Special agent for emergency real-time overrides.

    This agent can VETO other recommendations if it detects:
    - Unexpected consumption spikes
    - Risk of exceeding peak threshold
    - Battery backup reserve threatened

    This is the "Loadbalancer AI" the user mentioned - can trigger
    actions like stopping devices during spikes.
    """

    def __init__(self, spike_threshold_kw: float = 10.0,
                 critical_peak_margin_kw: float = 1.0):
        """
        Initialize real-time override agent.

        Args:
            spike_threshold_kw: Consumption level that triggers override
            critical_peak_margin_kw: How close to peak threshold before override
        """
        super().__init__("RealTimeOverride", enabled=True)
        self.spike_threshold = spike_threshold_kw
        self.critical_margin = critical_peak_margin_kw

    def analyze(self, context: BatteryContext) -> Optional[AgentRecommendation]:
        """
        Check for emergency conditions requiring immediate action.

        Returns veto-level recommendations for critical situations.
        """
        # Check for unexpected spike during E.ON hours
        if context.is_measurement_hour and context.consumption_kw > self.spike_threshold:
            # How close are we to peak threshold?
            if context.consumption_kw > context.peak_threshold_kw - self.critical_margin:
                # CRITICAL: About to set new peak!
                discharge_needed = context.consumption_kw - (context.peak_threshold_kw - self.critical_margin)
                discharge_needed = min(discharge_needed, context.soc_kwh - context.min_soc_kwh)

                if discharge_needed > 0:
                    rec = AgentRecommendation(
                        agent_name=self.name,
                        action=AgentAction.DISCHARGE,
                        kwh=discharge_needed,
                        confidence=1.0,  # Maximum confidence - this is critical
                        value_sek=discharge_needed * 60.0 / 30.0,  # Peak shaving value
                        priority=1,  # Critical priority
                        reasoning=f"EMERGENCY: Consumption spike detected ({context.consumption_kw:.1f} kW). "
                                 f"Discharging {discharge_needed:.1f} kWh to prevent new peak threshold.",
                        is_veto=True,  # This overrides other agents
                        requires_immediate_action=True,
                        metadata={
                            'spike_detected': True,
                            'consumption_kw': context.consumption_kw,
                            'threshold_kw': context.peak_threshold_kw,
                            'action_type': 'emergency_peak_prevention'
                        }
                    )

                    self._record_recommendation(rec)
                    return rec

        # Check for battery backup reserve threatened
        # CRITICAL: NEVER charge during E.ON measurement hours (06-23) even in emergency!
        # Charging during E.ON hours creates NEW peaks that get measured.
        # Better to wait until off-peak hours (00-05) to recharge.
        if context.soc_kwh < context.min_soc_kwh + 2.0:  # Within 2 kWh of minimum
            # Only charge if NOT during E.ON measurement hours
            if not context.is_measurement_hour:
                rec = AgentRecommendation(
                    agent_name=self.name,
                    action=AgentAction.CHARGE,
                    kwh=context.min_soc_kwh + 5.0 - context.soc_kwh,  # Restore to min + 5 kWh buffer
                    confidence=1.0,
                    value_sek=0.0,  # Not about value, about safety
                    priority=1,
                    reasoning=f"CRITICAL: Battery SOC ({context.soc_kwh:.1f} kWh) near minimum reserve. "
                             f"Charging to restore safety buffer (off-peak hours).",
                    is_veto=True,
                    requires_immediate_action=True,
                    metadata={
                        'battery_critical': True,
                        'current_soc': context.soc_kwh,
                        'min_soc': context.min_soc_kwh,
                        'action_type': 'battery_safety'
                    }
                )

                self._record_recommendation(rec)
                return rec
            # else: During E.ON hours - don't charge even if battery is low
            # Let it stay low temporarily to avoid creating new peaks

        return None  # No emergency conditions

    def explain_decision(self, context: BatteryContext, recommendation: AgentRecommendation) -> str:
        """Provide explanation for override action."""
        if recommendation.metadata.get('spike_detected'):
            return f"""
## Real-Time Override: Emergency Peak Prevention

**Situation:** Detected unexpected consumption spike during E.ON measurement hours.

**Current State:**
- Consumption: {context.consumption_kw:.1f} kW
- Peak Threshold: {context.peak_threshold_kw:.1f} kW
- Risk: About to set new monthly peak!

**Action:** Immediately discharge {recommendation.kwh:.1f} kWh to reduce grid import.

**Value:** Prevents {recommendation.value_sek:.0f} SEK/day in effect tariff increases.

**Note:** This is a veto-level override. Other agent plans are suspended for this critical action.
"""
        elif recommendation.metadata.get('battery_critical'):
            return f"""
## Real-Time Override: Battery Safety Reserve

**Situation:** Battery SOC critically low ({context.soc_kwh:.1f} kWh), approaching minimum reserve.

**Action:** Immediately charge {recommendation.kwh:.1f} kWh to restore safety buffer.

**Reason:** Maintaining backup reserve is more important than optimization strategies.
"""
        else:
            return "Real-time override triggered."
