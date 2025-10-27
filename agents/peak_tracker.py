"""
Peak Tracker - Real-time tracking of monthly peaks.

This class tracks consumption peaks during E.ON measurement hours (06:00-23:00)
and maintains the top N peaks per month for effect tariff calculations.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
import statistics


class PeakTracker:
    """
    Tracks monthly consumption peaks in real-time during simulation.

    For E.ON customers, effect tariff is calculated as the average of the
    top 3 peaks per month during measurement hours (06:00-23:00).
    """

    def __init__(self, measurement_start_hour: int = 6, measurement_end_hour: int = 23, top_n: int = 3):
        """
        Initialize peak tracker.

        Args:
            measurement_start_hour: Start of effect tariff measurement window (default: 6 for E.ON)
            measurement_end_hour: End of effect tariff measurement window (default: 23 for E.ON)
            top_n: Number of top peaks to track (default: 3 for E.ON)
        """
        self.measurement_start = measurement_start_hour
        self.measurement_end = measurement_end_hour
        self.top_n = top_n

        # Store all peaks by month: {month_key: [(timestamp, kw), ...]}
        self.monthly_peaks: Dict[str, List[Tuple[datetime, float]]] = {}

        # Cache for performance
        self._top_n_cache: Dict[str, List[float]] = {}
        self._threshold_cache: Dict[str, float] = {}

    def _get_month_key(self, timestamp: datetime) -> str:
        """Get month key from timestamp (YYYY-MM format)."""
        return timestamp.strftime('%Y-%m')

    def _is_measurement_hour(self, timestamp: datetime) -> bool:
        """Check if timestamp is within effect tariff measurement hours."""
        return self.measurement_start <= timestamp.hour <= self.measurement_end

    def update(self, timestamp: datetime, grid_import_kw: float) -> None:
        """
        Update tracker with new consumption data point.

        Args:
            timestamp: Timestamp of the measurement
            grid_import_kw: Grid import power in kW (after battery discharge)
        """
        # Only track during measurement hours
        if not self._is_measurement_hour(timestamp):
            return

        month_key = self._get_month_key(timestamp)

        # Initialize month if needed
        if month_key not in self.monthly_peaks:
            self.monthly_peaks[month_key] = []

        # Add peak
        self.monthly_peaks[month_key].append((timestamp, grid_import_kw))

        # Invalidate cache for this month
        if month_key in self._top_n_cache:
            del self._top_n_cache[month_key]
        if month_key in self._threshold_cache:
            del self._threshold_cache[month_key]

    def get_top_n_peaks(self, month_key: str) -> List[float]:
        """
        Get the top N peaks for a specific month.

        Args:
            month_key: Month in YYYY-MM format

        Returns:
            List of top N peak values in descending order
        """
        # Check cache first
        if month_key in self._top_n_cache:
            return self._top_n_cache[month_key]

        if month_key not in self.monthly_peaks or not self.monthly_peaks[month_key]:
            return []

        # Extract peak values and sort
        peaks = [kw for _, kw in self.monthly_peaks[month_key]]
        peaks_sorted = sorted(peaks, reverse=True)

        # Take top N
        top_peaks = peaks_sorted[:self.top_n]

        # Cache result
        self._top_n_cache[month_key] = top_peaks

        return top_peaks

    def get_top_n_average(self, month_key: str) -> float:
        """
        Get the average of top N peaks for a specific month.

        This is the value used by E.ON for effect tariff calculation.

        Args:
            month_key: Month in YYYY-MM format

        Returns:
            Average of top N peaks, or 0 if no peaks recorded
        """
        top_peaks = self.get_top_n_peaks(month_key)
        return statistics.mean(top_peaks) if top_peaks else 0.0

    def get_threshold(self, month_key: str) -> float:
        """
        Get the current threshold for entering top N peaks.

        If you have a consumption higher than this threshold,
        it will enter the top N and affect your effect tariff.

        Args:
            month_key: Month in YYYY-MM format

        Returns:
            Current Nth highest peak, or 0 if less than N peaks recorded
        """
        # Check cache first
        if month_key in self._threshold_cache:
            return self._threshold_cache[month_key]

        top_peaks = self.get_top_n_peaks(month_key)

        if len(top_peaks) < self.top_n:
            # Not enough peaks yet, threshold is 0 (any peak matters)
            threshold = 0.0
        else:
            # Threshold is the Nth peak (smallest in top N)
            threshold = top_peaks[-1]

        # Cache result
        self._threshold_cache[month_key] = threshold

        return threshold

    def would_improve_top_n(self, month_key: str, current_kw: float, reduced_kw: Optional[float] = None) -> Tuple[bool, float]:
        """
        Check if reducing a peak would improve the top N average.

        Args:
            month_key: Month in YYYY-MM format
            current_kw: Current consumption in kW
            reduced_kw: Reduced consumption after battery discharge (optional)

        Returns:
            Tuple of (would_improve, potential_savings_kw)
            - would_improve: True if reduction would help
            - potential_savings_kw: How much the average would improve
        """
        threshold = self.get_threshold(month_key)
        top_peaks = self.get_top_n_peaks(month_key)

        # If current consumption is below threshold, reduction won't help
        if current_kw <= threshold and len(top_peaks) >= self.top_n:
            return False, 0.0

        # Calculate current average
        current_avg = self.get_top_n_average(month_key)

        # If we reduce the peak, calculate new average
        if reduced_kw is not None:
            # Simulate reduction
            if len(top_peaks) >= self.top_n:
                # Replace the highest peak if current_kw is in top N
                if current_kw >= threshold:
                    # Find which peak to replace
                    simulated_peaks = [kw for _, kw in self.monthly_peaks[month_key] if kw != current_kw]
                    simulated_peaks.append(reduced_kw)
                    simulated_peaks_sorted = sorted(simulated_peaks, reverse=True)[:self.top_n]
                    new_avg = statistics.mean(simulated_peaks_sorted)
                else:
                    # Current peak not in top N, reduction won't help
                    new_avg = current_avg
            else:
                # Not enough peaks yet, any reduction helps
                simulated_peaks = [kw for _, kw in self.monthly_peaks[month_key] if kw != current_kw]
                simulated_peaks.append(reduced_kw)
                new_avg = statistics.mean(sorted(simulated_peaks, reverse=True)[:self.top_n])

            potential_savings = current_avg - new_avg
            return potential_savings > 0.01, potential_savings  # 0.01 kW minimum to be meaningful
        else:
            # Just check if current peak matters
            return current_kw > threshold, current_kw - threshold

    def get_all_peaks(self, month_key: str) -> List[Tuple[datetime, float]]:
        """
        Get all recorded peaks for a month.

        Args:
            month_key: Month in YYYY-MM format

        Returns:
            List of (timestamp, kw) tuples sorted by kW descending
        """
        if month_key not in self.monthly_peaks:
            return []

        peaks = self.monthly_peaks[month_key]
        return sorted(peaks, key=lambda x: x[1], reverse=True)

    def get_statistics(self, month_key: str) -> Dict:
        """
        Get comprehensive statistics for a month.

        Args:
            month_key: Month in YYYY-MM format

        Returns:
            Dictionary with peak statistics
        """
        if month_key not in self.monthly_peaks or not self.monthly_peaks[month_key]:
            return {
                'month': month_key,
                'total_measurements': 0,
                'top_n_peaks': [],
                'top_n_average': 0.0,
                'threshold': 0.0,
                'max_peak': 0.0,
                'min_peak': 0.0,
                'avg_all': 0.0
            }

        all_peaks = [kw for _, kw in self.monthly_peaks[month_key]]
        top_peaks = self.get_top_n_peaks(month_key)

        return {
            'month': month_key,
            'total_measurements': len(all_peaks),
            'top_n_peaks': top_peaks,
            'top_n_average': self.get_top_n_average(month_key),
            'threshold': self.get_threshold(month_key),
            'max_peak': max(all_peaks),
            'min_peak': min(all_peaks),
            'avg_all': statistics.mean(all_peaks)
        }

    def reset(self):
        """Clear all tracked data."""
        self.monthly_peaks.clear()
        self._top_n_cache.clear()
        self._threshold_cache.clear()

    def __repr__(self):
        months = len(self.monthly_peaks)
        total_peaks = sum(len(peaks) for peaks in self.monthly_peaks.values())
        return f"PeakTracker(months={months}, peaks={total_peaks}, top_n={self.top_n})"
