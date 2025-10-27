"""
Statistical analysis of consumption patterns for peak shaving reserve calculations.

Analyzes historical consumption data to understand:
- Percentile distributions (50th, 75th, 90th, 95th, 99th)
- Time-of-day patterns
- Day type differences (weekday vs weekend)
- Risk levels for different hours
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from enum import Enum


class DayType(Enum):
    """Type of day for pattern analysis."""
    WEEKDAY = "weekday"
    WEEKEND = "weekend"


class TimeOfDay(Enum):
    """Time of day buckets for pattern analysis."""
    NIGHT = "night"          # 00:00 - 05:59
    MORNING = "morning"      # 06:00 - 11:59
    AFTERNOON = "afternoon"  # 12:00 - 17:59
    EVENING = "evening"      # 18:00 - 23:59


@dataclass
class ConsumptionStats:
    """Statistical summary of consumption for a specific time period."""
    hour: int
    day_type: DayType
    time_of_day: TimeOfDay
    sample_count: int

    # Basic statistics
    mean_kw: float
    median_kw: float
    std_kw: float
    min_kw: float
    max_kw: float

    # Percentiles for risk assessment
    p50_kw: float  # 50th percentile (median)
    p75_kw: float  # 75th percentile
    p90_kw: float  # 90th percentile (conservative)
    p95_kw: float  # 95th percentile (very conservative)
    p99_kw: float  # 99th percentile (extreme events)

    def get_percentile(self, percentile: int) -> float:
        """Get consumption at given percentile."""
        percentile_map = {
            50: self.p50_kw,
            75: self.p75_kw,
            90: self.p90_kw,
            95: self.p95_kw,
            99: self.p99_kw
        }
        return percentile_map.get(percentile, self.p95_kw)


@dataclass
class ReserveRequirement:
    """Battery reserve requirement for peak shaving."""
    timestamp: pd.Timestamp
    hour: int
    day_type: DayType

    # Reserve calculation
    expected_peak_kw: float       # Expected consumption at chosen percentile
    grid_import_limit_kw: float   # Target to keep grid import below
    raw_reserve_kwh: float        # Theoretical reserve needed
    safety_buffer: float          # Multiplier for safety (1.1-1.2)
    required_reserve_kwh: float   # Final reserve with safety buffer

    # Confidence and risk
    percentile_used: int          # Which percentile (90, 95, 99)
    confidence: float             # 0.0-1.0, how confident we are
    risk_level: str               # "low", "medium", "high"

    # Metadata
    reasoning: str
    consumption_stats: ConsumptionStats


@dataclass
class CapacityAllocation:
    """How battery capacity is allocated between different purposes."""
    total_capacity_kwh: float
    current_soc_kwh: float

    # Allocations
    peak_shaving_reserve_kwh: float    # Reserved for peak shaving
    available_for_arbitrage_kwh: float # Can be used for arbitrage/self-consumption
    minimum_soc_kwh: float             # Technical minimum

    # Constraints
    can_charge: bool                    # Can we charge right now?
    can_discharge: bool                 # Can we discharge right now?
    max_charge_this_hour_kwh: float    # Max we can charge this hour
    max_discharge_this_hour_kwh: float # Max we can discharge this hour

    # Value tracking
    opportunity_cost_sek: float        # Arbitrage profit lost due to reserves

    def get_available_for_agent(self, agent_type: str) -> float:
        """Get available capacity for specific agent."""
        if agent_type == "peak_shaving":
            return self.peak_shaving_reserve_kwh
        elif agent_type in ["arbitrage", "self_consumption"]:
            return self.available_for_arbitrage_kwh
        else:
            return 0.0


class ConsumptionAnalyzer:
    """
    Analyzes historical consumption data to understand patterns and risks.

    This helps us answer: "For hour X on day type Y, what's the 95th percentile peak?"
    """

    def __init__(self, historical_data: pd.DataFrame, consumption_col: str = 'consumption_kwh'):
        """
        Initialize analyzer with historical data.

        Args:
            historical_data: DataFrame with 'timestamp' and consumption columns
            consumption_col: Name of consumption column (in kW or kWh)
        """
        self.df = historical_data.copy()
        self.consumption_col = consumption_col

        # Add derived columns
        self.df['hour'] = self.df['timestamp'].dt.hour
        self.df['day_of_week'] = self.df['timestamp'].dt.dayofweek
        self.df['is_weekend'] = self.df['day_of_week'].isin([5, 6])
        self.df['day_type'] = self.df['is_weekend'].apply(
            lambda x: DayType.WEEKEND if x else DayType.WEEKDAY
        )
        self.df['time_of_day'] = self.df['hour'].apply(self._get_time_of_day)

        # Pre-calculate statistics for all hour/day_type combinations
        self.stats_cache: Dict[Tuple[int, DayType], ConsumptionStats] = {}
        self._build_stats_cache()

    def _get_time_of_day(self, hour: int) -> TimeOfDay:
        """Map hour to time of day bucket."""
        if 0 <= hour < 6:
            return TimeOfDay.NIGHT
        elif 6 <= hour < 12:
            return TimeOfDay.MORNING
        elif 12 <= hour < 18:
            return TimeOfDay.AFTERNOON
        else:
            return TimeOfDay.EVENING

    def _build_stats_cache(self):
        """Pre-calculate statistics for all hour/day_type combinations."""
        for hour in range(24):
            for day_type in DayType:
                stats = self._calculate_stats(hour, day_type)
                if stats:
                    self.stats_cache[(hour, day_type)] = stats

    def _calculate_stats(self, hour: int, day_type: DayType) -> Optional[ConsumptionStats]:
        """Calculate statistics for specific hour and day type."""
        # Filter data
        mask = (self.df['hour'] == hour) & (self.df['day_type'] == day_type)
        data = self.df[mask][self.consumption_col]

        if len(data) < 3:  # Need at least 3 samples
            return None

        # Calculate percentiles
        percentiles = np.percentile(data, [50, 75, 90, 95, 99])

        return ConsumptionStats(
            hour=hour,
            day_type=day_type,
            time_of_day=self._get_time_of_day(hour),
            sample_count=len(data),
            mean_kw=float(data.mean()),
            median_kw=float(data.median()),
            std_kw=float(data.std()),
            min_kw=float(data.min()),
            max_kw=float(data.max()),
            p50_kw=float(percentiles[0]),
            p75_kw=float(percentiles[1]),
            p90_kw=float(percentiles[2]),
            p95_kw=float(percentiles[3]),
            p99_kw=float(percentiles[4])
        )

    def get_stats(self, hour: int, day_type: DayType) -> Optional[ConsumptionStats]:
        """Get cached statistics for hour and day type."""
        return self.stats_cache.get((hour, day_type))

    def get_stats_for_timestamp(self, timestamp: pd.Timestamp) -> Optional[ConsumptionStats]:
        """Get statistics for specific timestamp."""
        hour = timestamp.hour
        is_weekend = timestamp.dayofweek in [5, 6]
        day_type = DayType.WEEKEND if is_weekend else DayType.WEEKDAY
        return self.get_stats(hour, day_type)

    def get_risk_level(self, hour: int, day_type: DayType) -> str:
        """
        Assess risk level for specific hour/day_type.

        Risk is based on:
        - High variability (high std/mean ratio)
        - High max values
        - Evening hours (17-21) are typically high-risk
        """
        stats = self.get_stats(hour, day_type)
        if not stats:
            return "unknown"

        # Calculate coefficient of variation (std/mean)
        cv = stats.std_kw / stats.mean_kw if stats.mean_kw > 0 else 0

        # High risk factors
        high_cv = cv > 1.0  # High variability
        high_p95 = stats.p95_kw > 5.0  # 95th percentile > 5 kW
        evening_hours = 17 <= hour <= 21  # Peak evening hours

        if (high_cv and high_p95) or (evening_hours and high_p95):
            return "high"
        elif high_cv or high_p95 or evening_hours:
            return "medium"
        else:
            return "low"

    def get_recommended_percentile(self, hour: int, day_type: DayType,
                                   default_percentile: int = 95) -> int:
        """
        Get recommended percentile based on risk level.

        High risk hours use higher percentile (99th) for more safety.
        Low risk hours can use lower percentile (90th).
        """
        risk = self.get_risk_level(hour, day_type)

        if risk == "high":
            return 99  # Very conservative for high-risk hours
        elif risk == "medium":
            return 95  # Conservative
        else:
            return 90  # Moderately conservative

    def print_summary(self):
        """Print summary of consumption patterns."""
        print("\n" + "=" * 80)
        print("CONSUMPTION PATTERN ANALYSIS")
        print("=" * 80)

        for day_type in DayType:
            print(f"\n{day_type.value.upper()} PATTERNS:")
            print("-" * 80)
            print(f"{'Hour':<6} {'Mean':<8} {'P50':<8} {'P90':<8} {'P95':<8} {'P99':<8} {'Max':<8} {'Risk':<8} {'Samples':<8}")
            print("-" * 80)

            for hour in range(24):
                stats = self.get_stats(hour, day_type)
                if stats:
                    risk = self.get_risk_level(hour, day_type)
                    print(f"{hour:02d}:00  {stats.mean_kw:6.2f}   {stats.p50_kw:6.2f}   "
                          f"{stats.p90_kw:6.2f}   {stats.p95_kw:6.2f}   {stats.p99_kw:6.2f}   "
                          f"{stats.max_kw:6.2f}   {risk:<8} {stats.sample_count:<8}")
