"""
Multi-agent battery optimization system.

This package contains specialist agents for different optimization domains:
- Peak Tracker: Real-time tracking of monthly top-3 peaks
- Value Calculator: Economic value calculations
- Base Agent: Abstract interface for all agents
- Peak Shaving Agent: Identifies peak hours and reserves battery capacity
- Arbitrage Agent: Finds profitable charge/discharge opportunities
- Real-time Override Agent: Emergency responses and load balancing
- Orchestrator: Coordinates all agents and makes final decisions
"""

from .peak_tracker import PeakTracker
from .value_calculator import ValueCalculator
from .base_agent import (
    BaseAgent,
    AgentAction,
    AgentRecommendation,
    BatteryContext,
    RealTimeOverrideAgent
)
from .peak_shaving_agent import PeakShavingAgent
from .arbitrage_agent import ArbitrageAgent
from .orchestrator import Orchestrator, OrchestratorDecision

__all__ = [
    # Core infrastructure
    'PeakTracker',
    'ValueCalculator',

    # Base classes and data structures
    'BaseAgent',
    'AgentAction',
    'AgentRecommendation',
    'BatteryContext',

    # Specialist agents
    'RealTimeOverrideAgent',
    'PeakShavingAgent',
    'ArbitrageAgent',

    # Orchestrator
    'Orchestrator',
    'OrchestratorDecision'
]
