"""
Arbitrage Agent - Specialist agent for price-based trading.

This agent focuses on profiting from electricity price spreads:
- Charge during low prices (typically night)
- Discharge/export during high prices
- Consider self-consumption vs export economics

Key insight: Self-consumption almost always beats export due to:
- Import cost: ~2.50 SEK/kWh (spot + fees + tax + VAT)
- Export revenue: ~0.80 SEK/kWh (spot - transfer fee)
- Self-consumption saves 2.50, export earns 0.80

Only export when:
1. No consumption to cover (excess capacity)
2. Spot price > 3.00 SEK/kWh (makes export competitive)
3. Battery not needed for peak shaving
"""

from typing import Optional, List
from .base_agent import BaseAgent, AgentRecommendation, AgentAction, BatteryContext
from .value_calculator import ValueCalculator


class ArbitrageAgent(BaseAgent):
    """
    Specialist agent for arbitrage optimization.

    Handles both:
    - Self-consumption (use battery instead of grid import)
    - Export arbitrage (sell to grid during high prices)
    """

    def __init__(
        self,
        value_calculator: ValueCalculator,
        min_arbitrage_profit_sek: float = 5.0,
        min_export_spot_price: float = 3.0,
        night_charge_threshold: float = 0.70
    ):
        """
        Initialize arbitrage agent.

        Args:
            value_calculator: Shared ValueCalculator for economic analysis
            min_arbitrage_profit_sek: Minimum profit to justify arbitrage (SEK)
            min_export_spot_price: Minimum spot price to consider export (SEK/kWh)
            night_charge_threshold: Charge if night price below this (SEK/kWh)
        """
        super().__init__("ArbitrageAgent", enabled=True)
        self.value_calculator = value_calculator
        self.min_profit = min_arbitrage_profit_sek
        self.min_export_price = min_export_spot_price
        self.night_charge_threshold = night_charge_threshold

    def analyze(self, context: BatteryContext) -> Optional[AgentRecommendation]:
        """
        Analyze arbitrage opportunities.

        Decision flow:
        1. Night hours (00:00-05:59): Consider charging if price low
        2. Day hours with consumption: Prioritize self-consumption
        3. Day hours with high prices + excess capacity: Consider export
        """
        current_price = context.spot_price_sek_kwh
        hour = context.hour

        # Strategy 1: Night charging (00:00-05:59)
        if 0 <= hour <= 5:
            return self._analyze_charging(context)

        # Strategy 2: Self-consumption during consumption hours
        if context.consumption_kw > 0:
            return self._analyze_self_consumption(context)

        # Strategy 3: Export arbitrage (if no consumption)
        if current_price >= self.min_export_price:
            return self._analyze_export(context)

        return None

    def _analyze_charging(self, context: BatteryContext) -> Optional[AgentRecommendation]:
        """
        Analyze night charging opportunity.

        Charge if:
        - Spot price < threshold (cheap electricity)
        - Battery has room
        - Not already at target SOC
        - NOT during peak hours (06:00-23:00) - would create expensive peaks!
        """
        current_price = context.spot_price_sek_kwh

        # CRITICAL: Never charge during E.ON measurement hours (06:00-23:00)
        # Charging creates grid import peaks that cost 60 SEK/kW/month!
        # Even if price is cheap, the peak cost far exceeds any savings
        if context.is_measurement_hour:
            return None  # Don't charge during peak tariff hours

        # Should we charge?
        if current_price >= self.night_charge_threshold:
            return None  # Too expensive

        # CRITICAL: Reserve 10 kWh for peak shaving during daytime
        # This ensures battery always has capacity available for continuous discharge
        # Even if we don't know when spikes will occur, we maintain readiness
        PEAK_RESERVE_KWH = 10.0  # Reserve 10 kWh for daytime peak shaving

        # Don't charge beyond (capacity - reserve)
        # Example: 25 kWh capacity - 10 kWh reserve = max 15 kWh charge target
        safe_max_soc = context.capacity_kwh - PEAK_RESERVE_KWH

        # CRITICAL: Check consumption forecast to reserve capacity for peak shaving
        # Don't fill battery if high consumption expected during measurement hours
        target_soc = min(context.target_morning_soc_kwh, safe_max_soc)

        if context.consumption_forecast:
            # Look at upcoming measurement hours (next 6-18 hours covers morning/day)
            # This ensures we check morning wake-up spikes and daytime consumption
            hours_to_check = min(18, len(context.consumption_forecast))
            upcoming_consumption = context.consumption_forecast[:hours_to_check]

            # Find maximum expected consumption in measurement hours
            max_upcoming_consumption = 0
            for i, consumption_kw in enumerate(upcoming_consumption):
                future_hour = (context.hour + i) % 24
                # Only consider E.ON measurement hours (06:00-23:00)
                if 6 <= future_hour <= 23:
                    max_upcoming_consumption = max(max_upcoming_consumption, consumption_kw)

            # Debug: Show what we're seeing
            print(f"   🔍 Arbitrage at hour {context.hour}: Max upcoming consumption = {max_upcoming_consumption:.1f} kW")

            # If high consumption expected (> 7 kW), ENSURE battery has capacity for peak shaving!
            if max_upcoming_consumption > 7.0:
                # Calculate how much battery discharge we need to reduce peak to 5 kW
                # Limited by inverter max (12 kW) and assumed 30-min spike duration
                peak_reduction_kw = min(max_upcoming_consumption - 5.0, 12.0)
                reserve_kwh = peak_reduction_kw * 0.5  # 30-min spike = 0.5 hour
                reserve_kwh = min(reserve_kwh, 12.0)  # Cap at reasonable level

                # CRITICAL FIX: INCREASE target SOC to ensure battery HAS the reserve!
                # We need: min_soc + reserve + buffer for safety
                target_soc = max(
                    context.min_soc_kwh + reserve_kwh + 3.0,  # min + reserve + 3 kWh buffer
                    context.target_morning_soc_kwh,  # At least default target
                    15.0  # Minimum 15 kWh for peak shaving effectiveness
                )

                # Log this decision
                print(f"   📊 Arbitrage: High peak expected ({max_upcoming_consumption:.1f} kW)")
                print(f"      Need {reserve_kwh:.1f} kWh reserve → Target SOC: {target_soc:.1f} kWh")
                print(f"      Current SOC: {context.soc_kwh:.1f} kWh → Will charge {max(0, target_soc - context.soc_kwh):.1f} kWh")

        room_to_charge = target_soc - context.soc_kwh

        if room_to_charge < 1.0:  # Less than 1 kWh room
            return None  # Already full enough

        # How much can we charge this hour?
        charge_kwh = min(
            room_to_charge,
            context.max_charge_kw,  # Hardware limit
            context.capacity_kwh - context.soc_kwh  # Physical capacity
        )

        if charge_kwh < 0.5:  # Less than 0.5 kWh
            return None  # Not worth it

        # Calculate value: charge cheap now, use later for self-consumption
        import_cost_now = self.value_calculator.calculate_import_cost(
            spot_price=current_price,
            kwh=charge_kwh,
            include_vat=True
        )

        # Estimate future savings (assume average day price ~1.50 SEK/kWh)
        future_avg_price = 1.50
        if context.spot_forecast:
            # Use actual forecast if available (06:00-23:00 hours)
            day_hours = [p for i, p in enumerate(context.spot_forecast) if 6 <= (context.hour + i) % 24 <= 23]
            if day_hours:
                future_avg_price = sum(day_hours) / len(day_hours)

        future_savings = self.value_calculator.calculate_self_consumption_value(
            spot_price=future_avg_price,
            kwh=charge_kwh * context.efficiency,  # Account for efficiency loss
            battery_charge_cost=import_cost_now / charge_kwh,
            include_vat=True
        )

        if future_savings < 1.0:  # Less than 1 SEK value
            return None  # Not worth it

        recommendation = AgentRecommendation(
            agent_name=self.name,
            action=AgentAction.CHARGE,
            kwh=charge_kwh,
            confidence=0.85,
            value_sek=future_savings,
            priority=3,  # Medium priority (lower than peak shaving)
            reasoning=(
                f"Night charging opportunity: {current_price:.2f} SEK/kWh spot price. "
                f"Charging {charge_kwh:.1f} kWh for future self-consumption. "
                f"Expected savings: {future_savings:.0f} SEK."
            ),
            metadata={
                'charge_price': current_price,
                'charge_cost_sek': import_cost_now,
                'expected_future_price': future_avg_price,
                'expected_savings_sek': future_savings,
                'target_soc_kwh': target_soc
            }
        )

        self._record_recommendation(recommendation)
        return recommendation

    def _analyze_self_consumption(self, context: BatteryContext) -> Optional[AgentRecommendation]:
        """
        Analyze self-consumption opportunity.

        Discharge to cover consumption instead of importing from grid.
        This is almost always profitable during day hours.
        """

        # CRITICAL: NEVER discharge for self-consumption during E.ON measurement hours (06-23)!
        # Reasons:
        # 1. Peak shaving is 60 SEK/kW/month = ~2 SEK/kWh value
        # 2. Self-consumption saves only ~0.10 SEK/kWh
        # 3. Need to preserve battery for evening spikes (17-23)
        # 4. Self-consumption can happen at night (00-05) when E.ON doesn't measure
        if context.is_measurement_hour:
            return None  # Save battery for peak shaving during E.ON hours

        current_price = context.spot_price_sek_kwh

        # How much consumption can we cover?
        available_discharge = context.soc_kwh - context.min_soc_kwh
        discharge_kwh = min(
            context.consumption_kw,  # Cover current consumption
            available_discharge,  # Battery availability
            context.max_discharge_kw  # Hardware limit
        )

        if discharge_kwh < 0.5:  # Less than 0.5 kWh
            return None  # Not enough to discharge

        # Calculate value
        value = self.value_calculator.calculate_self_consumption_value(
            spot_price=current_price,
            kwh=discharge_kwh,
            battery_charge_cost=0.60,  # Typical night charging cost
            include_vat=True
        )

        if value < 0.5:  # Less than 0.50 SEK value
            return None  # Not worth it

        # Priority depends on price
        if current_price > 2.50:
            priority = 2  # High value hour
            confidence = 0.90
        elif current_price > 1.50:
            priority = 3  # Medium value hour
            confidence = 0.80
        else:
            # Low price hour - might want to save battery for peaks
            priority = 4
            confidence = 0.60

        recommendation = AgentRecommendation(
            agent_name=self.name,
            action=AgentAction.DISCHARGE,
            kwh=discharge_kwh,
            confidence=confidence,
            value_sek=value,
            priority=priority,
            reasoning=(
                f"Self-consumption opportunity: {current_price:.2f} SEK/kWh spot price. "
                f"Discharging {discharge_kwh:.1f} kWh to cover consumption instead of grid import. "
                f"Saves {value:.0f} SEK vs buying from grid."
            ),
            metadata={
                'spot_price': current_price,
                'consumption_kw': context.consumption_kw,
                'import_cost_avoided': self.value_calculator.calculate_import_cost(
                    current_price, discharge_kwh, include_vat=True
                ),
                'battery_cost': 0.60 * discharge_kwh,
                'net_savings': value
            }
        )

        self._record_recommendation(recommendation)
        return recommendation

    def _analyze_export(self, context: BatteryContext) -> Optional[AgentRecommendation]:
        """
        Analyze export arbitrage opportunity.

        IMPORTANT: Export is almost NEVER better than self-consumption!
        - Self-consumption saves: ~2.50 SEK/kWh (import cost)
        - Export earns: ~0.80 SEK/kWh (spot - överföringsavgift)

        Only export when:
        - Spot price VERY high (> 3.00 SEK/kWh)
        - No consumption to cover (excess capacity)
        - Export revenue > battery charge cost
        - Battery has excess capacity beyond peak reserve
        """
        current_price = context.spot_price_sek_kwh

        if current_price < self.min_export_price:
            return None  # Price not high enough

        # Calculate export revenue (spot - överföringsavgift)
        export_revenue_per_kwh = max(0, current_price - self.value_calculator.transfer_fee)

        # Check if export is profitable vs battery charge cost
        battery_charge_cost = 0.60  # Typical night charging cost
        if export_revenue_per_kwh < battery_charge_cost:
            return None  # Would lose money! Better to use for self-consumption later

        if export_revenue_per_kwh < 1.0:  # Less than 1 SEK/kWh revenue
            return None  # Not profitable enough

        # How much can we export?
        available_discharge = context.soc_kwh - context.min_soc_kwh
        # Note: In real system, would check peak_shaving_agent.should_reserve_capacity()
        # For now, keep 5 kWh reserve for potential peaks
        reserve_for_peaks = 5.0 if context.is_measurement_hour else 2.0

        export_kwh = min(
            available_discharge - reserve_for_peaks,
            context.max_discharge_kw  # Hardware limit
        )

        if export_kwh < 1.0:  # Less than 1 kWh
            return None  # Not enough to export

        # Calculate profit
        profit = self.value_calculator.calculate_arbitrage_value(
            discharge_price=current_price,
            charge_price=0.60,  # Typical night charging cost
            kwh=export_kwh
        )

        if profit < self.min_profit:
            return None  # Not profitable enough

        # High price = high priority
        priority = 2 if current_price > 5.0 else 3
        confidence = 0.70  # Lower confidence - export is risky

        recommendation = AgentRecommendation(
            agent_name=self.name,
            action=AgentAction.EXPORT,
            kwh=export_kwh,
            confidence=confidence,
            value_sek=profit,
            priority=priority,
            reasoning=(
                f"Export arbitrage opportunity: {current_price:.2f} SEK/kWh spot price! "
                f"Exporting {export_kwh:.1f} kWh for {profit:.0f} SEK profit. "
                f"Revenue: {export_revenue_per_kwh:.2f} SEK/kWh after transfer fee."
            ),
            metadata={
                'spot_price': current_price,
                'export_revenue_per_kwh': export_revenue_per_kwh,
                'export_revenue_total': export_revenue_per_kwh * export_kwh * context.efficiency,
                'charge_cost': 0.60 * export_kwh,
                'net_profit': profit,
                'reserve_maintained_kwh': reserve_for_peaks
            }
        )

        self._record_recommendation(recommendation)
        return recommendation

    def explain_decision(self, context: BatteryContext, recommendation: AgentRecommendation) -> str:
        """
        Provide detailed explanation of arbitrage decision.
        """
        action = recommendation.action
        metadata = recommendation.metadata

        if action == AgentAction.CHARGE:
            return f"""
## Arbitrage: Night Charging

**Opportunity:** Low spot price during night hours.

**Current Conditions:**
- Time: {context.timestamp.strftime('%Y-%m-%d %H:%M')}
- Spot Price: {metadata['charge_price']:.2f} SEK/kWh
- Import Cost (with fees): {metadata['charge_cost_sek'] / recommendation.kwh:.2f} SEK/kWh

**Action:**
- Charge: {recommendation.kwh:.1f} kWh
- Cost: {metadata['charge_cost_sek']:.0f} SEK

**Future Value:**
- Expected day price: {metadata['expected_future_price']:.2f} SEK/kWh
- Expected savings: {metadata['expected_savings_sek']:.0f} SEK
- Use for self-consumption during day hours

**Battery State:**
- Current SOC: {context.soc_kwh:.1f} kWh
- After charge: {context.soc_kwh + recommendation.kwh:.1f} kWh
- Target: {metadata['target_soc_kwh']:.1f} kWh

**Confidence:** {recommendation.confidence * 100:.0f}%
"""

        elif action == AgentAction.DISCHARGE:
            return f"""
## Arbitrage: Self-Consumption

**Opportunity:** Use battery instead of expensive grid import.

**Current Conditions:**
- Time: {context.timestamp.strftime('%Y-%m-%d %H:%M')}
- Spot Price: {metadata['spot_price']:.2f} SEK/kWh
- Import Cost (with fees): {metadata['import_cost_avoided'] / recommendation.kwh:.2f} SEK/kWh
- Consumption: {metadata['consumption_kw']:.1f} kW

**Economics:**
- Cost if buying from grid: {metadata['import_cost_avoided']:.0f} SEK
- Cost from battery (charged at night): {metadata['battery_cost']:.0f} SEK
- **Net savings: {metadata['net_savings']:.0f} SEK**

**Action:**
- Discharge: {recommendation.kwh:.1f} kWh to cover consumption
- Avoid grid import: {recommendation.kwh:.1f} kWh

**Battery State:**
- Current SOC: {context.soc_kwh:.1f} kWh
- After discharge: {context.soc_kwh - recommendation.kwh:.1f} kWh
- Reserve maintained: {(context.soc_kwh - recommendation.kwh - context.min_soc_kwh):.1f} kWh

**Why self-consumption beats export:**
- Saving {metadata['import_cost_avoided'] / recommendation.kwh:.2f} SEK/kWh by avoiding import
- vs earning only ~{metadata['spot_price'] - 0.42:.2f} SEK/kWh from export

**Confidence:** {recommendation.confidence * 100:.0f}%
"""

        elif action == AgentAction.EXPORT:
            return f"""
## Arbitrage: Export to Grid

**Opportunity:** EXTREME spot price makes export profitable!

**Current Conditions:**
- Time: {context.timestamp.strftime('%Y-%m-%d %H:%M')}
- Spot Price: {metadata['spot_price']:.2f} SEK/kWh (very high!)
- Export Revenue: {metadata['export_revenue_per_kwh']:.2f} SEK/kWh (after transfer fee)
- Consumption: {context.consumption_kw:.1f} kW

**Economics:**
- Export revenue: {metadata['export_revenue_total']:.0f} SEK
- Battery charge cost: {metadata['charge_cost']:.0f} SEK
- **Net profit: {metadata['net_profit']:.0f} SEK**

**Action:**
- Export: {recommendation.kwh:.1f} kWh to grid
- Profit: {recommendation.value_sek:.0f} SEK

**Battery State:**
- Current SOC: {context.soc_kwh:.1f} kWh
- After export: {context.soc_kwh - recommendation.kwh:.1f} kWh
- Reserve for peaks: {metadata['reserve_maintained_kwh']:.1f} kWh

**Note:** Export only happens during extreme prices (>{self.min_export_price} SEK/kWh).
Most of the time, self-consumption is more valuable.

**Confidence:** {recommendation.confidence * 100:.0f}%
"""

        return "Arbitrage decision."

    def __repr__(self):
        return (f"ArbitrageAgent(min_profit={self.min_profit}SEK, "
                f"recommendations={self.recommendations_count}, "
                f"value={self.total_value_generated:.0f}SEK)")
