"""
Value Calculator - Calculate SEK value for different battery strategies.

This class provides methods to calculate the economic value of:
- Peak shaving (reducing effect tariff)
- Self-consumption (avoiding grid import costs)
- Arbitrage (export during high prices)
"""

from typing import Dict, Optional


class ValueCalculator:
    """
    Calculate SEK value for different battery optimization strategies.

    Uses Swedish electricity cost structure:
    - Import cost = spot + grid_fee + energy_tax (+ VAT)
    - Export revenue = spot - transfer_fee
    - Effect tariff = peak_kw × tariff_sek_per_kw_month
    """

    def __init__(
        self,
        grid_fee_sek_kwh: float = 0.42,
        energy_tax_sek_kwh: float = 0.40,
        transfer_fee_sek_kwh: float = 0.42,  # Same as grid fee for most operators
        vat_rate: float = 0.25,
        effect_tariff_sek_kw_month: float = 60.0,
        battery_efficiency: float = 0.95
    ):
        """
        Initialize value calculator with cost parameters.

        Args:
            grid_fee_sek_kwh: Grid transfer fee for import (SEK/kWh)
            energy_tax_sek_kwh: Energy tax (SEK/kWh)
            transfer_fee_sek_kwh: Transfer fee for export (SEK/kWh)
            vat_rate: VAT rate (0.25 = 25%)
            effect_tariff_sek_kw_month: Effect tariff (SEK/kW/month)
            battery_efficiency: Round-trip efficiency (0.95 = 95%)
        """
        self.grid_fee = grid_fee_sek_kwh
        self.energy_tax = energy_tax_sek_kwh
        self.transfer_fee = transfer_fee_sek_kwh
        self.vat_rate = vat_rate
        self.effect_tariff = effect_tariff_sek_kw_month
        self.efficiency = battery_efficiency

    def calculate_import_cost(self, spot_price: float, kwh: float = 1.0, include_vat: bool = True) -> float:
        """
        Calculate total cost to import electricity from grid.

        Args:
            spot_price: Spot market price (SEK/kWh)
            kwh: Amount of electricity (kWh)
            include_vat: Whether to include VAT in calculation

        Returns:
            Total cost in SEK
        """
        subtotal = (spot_price + self.grid_fee + self.energy_tax) * kwh

        if include_vat:
            return subtotal * (1 + self.vat_rate)
        return subtotal

    def calculate_export_revenue(self, spot_price: float, kwh: float = 1.0) -> float:
        """
        Calculate net revenue from exporting electricity to grid.

        Args:
            spot_price: Spot market price (SEK/kWh)
            kwh: Amount of electricity (kWh)

        Returns:
            Net revenue in SEK (can be 0 if spot price < transfer fee)
        """
        net_price_per_kwh = max(0, spot_price - self.transfer_fee)
        return net_price_per_kwh * kwh

    def calculate_peak_shaving_value(
        self,
        kw_reduction: float,
        is_in_top_n: bool = True,
        days_in_month: int = 30
    ) -> float:
        """
        Calculate daily value of peak shaving.

        Args:
            kw_reduction: How many kW reduced from peak
            is_in_top_n: Whether this peak affects the top N average
            days_in_month: Days in month (for daily value calculation)

        Returns:
            Value in SEK per day
        """
        if not is_in_top_n or kw_reduction <= 0:
            return 0.0

        # Monthly savings
        monthly_savings = kw_reduction * self.effect_tariff

        # Daily value
        daily_value = monthly_savings / days_in_month

        return daily_value

    def calculate_self_consumption_value(
        self,
        spot_price: float,
        kwh: float,
        battery_charge_cost: float,
        include_vat: bool = True
    ) -> float:
        """
        Calculate value of using battery instead of grid import.

        Args:
            spot_price: Current spot market price (SEK/kWh)
            kwh: Amount of self-consumption (kWh)
            battery_charge_cost: Cost to charge battery (SEK/kWh), typically night price
            include_vat: Whether to include VAT in calculation

        Returns:
            Net value/savings in SEK
        """
        # Cost to import from grid
        import_cost = self.calculate_import_cost(spot_price, kwh, include_vat)

        # Cost to use battery (charged at night)
        battery_cost = battery_charge_cost * kwh / self.efficiency  # Account for efficiency loss

        # Net savings
        return import_cost - battery_cost

    def calculate_arbitrage_value(
        self,
        discharge_price: float,
        charge_price: float,
        kwh: float
    ) -> float:
        """
        Calculate profit from arbitrage (charge low, export high).

        Args:
            discharge_price: Spot price when discharging (SEK/kWh)
            charge_price: Spot price when charging (SEK/kWh)
            kwh: Amount of energy (kWh)

        Returns:
            Net profit in SEK (can be negative if unprofitable)
        """
        # Revenue from exporting
        export_revenue = self.calculate_export_revenue(discharge_price, kwh)

        # Cost to charge (including import costs)
        charge_cost = self.calculate_import_cost(charge_price, kwh, include_vat=True)

        # Account for efficiency loss
        effective_kwh = kwh * self.efficiency

        # Net profit
        profit = (export_revenue * effective_kwh) - charge_cost

        return profit

    def calculate_combined_value(
        self,
        spot_price: float,
        consumption_kwh: float,
        discharge_kwh: float,
        battery_charge_cost: float,
        peak_kw_reduction: float = 0.0,
        is_in_top_n: bool = False
    ) -> Dict[str, float]:
        """
        Calculate combined value when multiple strategies apply simultaneously.

        Example: Discharging during a peak hour with high prices gives both
        peak shaving value AND self-consumption value.

        Args:
            spot_price: Current spot price (SEK/kWh)
            consumption_kwh: Current consumption (kWh)
            discharge_kwh: Amount discharged from battery (kWh)
            battery_charge_cost: Cost to charge battery (SEK/kWh)
            peak_kw_reduction: kW reduction from peak (if applicable)
            is_in_top_n: Whether this hour affects top N peaks

        Returns:
            Dictionary with breakdown of values
        """
        # Peak shaving value (per day)
        peak_value = self.calculate_peak_shaving_value(peak_kw_reduction, is_in_top_n)

        # Self-consumption value (covering own usage)
        self_consumption_kwh = min(discharge_kwh, consumption_kwh)
        self_consumption_value = self.calculate_self_consumption_value(
            spot_price, self_consumption_kwh, battery_charge_cost
        )

        # Arbitrage value (if discharging more than consumption)
        arbitrage_kwh = max(0, discharge_kwh - consumption_kwh)
        arbitrage_value = 0.0
        if arbitrage_kwh > 0:
            arbitrage_value = self.calculate_arbitrage_value(
                spot_price, battery_charge_cost, arbitrage_kwh
            )

        total_value = peak_value + self_consumption_value + arbitrage_value

        return {
            'peak_shaving_sek': peak_value,
            'self_consumption_sek': self_consumption_value,
            'arbitrage_sek': arbitrage_value,
            'total_sek': total_value,
            'breakdown': {
                'peak_kw_reduction': peak_kw_reduction,
                'self_consumption_kwh': self_consumption_kwh,
                'arbitrage_kwh': arbitrage_kwh
            }
        }

    def compare_strategies(
        self,
        spot_price: float,
        consumption_kwh: float,
        battery_charge_cost: float,
        peak_kw_without_battery: float,
        is_in_top_n: bool,
        battery_available_kwh: float
    ) -> Dict[str, Dict]:
        """
        Compare different discharge strategies and recommend best option.

        Args:
            spot_price: Current spot price (SEK/kWh)
            consumption_kwh: Current consumption (kWh)
            battery_charge_cost: Cost to charge battery (SEK/kWh)
            peak_kw_without_battery: Peak if no battery used (kW)
            is_in_top_n: Whether this hour affects top N peaks
            battery_available_kwh: Available battery capacity (kWh)

        Returns:
            Dictionary comparing different strategies with recommendations
        """
        TARGET_PEAK_KW = 5.0  # Target peak import level

        strategies = {}

        # Strategy 1: Do nothing
        strategies['do_nothing'] = {
            'discharge_kwh': 0,
            'grid_import_kw': peak_kw_without_battery,
            'value': self.calculate_combined_value(
                spot_price, consumption_kwh, 0, battery_charge_cost, 0, False
            )
        }

        # Strategy 2: Peak shaving only (reduce to 5 kW target)
        if peak_kw_without_battery > TARGET_PEAK_KW:
            peak_discharge = min(
                peak_kw_without_battery - TARGET_PEAK_KW,
                battery_available_kwh,
                consumption_kwh
            )
            peak_reduction = min(peak_discharge, peak_kw_without_battery - TARGET_PEAK_KW)

            strategies['peak_shaving_only'] = {
                'discharge_kwh': peak_discharge,
                'grid_import_kw': peak_kw_without_battery - peak_discharge,
                'value': self.calculate_combined_value(
                    spot_price, consumption_kwh, peak_discharge,
                    battery_charge_cost, peak_reduction, is_in_top_n
                )
            }

        # Strategy 3: Full self-consumption (cover all consumption)
        full_discharge = min(consumption_kwh, battery_available_kwh)
        strategies['full_self_consumption'] = {
            'discharge_kwh': full_discharge,
            'grid_import_kw': max(0, peak_kw_without_battery - full_discharge),
            'value': self.calculate_combined_value(
                spot_price, consumption_kwh, full_discharge,
                battery_charge_cost,
                min(peak_kw_without_battery, full_discharge), is_in_top_n
            )
        }

        # Find best strategy
        best_strategy = max(strategies.items(), key=lambda x: x[1]['value']['total_sek'])

        return {
            'strategies': strategies,
            'recommended': best_strategy[0],
            'recommended_details': best_strategy[1]
        }

    def __repr__(self):
        return (f"ValueCalculator(grid_fee={self.grid_fee}, energy_tax={self.energy_tax}, "
                f"effect_tariff={self.effect_tariff}, efficiency={self.efficiency})")
