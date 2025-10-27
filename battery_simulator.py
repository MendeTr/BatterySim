import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
import requests
import os

# Multi-agent system imports
from agents import (
    PeakTracker,
    ValueCalculator,
    BatteryContext,
    RealTimeOverrideAgent,
    PeakShavingAgent,
    ArbitrageAgent,
    Orchestrator,
    AgentAction
)

class GPTArbitrageAgent:
    """
    GPT-powered arbitrage decision agent for battery optimization
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.base_url = "https://api.openai.com/v1/chat/completions"
        
    def make_arbitrage_decision(self, context: Dict) -> Dict:
        """
        Use GPT to make intelligent arbitrage decisions
        
        Args:
            context: Dictionary containing current state and market data
            
        Returns:
            Dictionary with action, amount, and reasoning
        """
        if not self.api_key:
            # Fallback to rule-based system if no API key
            return self._fallback_decision(context)
            
        prompt = self._build_prompt(context)
        
        try:
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert energy arbitrage AI for Swedish electricity markets. Analyze the provided context and make optimal battery charge/discharge decisions to maximize profit while considering solar self-consumption, grid fees, taxes, and export rates."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                decision_text = result['choices'][0]['message']['content']
                return self._parse_gpt_response(decision_text, context)
            else:
                print(f"GPT API error: {response.status_code}")
                return self._fallback_decision(context)
                
        except Exception as e:
            print(f"GPT API call failed: {e}")
            return self._fallback_decision(context)
    
    def _build_prompt(self, context: Dict) -> str:
        """Build the prompt for GPT with current market context"""
        
        prompt = f"""
=== SYSTEM OVERVIEW (SE4 Sweden) ===
Time: {context['current_time']} | Price: {context['current_price']:.3f} SEK/kWh
Battery: {context['soc']:.1f} kWh ({context['soc_percent']:.1f}%) | Capacity: {context['battery_capacity']} kWh | Power: {context['battery_power']} kW
Solar: {context['solar']:.2f} kWh | Consumption: {context['consumption']:.2f} kWh | Efficiency: {context['efficiency']:.2f}

                COSTS:
                - Buy from grid: {context['current_price'] + context['grid_fee'] + context['energy_tax']:.3f} SEK/kWh
                - Sell to grid: {max(0, context['current_price'] - context['transfer_fee']):.3f} SEK/kWh (spot - transfer fee)
                - Peak fee: {context['effect_tariff_sek_kw_month']} SEK/kW/month (measured 06:00-23:00)

=== MARKET DATA (Next 24h) ===
PRICES: {context['price_forecast']}
CONSUMPTION: {context['consumption_forecast']}
SOLAR: {context['solar_forecast']}

PEAK ANALYSIS (06:00-23:00):
- Currently in peak hours: {context['is_peak_hours']}
- Historical peaks (last 7 days): {context['historical_peaks']}

=== DECISION FRAMEWORK ===

                PRIORITY 1: PEAK SHAVING (Highest value: {context['effect_tariff_sek_kw_month']} SEK/kW/month)
                Rule: IF peak_hours AND consumption > 5.0 kW AND soc > 10%
                  → DISCHARGE to keep grid consumption < 5 kW
                  → Target: Reduce peak by max possible (up to {context['battery_power']} kW limit)
                  → CRITICAL: With {context['battery_power']} kW power, you can cut ANY peak!
                  → MANDATORY: ALWAYS discharge during peak hours if consumption > 5 kW!

PRIORITY 2: PREDICTIVE CHARGING (Prepare for peaks)
Rule: IF night_hours (00:00-06:00) AND soc < 95%
  → Sub-rule A: IF price < 0.5 SEK/kWh → CHARGE (cheap opportunity)
  → Sub-rule B: IF next_24h has consumption > 6 kW → CHARGE (prepare for peak)
  → Sub-rule C: IF price < 0.8 SEK/kWh AND tomorrow_avg_consumption > 5 kW → CHARGE
  → Target SOC: 90% for next peak period

PRIORITY 3: ARBITRAGE (Only if peak shaving not needed)
Rule: IF NOT peak_hours OR soc > 95%
  → CHARGE if: price < 0.3 SEK/kWh AND no high consumption in next 12h
  → DISCHARGE if: price > 2.0 SEK/kWh AND no high consumption in next 6h AND NOT peak_hours
  → Minimum profit: 0.5 SEK/kWh after all costs

SOLAR PRIORITY: Always self-consume solar first. Battery charges from solar are "free" for SOC targets.

SOC MANAGEMENT:
- Peak hours (06:00-23:00): Maintain 80-95% SOC
- Night hours (00:00-06:00): Allow 20-95% SOC
- Safety minimum: Never discharge below 10% SOC
- Safety maximum: Never charge above 98% SOC

                === DECISION LOGIC (Apply in order) ===
                1. IF consumption > 5 kW AND peak_hours AND soc > 10% 
                   → DISCHARGE up to {context['battery_power']} kW (immediate peak shaving)
                   → CRITICAL: With {context['battery_power']} kW, you can cut consumption from 12 kW to 5 kW!

                2. ELSE IF hour == 0-6 AND soc < 95% AND (price < 0.5 OR next_day_has_peaks)
                   → CHARGE up to {context['battery_power']} kW (prepare for tomorrow)

                3. ELSE IF price < 0.3 AND soc < 95% AND no_peaks_next_12h AND NOT peak_hours
                   → CHARGE up to {context['battery_power']} kW (arbitrage opportunity)

                4. ELSE IF price > 2.0 AND soc > 80% AND no_peaks_next_6h AND NOT peak_hours
                   → DISCHARGE up to {context['battery_power']} kW (arbitrage opportunity)

                5. ELSE → HOLD

                === OUTPUT FORMAT ===
                {{
                    "action": "charge|discharge|hold",
                    "amount_kwh": float,  // How much to charge/discharge (0 if hold, max {context['battery_power']} kW)
                    "reasoning": "Brief explanation with priority level",
                    "confidence": float,  // 0.0-1.0 (high: >0.8, medium: 0.5-0.8, low: <0.5)
                    "priority": "peak_shaving|predictive|arbitrage|hold",
                    "expected_impact": "Brief economic impact estimate"
                }}

CONFIDENCE GUIDELINES:
- High (>0.8): Clear peak event, extreme prices, certain forecasts
- Medium (0.5-0.8): Normal operations, typical patterns
- Low (<0.5): Uncertain forecasts, edge cases, conflicting signals
"""
        return prompt
    
    def _parse_gpt_response(self, response_text: str, context: Dict) -> Dict:
        """Parse GPT response and return structured decision"""
        try:
            # Extract JSON from response
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end != 0:
                json_str = response_text[start:end]
                decision = json.loads(json_str)
                
                # Validate and sanitize decision
                action = decision.get('action', 'hold').lower()
                if action not in ['charge', 'discharge', 'hold']:
                    action = 'hold'
                    
                amount = float(decision.get('amount_kwh', 0))
                amount = max(0, min(amount, context['battery_power']))  # Limit to battery power
                
                return {
                    'action': action,
                    'amount_kwh': amount,
                    'reasoning': decision.get('reasoning', 'GPT decision'),
                    'confidence': float(decision.get('confidence', 0.5))
                }
        except Exception as e:
            print(f"Failed to parse GPT response: {e}")
            
        return self._fallback_decision(context)
    
    def _fallback_decision(self, context: Dict) -> Dict:
        """Fallback rule-based decision when GPT is unavailable"""
        current_price = context['current_price']
        total_cost = current_price + context['grid_fee'] + context['energy_tax']
        export_revenue = max(0, current_price - context['transfer_fee'])

        # Simple rule: only arbitrage if there's >0.5 SEK/kWh profit margin
        if export_revenue > total_cost + 0.5 and context['soc'] > 1.0:
            return {
                'action': 'discharge',
                'amount_kwh': min(context['battery_power'], context['soc']),
                'reasoning': 'Rule-based: High profit margin',
                'confidence': 0.3
            }
        elif total_cost < current_price * 0.5 and context['soc'] < context['battery_capacity'] * 0.9:
            return {
                'action': 'charge',
                'amount_kwh': min(context['battery_power'], context['battery_capacity'] - context['soc']),
                'reasoning': 'Rule-based: Low price opportunity',
                'confidence': 0.3
            }
        
        return {
            'action': 'hold',
            'amount_kwh': 0,
            'reasoning': 'Rule-based: No profitable opportunity',
            'confidence': 0.5
        }


class BatteryROISimulator:
    """
    Battery ROI Simulator for Swedish Solar + Battery installations
    Simulates battery operation with historical data and calculates ROI
    """

    def __init__(self, battery_capacity_kwh: float, battery_power_kw: float,
                 battery_efficiency: float = 0.95, battery_cost_sek: float = 80000,
                 battery_lifetime_years: int = 15, use_gpt_arbitrage: bool = False,
                 use_multi_agent: bool = False,
                 use_boss_agent: bool = False,
                 progress_callback=None):
        """
        Initialize battery simulator

        Args:
            battery_capacity_kwh: Battery capacity in kWh (Kapacitet)
            battery_power_kw: Maximum charge/discharge power in kW (Effekt)
            battery_efficiency: Round-trip efficiency (0-1)
            battery_cost_sek: Total battery system cost in SEK (inkl installation)
            battery_lifetime_years: Expected battery lifetime
            use_gpt_arbitrage: Whether to use GPT agent for smart planning
            use_multi_agent: Whether to use multi-agent system (faster, more accurate)
            progress_callback: Function to call with progress updates for frontend
        """
        self.capacity = battery_capacity_kwh
        self.power = battery_power_kw
        self.efficiency = battery_efficiency
        self.cost = battery_cost_sek
        self.lifetime = battery_lifetime_years
        self.use_gpt_arbitrage = use_gpt_arbitrage
        self.use_multi_agent = use_multi_agent
        self.use_boss_agent = use_boss_agent
        self.progress_callback = progress_callback

        # Initialize GPT agent if requested
        if use_gpt_arbitrage:
            self.gpt_agent = GPTArbitrageAgent()
        else:
            self.gpt_agent = None

        # Storage for daily plans (when using GPT)
        self.daily_plans = {}

        # Initialize multi-agent system if requested
        self.multi_agent_orchestrator = None
        self.boss_agent = None
        self.peak_tracker = None
        self.value_calculator = None
        self.consumption_analyzer = None
        self.reserve_calculator = None

        if use_multi_agent:
            self._initialize_multi_agent_system()
        elif use_boss_agent:
            # Boss agent needs to be initialized later with historical data
            pass

    def _send_progress(self, message: str, percent: float):
        """Send progress update to frontend"""
        if self.progress_callback:
            self.progress_callback({'message': message, 'percent': percent})

    def _initialize_multi_agent_system(self):
        """Initialize the multi-agent optimization system."""
        print("🤖 Initializing multi-agent system...")

        # Create infrastructure components
        self.peak_tracker = PeakTracker(
            measurement_start_hour=6,
            measurement_end_hour=23,
            top_n=3
        )

        self.value_calculator = ValueCalculator(
            grid_fee_sek_kwh=0.42,  # Will be updated with actual values during simulation
            energy_tax_sek_kwh=0.40,
            transfer_fee_sek_kwh=0.42,
            vat_rate=0.25,
            effect_tariff_sek_kw_month=60.0,
            battery_efficiency=self.efficiency
        )

        # Create specialist agents
        override_agent = RealTimeOverrideAgent(
            spike_threshold_kw=10.0,
            critical_peak_margin_kw=1.0
        )

        peak_agent = PeakShavingAgent(
            peak_tracker=self.peak_tracker,
            value_calculator=self.value_calculator,
            target_peak_kw=5.0,
            aggressive_threshold_multiplier=0.70  # Act at 70% of threshold (more preventive!)
        )

        arbitrage_agent = ArbitrageAgent(
            value_calculator=self.value_calculator,
            min_arbitrage_profit_sek=20.0,  # Higher bar - only trade if really profitable
            min_export_spot_price=3.0,  # Only export at 3+ SEK/kWh (user requirement)
            night_charge_threshold=0.40  # Only charge at night if EXTREMELY cheap (below 0.40)
        )

        # Create orchestrator
        self.multi_agent_orchestrator = Orchestrator(
            agents=[override_agent, peak_agent, arbitrage_agent],
            value_calculator=self.value_calculator,
            use_llm_for_conflicts=False  # Rule-based for speed
        )

        print(f"✅ Multi-agent system initialized: {self.multi_agent_orchestrator}")
        print(f"   Agents: RealTimeOverride, PeakShaving, Arbitrage")

    def _initialize_boss_agent_system(self, historical_df: pd.DataFrame):
        """
        Initialize the Boss Agent (reserve-based) system with historical data.

        Args:
            historical_df: Historical consumption data for pattern analysis
        """
        from agents.consumption_analyzer import ConsumptionAnalyzer
        from agents.reserve_calculator import DynamicReserveCalculator
        from agents.boss_agent import BossAgent

        print("👔 Initializing Boss Agent (reserve-based) system...")

        # Create infrastructure
        self.peak_tracker = PeakTracker(
            measurement_start_hour=6,
            measurement_end_hour=23,
            top_n=3
        )

        self.value_calculator = ValueCalculator(
            grid_fee_sek_kwh=0.42,  # Will be updated with actual values
            energy_tax_sek_kwh=0.40,
            transfer_fee_sek_kwh=0.42,
            vat_rate=0.25,
            effect_tariff_sek_kw_month=60.0,
            battery_efficiency=self.efficiency
        )

        # Analyze historical consumption patterns
        self.consumption_analyzer = ConsumptionAnalyzer(
            historical_data=historical_df,
            consumption_col='consumption_kwh'
        )

        # Create reserve calculator
        self.reserve_calculator = DynamicReserveCalculator(
            consumption_analyzer=self.consumption_analyzer,
            grid_import_limit_kw=5.0,  # Target peak
            max_discharge_kw=self.power,  # Inverter limit
            default_percentile=95,
            safety_buffer=1.15,
            spike_duration_hours=0.5,  # Assume 30-min spikes
            min_reserve_kwh=2.0,
            max_reserve_kwh=15.0
        )

        # Create specialist agents
        override_agent = RealTimeOverrideAgent(
            spike_threshold_kw=10.0,
            critical_peak_margin_kw=1.0
        )

        peak_agent = PeakShavingAgent(
            peak_tracker=self.peak_tracker,
            value_calculator=self.value_calculator,
            target_peak_kw=5.0,
            aggressive_threshold_multiplier=0.80
        )

        arbitrage_agent = ArbitrageAgent(
            value_calculator=self.value_calculator,
            min_arbitrage_profit_sek=20.0,
            min_export_spot_price=3.0,
            night_charge_threshold=0.40
        )

        # Create Boss Agent coordinator
        self.boss_agent = BossAgent(
            consumption_analyzer=self.consumption_analyzer,
            reserve_calculator=self.reserve_calculator,
            peak_shaving_agent=peak_agent,
            arbitrage_agent=arbitrage_agent,
            real_time_override_agent=override_agent,
            verbose=False  # Set to True for detailed logging
        )

        print(f"✅ Boss Agent system initialized")
        print(f"   Historical data: {len(historical_df)} hours")
        print(f"   Agents: RealTimeOverride, PeakShaving (reserve-based), Arbitrage")
        print(f"   Strategy: Reserve-first with statistical analysis")

    def _get_consumption_forecast(self, df: pd.DataFrame, current_idx: int, current_hour: int) -> List[float]:
        """
        Generate consumption forecast for next 24 hours based on historical patterns.

        This learns typical consumption at each hour of the day from PAST data only.
        Example: Hour 7 typically has 8 kW (morning wake-up), hour 18 has 6 kW (dinner).

        IMPORTANT: Only use data BEFORE current_idx to avoid using future data!
        """
        forecast = []

        # Only use historical data (before current time)
        historical_df = df.iloc[:current_idx]

        if len(historical_df) < 24:
            # Not enough history yet, use overall average
            avg = df['consumption_kwh'].mean() if len(historical_df) == 0 else historical_df['consumption_kwh'].mean()
            return [avg] * 24

        # For each of the next 24 hours
        for i in range(24):
            future_hour = (current_hour + i) % 24

            # Find all historical data for this hour of day
            historical_at_hour = historical_df[historical_df['timestamp'].dt.hour == future_hour]['consumption_kwh']

            if len(historical_at_hour) > 0:
                # Use average of historical consumption at this hour
                avg_consumption = historical_at_hour.mean()
                forecast.append(avg_consumption)
            else:
                # Fallback: use overall average
                forecast.append(historical_df['consumption_kwh'].mean())

        return forecast

    def _build_battery_context(self, df: pd.DataFrame, idx: int, soc: float,
                               grid_fee_sek_kwh: float, energy_tax_sek_kwh: float,
                               vat_rate: float) -> BatteryContext:
        """Build BatteryContext for current hour."""
        row = df.iloc[idx]
        timestamp = row['timestamp']
        hour = timestamp.hour
        month_key = timestamp.strftime('%Y-%m')

        # Get spot price forecast for next 24 hours
        spot_forecast = []
        for i in range(min(24, len(df) - idx)):
            spot_forecast.append(df.iloc[idx + i]['spot_price_sek_kwh'])

        # Get consumption forecast for next 24 hours (from historical patterns)
        consumption_forecast = self._get_consumption_forecast(df, idx, hour)

        # Calculate import cost and export revenue
        spot_price = row['spot_price_sek_kwh']
        import_cost = (spot_price + grid_fee_sek_kwh + energy_tax_sek_kwh) * (1 + vat_rate)
        export_revenue = max(0, spot_price - grid_fee_sek_kwh)

        # Get peak tracking data
        top_n_peaks = self.peak_tracker.get_top_n_peaks(month_key) if self.peak_tracker else []
        peak_threshold = self.peak_tracker.get_threshold(month_key) if self.peak_tracker else 0.0

        # Get consumption stats
        consumption_kw = row['consumption_kwh']
        avg_consumption = df['consumption_kwh'].mean()
        peak_consumption = df['consumption_kwh'].max()

        return BatteryContext(
            timestamp=timestamp,
            hour=hour,
            soc_kwh=soc,
            capacity_kwh=self.capacity,
            max_charge_kw=self.power,
            max_discharge_kw=self.power,
            efficiency=self.efficiency,
            consumption_kw=consumption_kw,
            solar_production_kw=row.get('solar_kwh', 0.0),
            grid_import_kw=consumption_kw - row.get('solar_kwh', 0.0),  # Before battery
            spot_price_sek_kwh=spot_price,
            import_cost_sek_kwh=import_cost,
            export_revenue_sek_kwh=export_revenue,
            spot_forecast=spot_forecast,
            consumption_forecast=consumption_forecast,
            current_month=month_key,
            top_n_peaks=top_n_peaks,
            peak_threshold_kw=peak_threshold,
            is_measurement_hour=(6 <= hour <= 23),
            avg_consumption_kw=avg_consumption,
            peak_consumption_kw=peak_consumption,
            min_soc_kwh=self.capacity * 0.05,  # 5% minimum reserve
            target_morning_soc_kwh=self.capacity * 0.60  # Target 60% at 06:00 (leave room for peak shaving!)
        )

    def _create_daily_plan(self, df: pd.DataFrame, current_idx: int, current_soc: float,
                           grid_fee_sek_kwh: float, energy_tax_sek_kwh: float,
                           effect_tariff_sek_kw_month: float) -> Dict:
        """
        Create a 24-hour battery plan using GPT
        Called once per day at 13:00 when next day's prices are available

        Plans for TOMORROW (next full day 00:00-23:59) to avoid replanning same hours
        Returns dict with hourly actions for next day
        """
        if not self.gpt_agent:
            return {}

        current_time = df.loc[current_idx, 'timestamp']

        # Calculate tomorrow's date
        import datetime
        tomorrow = (current_time + datetime.timedelta(days=1)).date()

        # Check if we already have a plan for tomorrow
        if tomorrow in self.daily_plans:
            return self.daily_plans[tomorrow]

        # Find the start of tomorrow (00:00) in the dataframe
        tomorrow_start_idx = None
        for i in range(current_idx, min(len(df), current_idx + 24)):
            if df.loc[i, 'timestamp'].date() == tomorrow and df.loc[i, 'timestamp'].hour == 0:
                tomorrow_start_idx = i
                break

        if tomorrow_start_idx is None:
            # Can't find tomorrow in data, fall back to rule-based
            return {}

        # Get 24 hours of tomorrow's data for planning
        end_idx = min(len(df) - 1, tomorrow_start_idx + 24)
        forecast_df = df.loc[tomorrow_start_idx:end_idx].copy()

        # Build comprehensive context for GPT
        context = {
            'current_time': current_time,
            'current_soc': current_soc,
            'soc_percent': (current_soc / self.capacity) * 100,
            'battery_capacity': self.capacity,
            'battery_power': self.power,
            'efficiency': self.efficiency,
            'grid_fee': grid_fee_sek_kwh,
            'energy_tax': energy_tax_sek_kwh,
            'transfer_fee': grid_fee_sek_kwh,  # Same as grid fee (user configurable)
            'effect_tariff_sek_kw_month': effect_tariff_sek_kw_month,
            'eon_peak_hours': '06:00-23:00',  # E.ON measures peaks only during these hours

            # Next 24-48 hours forecast
            'price_forecast': forecast_df[['timestamp', 'spot_price_sek_kwh']].to_dict('records'),
            'consumption_forecast': forecast_df[['timestamp', 'consumption_kwh']].to_dict('records'),
            'solar_forecast': forecast_df[['timestamp', 'solar_kwh']].to_dict('records'),

            # Historical consumption patterns (last 7 days same hours)
            'consumption_patterns': self._get_consumption_patterns(df, current_idx)
        }

        # Get GPT to create 24-hour plan
        prompt = self._build_daily_planning_prompt(context)

        # Retry logic for API timeouts
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"  🔄 Calling OpenAI API (attempt {attempt + 1}/{max_retries})...")
                # Call GPT API
                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.gpt_agent.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an expert battery energy management AI for Swedish electricity markets. Create optimal 24-hour charge/discharge schedules that maximize savings through peak shaving (E.ON 06:00-23:00) and price arbitrage."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.1,
                        "max_tokens": 2000
                    },
                    timeout=60  # Increased from 30 to 60 seconds
                )
                # Success! Process the response
                print(f"  📡 API Response Status: {response.status_code}")

                if response.status_code == 200:
                    result = response.json()
                    plan_text = result['choices'][0]['message']['content']
                    print(f"  ✅ Got GPT response ({len(plan_text)} chars)")
                    daily_plan = self._parse_daily_plan(plan_text)
                    if daily_plan:
                        print(f"  ✅ Parsed {len(daily_plan)} hourly decisions")
                        # Debug: Show what actions GPT planned
                        discharge_hours = [h for h, action in daily_plan.items() if action.get('action') == 'discharge']
                        charge_hours = [h for h, action in daily_plan.items() if action.get('action') == 'charge']
                        print(f"  📊 Plan: Discharge during hours {discharge_hours}, Charge during hours {charge_hours}")
                    else:
                        print(f"  ⚠️  Failed to parse plan")
                        print(f"  Raw response: {plan_text[:200]}...")
                    self.daily_plans[tomorrow] = daily_plan
                    return daily_plan
                else:
                    print(f"  ❌ GPT API error: {response.status_code}")
                    print(f"  Response: {response.text[:500]}")
                    return {}

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    print(f"  ⏱️  Timeout, retrying...")
                    import time
                    time.sleep(2)  # Wait 2 seconds before retry
                    continue
                else:
                    print(f"  ❌ Failed after {max_retries} attempts, using fallback")
                    return {}  # Fallback to rule-based
            except Exception as e:
                print(f"  ❌ API error: {e}")
                import traceback
                traceback.print_exc()
                return {}

        # Should not reach here
        return {}

    def _get_consumption_patterns(self, df: pd.DataFrame, current_idx: int) -> Dict:
        """Get historical consumption patterns for same hours in past week"""
        patterns = {}
        current_time = df.loc[current_idx, 'timestamp']

        # Look back 7 days
        for day_offset in range(1, 8):
            past_idx = current_idx - (24 * day_offset)
            if past_idx >= 0:
                for hour_offset in range(24):
                    check_idx = past_idx + hour_offset
                    if check_idx < len(df):
                        hour = df.loc[check_idx, 'timestamp'].hour
                        consumption = df.loc[check_idx, 'consumption_kwh']
                        if hour not in patterns:
                            patterns[hour] = []
                        patterns[hour].append(consumption)

        # Calculate average consumption per hour
        avg_patterns = {hour: sum(values) / len(values)
                       for hour, values in patterns.items() if values}

        return avg_patterns

    def _build_daily_planning_prompt(self, context: Dict) -> str:
        """Build GPT prompt for daily battery planning"""
        return f"""You are planning a 24-hour battery schedule for a Swedish home with solar panels.

**CURRENT STATUS:**
- Time: {context['current_time']}
- Battery SOC: {context['current_soc']:.1f} kWh ({context['soc_percent']:.0f}%)
- Capacity: {context['battery_capacity']} kWh
- Max Power: {context['battery_power']} kW
- Efficiency: {context['efficiency']*100:.0f}%

**MARKET CONDITIONS:**
- Grid fee (import): {context['grid_fee']:.2f} SEK/kWh
- Transfer fee (export): {context['transfer_fee']:.2f} SEK/kWh
- Energy tax: {context['energy_tax']:.2f} SEK/kWh
- Export revenue formula: spot_price - transfer_fee (don't export if spot < transfer fee!)
- Effect tariff: {context['effect_tariff_sek_kw_month']} SEK/kW/month (measured {context['eon_peak_hours']})

**PRIORITIES:**
1. **Smart Peak Shaving (HIGHEST PRIORITY)**: E.ON measures peaks during {context['eon_peak_hours']}.
   - TARGET: Keep grid import at or below 5 kW during peak hours
   - DON'T eliminate peaks completely - just flatten them to 5 kW target
   - If consumption is 12 kW, discharge 7 kW to reach 5 kW grid import
   - This saves battery for MULTIPLE peak events per month instead of wasting it on one event!
2. **Arbitrage**: Charge when spot price is low, discharge when high (but not if it conflicts with peak shaving).
3. **Self-consumption**: Use solar directly when available.

**HISTORICAL CONSUMPTION PATTERNS (avg kW per hour from past 7-30 days):**
{self._format_consumption_patterns(context['consumption_patterns'])}

**TOMORROW'S SOLAR FORECAST (estimated based on season/weather):**
{self._format_solar_forecast(context['solar_forecast'][:24])}

**NEXT 24-48H PRICE FORECAST:**
{self._format_price_forecast(context['price_forecast'][:48])}

**IMPORTANT:** You do NOT know tomorrow's exact consumption - only historical patterns!
Use the historical patterns to predict when peaks are LIKELY to occur, then plan accordingly.

**TASK:**
Create a 24-hour plan for TOMORROW (00:00-23:59). For each hour, decide: charge, discharge, or hold.

⚠️ CRITICAL BATTERY MANAGEMENT:
Your current SOC is {context['current_soc']:.1f} kWh ({context['soc_percent']:.0f}%). Battery capacity is {context['battery_capacity']} kWh.

STEP 1 - ANALYZE HISTORICAL PATTERNS (predict tomorrow's consumption):
Look at "HISTORICAL CONSUMPTION PATTERNS" to understand when peaks typically occur:

🔥 HIGH PEAK DAY PREDICTION: If historical patterns show hours > 8 kW
  → Strategy: Conserve battery for those typical peak hours
  → Discharge aggressively during historical peak times (usually 17:00-20:00)
  → Example: If Hour 18 averages 10 kW historically, plan to discharge there

💚 LOW PEAK DAY PREDICTION: If historical patterns show NO hours > 8 kW
  → Strategy: USE BATTERY FREELY! No need to save capacity
  → Discharge during ALL consumption hours to maximize self-consumption
  → This is "free money" - use the battery you charged at night!

Identify typical peak hours from historical data:
- Hours with historical avg > 8 kW = HIGH PEAKS (must reduce to 5 kW)
- Hours with historical avg 5-8 kW = MEDIUM
- Hours with historical avg < 5 kW = LOW

STEP 2 - NIGHT CHARGING STRATEGY (00:00-05:00):
First, ESTIMATE how much discharge capacity you'll need based on HISTORICAL patterns:
- Look at hours 06:00-23:00 in historical consumption patterns
- For each hour with historical avg > 8 kW: estimate discharge needed (avg_consumption - solar - 5)
- Example: Hour 18 averages 10 kW historically, 0 solar → plan for ~5 kW discharge
- Sum up all discharge needs: Total = 5 + 4 + 3... = X kW total
- Add 30% safety buffer (consumption varies day-to-day!)

Then, CHARGE during night (00:00-05:00) to meet this need:
- Charge at FULL POWER ({context['battery_power']} kW) during cheapest hours
- Goal: Battery at 80-95% capacity by 06:00 to handle typical peak hours
- This charging happens at NIGHT (00:00-05:00), NOT during E.ON measurement hours!

STEP 3 - DISCHARGE STRATEGY (E.ON hours 06:00-23:00 ONLY):

⚠️ FIRST: Identify the TOP 3 HIGHEST consumption hours in HISTORICAL PATTERNS (06:00-23:00)
  → These are your CRITICAL hours - they determine the monthly effect tariff!
  → Example: If Hour 18 averages 10 kW, Hour 17 averages 9 kW, Hour 19 averages 8.5 kW
  → RESERVE battery capacity specifically for these typical peak hours!
  → ASSUME tomorrow will be similar to historical average (plan for the pattern, not the exact value)

🔥 Priority 1 (CRITICAL): TOP 3 HIGHEST consumption hours
  → MANDATORY: Discharge to reach EXACTLY 5 kW grid import in these hours
  → Calculation: discharge_amount = (consumption - solar - 5)
  → Example: Hour 18 has 12 kW consumption, 0 kW solar → discharge 7 kW to reach 5 kW grid import
  → Example: Hour 17 has 10 kW consumption, 1 kW solar → discharge 4 kW to reach 5 kW grid import
  → DO NOT discharge heavily in other hours if it means you'll run out before these peaks!
  → If you have 25 kWh battery and need 7+4+3=14 kWh for top 3 peaks → SAVE AT LEAST 14 kWh for them!

⚠️ Priority 2 (MEDIUM): Hours with consumption 5-8 kW
  → Discharge to reduce grid import closer to 5 kW IF battery has capacity left
  → Example: 7 kW consumption, 0 solar → discharge 2 kW to reach 5 kW grid import

💡 Priority 3 (ARBITRAGE): Hours with consumption 5-8 kW OR price > 1.5 SEK/kWh
  → If you have excess capacity after reserving for Priority 1 peaks, use battery here!
  → Discharge during expensive price hours to avoid high grid costs
  → Example: Hour 14 has 1.8 SEK/kWh price and 4 kW consumption → discharge 4 kW for arbitrage

🔋 Priority 4 (SELF-CONSUMPTION): Use battery throughout the day - BUT CAREFULLY!
  → First check: Do you have enough battery for the top 3 peaks? (calculate total needed)
  → ONLY use for self-consumption if you have EXTRA capacity after reserving for top 3 peaks
  → Example: Need 15 kWh for peaks, have 20 kWh → can use 5 kWh for self-consumption
  → Discharge during expensive hours (>1.5 SEK/kWh) or when battery >80% full
  → Reserve minimum 30% (7.5 kWh) for unexpected evening peaks

⚠️ CRITICAL RULE: Peak shaving ALWAYS comes before self-consumption!
  → If you must choose between discharging at Hour 10 (4 kW) or saving for Hour 18 (12 kW peak)
  → ALWAYS save for the peak! The 12 kW peak costs 60 SEK/month, the 4 kW hour costs ~5 SEK
  → Don't waste 7 kWh on small loads if it means missing a 12 kW peak reduction!

⚡ CRITICAL: The top 3 highest peaks in the month determine your effect tariff!

🎯 EXAMPLE CALCULATION (using historical patterns):
Historical patterns show:
- Hour 06: 3 kW avg, Hour 07: 4 kW avg, Hour 08: 5 kW avg...
- Hour 17: 9 kW avg (2nd highest), Hour 18: 10 kW avg (HIGHEST!), Hour 19: 8.5 kW avg (3rd highest)
- Hour 20: 7 kW avg, Hour 21: 6 kW avg, Hour 22: 5 kW avg...

Step-by-step planning:
1. Identify top 3 historical peaks: Hour 18 (10 kW), Hour 17 (9 kW), Hour 19 (8.5 kW)
2. Estimate needed discharge (with 30% buffer for variation):
   - Hour 18: (10 - 0 solar - 5 target) × 1.3 = 6.5 kW discharge planned
   - Hour 17: (9 - 0 solar - 5 target) × 1.3 = 5.2 kW discharge planned
   - Hour 19: (8.5 - 0 solar - 5 target) × 1.3 = 4.6 kW discharge planned
   - TOTAL: ~16.3 kWh needed for top 3 peak hours
3. Battery has 25 kWh, plan to charge to 80% = 20 kWh available
4. RESERVE 16.3 kWh for hours 17-19, can use remaining 3.7 kWh for other hours
5. Plan discharge:
   - Hours 06-16: Discharge MAX 3.7 kWh total (use during expensive price hours or self-consumption)
   - Hour 17: Discharge 5.2 kW → target grid import = 5 kW ✅
   - Hour 18: Discharge 6.5 kW → target grid import = 5 kW ✅
   - Hour 19: Discharge 4.6 kW → target grid import = 5 kW ✅
   - Hours 20-23: Battery low, minimal discharge

Result: Top 3 peaks reduced to ~5 kW → effect tariff minimized = MAXIMUM SAVINGS!
Note: Actual consumption may vary ±20-30% from historical average, hence the buffer.
→ If you have THREE hours with 10+ kW consumption, discharge aggressively on ALL THREE
→ Better to discharge 20 kWh total across 3 big peaks than waste 5 kWh on small loads!

Output format (JSON):
```json
{{
  "plan": [
    {{"hour": 0, "action": "charge|discharge|hold", "amount_kwh": 0.0, "reason": "why"}},
    ...24 hours
  ],
  "strategy_summary": "Overall strategy explanation"
}}
```

EXAMPLE OF PERFECT STRATEGY:
Tomorrow's forecast shows (low peak day):
- Hour 0-5: CHARGE at full power (12 kW × 2h = 24 kWh charged, battery at 96%)
- Hour 7: 3 kW consumption, battery at 95% → DISCHARGE 3 kW (use battery, don't waste capacity!)
- Hour 10: 4 kW consumption, battery at 90% → DISCHARGE 4 kW
- Hour 14: 2 kW consumption, price 1.7 SEK → DISCHARGE 2 kW (arbitrage!)
- Hour 17: 5 kW consumption, battery at 80% → DISCHARGE 5 kW
- Hour 22: 3 kW consumption, battery at 70% → DISCHARGE 3 kW

Result: Battery used throughout day, reduced grid import from 60 kWh to 45 kWh = savings!

EXAMPLE 2: High peak day:
- Hour 0-5: CHARGE 24 kWh (battery at 96%)
- Hour 7-16: HOLD or minimal discharge (save for peaks)
- Hour 17: 11 kW consumption → DISCHARGE 6 kW to reach 5 kW (Priority 1!)
- Hour 18: 12 kW consumption → DISCHARGE 7 kW to reach 5 kW (Priority 1!)
- Hour 19: 10 kW consumption → DISCHARGE 5 kW to reach 5 kW (Priority 1!)

Result: Top 3 peaks all at 5 kW → Monthly peak = 5 kW → Maximum effect tariff savings!

Remember:
- E.ON takes average of TOP 3 PEAKS in the month
- Your goal: Get all top 3 peaks to 5 kW on high peak days
- On LOW peak days (no consumption >8 kW): USE BATTERY for all consumption! Don't let it sit idle!
- Current SOC: {context['current_soc']:.1f} kWh - if this is >15 kWh, you MUST use battery during the day
- NEVER charge during 06:00-23:00 (creates peaks!)
- Don't discharge during 00:00-05:00 (no E.ON measurement)

🚨 MANDATORY RULE: If no consumption >8 kW tomorrow, discharge battery for ALL daytime consumption (06:00-23:00)!
→ Low peak day = free to use battery without worrying about saving capacity
→ Example: Max consumption 6 kW tomorrow → discharge during ALL hours with consumption
→ This maximizes self-consumption and arbitrage savings!
"""

    def _format_consumption_patterns(self, patterns: Dict) -> str:
        """Format consumption patterns for GPT prompt"""
        lines = []
        for hour in range(24):
            avg = patterns.get(hour, 0)
            lines.append(f"  {hour:02d}:00 - {avg:.2f} kW")
        return "\n".join(lines)

    def _format_price_forecast(self, forecast: list) -> str:
        """Format price forecast for GPT prompt"""
        lines = []
        for item in forecast[:24]:  # Only show next 24h
            ts = item['timestamp']
            price = item['spot_price_sek_kwh']
            hour_str = ts.strftime('%Y-%m-%d %H:%00') if hasattr(ts, 'strftime') else str(ts)
            lines.append(f"  {hour_str}: {price:.3f} SEK/kWh")
        return "\n".join(lines)

    def _format_consumption_forecast(self, forecast: list) -> str:
        """Format consumption forecast for GPT prompt"""
        lines = []
        for item in forecast[:24]:  # Only show next 24h
            ts = item['timestamp']
            consumption = item['consumption_kwh']
            hour_only = ts.hour if hasattr(ts, 'hour') else 0
            lines.append(f"  Hour {hour_only:02d}: {consumption:.2f} kW")
        return "\n".join(lines)

    def _format_solar_forecast(self, forecast: list) -> str:
        """Format solar forecast for GPT prompt"""
        lines = []
        for item in forecast[:24]:  # Only show next 24h
            ts = item['timestamp']
            solar = item['solar_kwh']
            hour_only = ts.hour if hasattr(ts, 'hour') else 0
            lines.append(f"  Hour {hour_only:02d}: {solar:.2f} kW")
        return "\n".join(lines)

    def _parse_daily_plan(self, plan_text: str) -> Dict:
        """Parse GPT's daily plan response"""
        try:
            # Extract JSON from markdown code blocks if present
            import json
            import re

            # Try to find JSON in code blocks
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', plan_text, re.DOTALL)
            if json_match:
                plan_json = json.loads(json_match.group(1))
            else:
                # Try to parse the whole text as JSON
                plan_json = json.loads(plan_text)

            # Convert to hour-indexed dict for easy lookup
            hourly_plan = {}
            for item in plan_json.get('plan', []):
                hour = item.get('hour')
                hourly_plan[hour] = {
                    'action': item.get('action', 'hold'),
                    'amount_kwh': float(item.get('amount_kwh', 0)),
                    'reason': item.get('reason', '')
                }

            return hourly_plan

        except Exception as e:
            print(f"Failed to parse GPT plan: {e}")
            print(f"Raw response: {plan_text[:500]}")
            return {}

    def load_tibber_data(self, csv_path: str) -> pd.DataFrame:
        """
        Load and parse Tibber CSV export
        Expected columns: timestamp, consumption (kWh), cost (SEK), spotprice (SEK/kWh)
        """
        df = pd.read_csv(csv_path)
        
        # Handle different possible column names from Tibber
        column_mapping = {
            'Från': 'timestamp',
            'Till': 'timestamp_end',
            'Förbrukning': 'consumption_kwh',
            'Kostnad': 'total_cost_sek',
            'Spotpris': 'spot_price_sek_kwh',
            # Tibber export format
            'timestamp_utc': 'timestamp',
            'timestamp_local': 'timestamp_local',
            'load_kwh': 'consumption_kwh',
            'price_sek_per_kwh': 'spot_price_sek_kwh',
            'cost_sek': 'total_cost_sek',
            'pv_kwh': 'solar_kwh',
            'export_profit_sek': 'export_revenue_sek'
        }
        
        # Rename columns if they exist
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                df = df.rename(columns={old_name: new_name})
        
        # Parse timestamp
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Ensure we have necessary columns
        required = ['timestamp', 'consumption_kwh', 'spot_price_sek_kwh']
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        # If solar data is available in the CSV, use it instead of generating estimates
        if 'solar_kwh' in df.columns:
            print(f"Using real solar production data from CSV: {df['solar_kwh'].sum():.1f} kWh total")
        else:
            print("No solar production data found in CSV, will use estimates")
        
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df
    
    def calculate_current_costs(self, df: pd.DataFrame, grid_fee_sek_kwh: float,
                               energy_tax_sek_kwh: float, vat_rate: float = 0.25) -> Dict:
        """
        Calculate current electricity costs without battery
        """
        # Check if we have real cost data from CSV
        if 'cost_sek' in df.columns and 'export_profit_sek' in df.columns:
            # Use real cost data from CSV (already includes all fees and taxes)
            total_cost = df['cost_sek'].sum() - df['export_profit_sek'].sum()  # Net cost
            total_consumption = df['consumption_kwh'].sum()
            avg_price = total_cost / total_consumption if total_consumption > 0 else 0
            print(f"Using real cost data from CSV: {total_cost:.0f} SEK net cost")
        else:
            # Fallback to calculated costs (for files without cost data)
            df['grid_fee'] = df['consumption_kwh'] * grid_fee_sek_kwh
            df['energy_tax'] = df['consumption_kwh'] * energy_tax_sek_kwh
            df['spot_cost'] = df['consumption_kwh'] * df['spot_price_sek_kwh']
            df['subtotal'] = df['spot_cost'] + df['grid_fee'] + df['energy_tax']
            df['total_cost_with_vat'] = df['subtotal'] * (1 + vat_rate)
            
            total_consumption = df['consumption_kwh'].sum()
            total_cost = df['total_cost_with_vat'].sum()
            avg_price = total_cost / total_consumption if total_consumption > 0 else 0
            print(f"Using calculated costs: {total_cost:.0f} SEK")
        
        return {
            'total_consumption_kwh': total_consumption,
            'total_cost_sek': total_cost,
            'average_price_sek_kwh': avg_price
        }
    
    def add_solar_production(self, df: pd.DataFrame, solar_data: pd.DataFrame = None,
                            solar_capacity_kwp: float = 0) -> pd.DataFrame:
        """
        Add solar production data to the dataframe
        If no solar data provided, generates estimated production based on Swedish patterns
        """
        if solar_data is not None:
            df = df.merge(solar_data, on='timestamp', how='left')
            df['solar_kwh'] = df['solar_kwh'].fillna(0)
        elif solar_capacity_kwp > 0:
            # Simple solar estimation for Sweden
            df['solar_kwh'] = self._estimate_solar_production(df['timestamp'], solar_capacity_kwp)
        else:
            df['solar_kwh'] = 0
        
        # Calculate net consumption (positive = import, negative = export)
        df['net_consumption_kwh'] = df['consumption_kwh'] - df['solar_kwh']
        
        return df
    
    def _estimate_solar_production(self, timestamps: pd.Series, capacity_kwp: float) -> pd.Series:
        """
        Estimate solar production based on time of year and time of day
        Very simplified model for Swedish conditions
        """
        production = []
        
        for ts in timestamps:
            hour = ts.hour
            month = ts.month
            
            # No production at night
            if hour < 6 or hour > 20:
                production.append(0)
                continue
            
            # Seasonal factor (Sweden has dramatic seasonal variation)
            if month in [12, 1, 2]:  # Winter
                seasonal_factor = 0.1
            elif month in [3, 4]:  # Spring
                seasonal_factor = 0.5
            elif month in [5, 6, 7, 8]:  # Summer
                seasonal_factor = 1.0
            elif month in [9, 10]:  # Autumn
                seasonal_factor = 0.5
            else:  # November
                seasonal_factor = 0.2
            
            # Daily curve (bell curve peaking at noon)
            hour_factor = np.sin(np.pi * (hour - 6) / 14) ** 2 if 6 <= hour <= 20 else 0
            
            # Random weather factor (clouds, etc)
            weather_factor = np.random.uniform(0.6, 1.0)
            
            hourly_production = capacity_kwp * seasonal_factor * hour_factor * weather_factor
            production.append(hourly_production)
        
        return pd.Series(production)
    
    def simulate_battery_operation(self, df: pd.DataFrame, grid_fee_sek_kwh: float,
                                   energy_tax_sek_kwh: float, effect_tariff_sek_kw_month: float = 0,
                                   vat_rate: float = 0.25,
                                   enable_arbitrage: bool = True,
                                   effect_tariff_method: str = 'single_peak',
                                   date_range_start: str = None,
                                   date_range_end: str = None) -> Tuple[pd.DataFrame, Dict]:
        """
        Simulate optimal battery operation and calculate savings

        effect_tariff_method: 'single_peak' (highest peak) or 'top3_average' (average of top 3 peaks)
        date_range_start/end: Optional date strings 'YYYY-MM-DD' to limit simulation period
        """
        df = df.copy()

        # Filter by date range if specified
        if date_range_start or date_range_end:
            if date_range_start:
                df = df[df['timestamp'] >= date_range_start]
                print(f"📅 Filtering data from: {date_range_start}")
            if date_range_end:
                df = df[df['timestamp'] <= date_range_end]
                print(f"📅 Filtering data to: {date_range_end}")
            print(f"📊 Simulating {len(df)} hours ({len(df)//24} days)")

        df = df.reset_index(drop=True)

        # Initialize Boss Agent with historical data if needed
        if self.use_boss_agent and not self.boss_agent:
            # Get all data before simulation start (for pattern analysis)
            historical_df = df.copy()
            self._initialize_boss_agent_system(historical_df)

        # Update multi-agent or boss agent systems with actual parameters
        if (self.use_multi_agent or self.use_boss_agent) and self.value_calculator:
            print(f"📊 Updating multi-agent system with actual parameters:")
            print(f"   Grid fee: {grid_fee_sek_kwh} SEK/kWh")
            print(f"   Energy tax: {energy_tax_sek_kwh} SEK/kWh")
            print(f"   Transfer fee: {grid_fee_sek_kwh} SEK/kWh (same as grid fee)")
            print(f"   VAT rate: {vat_rate * 100}%")
            print(f"   Effect tariff: {effect_tariff_sek_kw_month} SEK/kW/month")

            # Update ValueCalculator with actual values from frontend
            self.value_calculator.grid_fee = grid_fee_sek_kwh
            self.value_calculator.energy_tax = energy_tax_sek_kwh
            self.value_calculator.transfer_fee = grid_fee_sek_kwh  # Same as grid fee
            self.value_calculator.vat_rate = vat_rate
            self.value_calculator.effect_tariff = effect_tariff_sek_kw_month

        # Initialize battery state
        df['battery_soc_kwh'] = 0.0  # State of charge
        df['battery_charge_kwh'] = 0.0  # Energy charged this hour
        df['battery_discharge_kwh'] = 0.0  # Energy discharged this hour
        df['grid_import_kwh'] = 0.0  # Energy imported from grid
        df['grid_export_kwh'] = 0.0  # Energy exported to grid
        df['self_consumption_kwh'] = 0.0  # Solar used directly or from battery
        
        soc = self.capacity * 0.5  # Start at 50% charge
        plan_created_for_date = None  # Track when we last called GPT

        for idx in range(len(df)):
            # Send progress updates to frontend every 24 hours
            if idx % 24 == 0:
                progress_pct = (idx / len(df)) * 100
                days_done = idx // 24
                total_days = len(df) // 24
                self._send_progress(f"Simulating day {days_done}/{total_days}...", progress_pct)

            current_hour = df.loc[idx, 'timestamp'].hour
            current_date = df.loc[idx, 'timestamp'].date()

            # Create daily plan at 13:00 for tomorrow when using GPT
            if enable_arbitrage and self.use_gpt_arbitrage and self.gpt_agent:
                # Call GPT planner once per day at 13:00 to plan for tomorrow
                if current_hour == 13 and plan_created_for_date != current_date:
                    import datetime
                    tomorrow = current_date + datetime.timedelta(days=1)
                    print(f"\n📅 Creating daily plan for {tomorrow} at {current_hour}:00")
                    new_plan = self._create_daily_plan(df, idx, soc, grid_fee_sek_kwh,
                                                       energy_tax_sek_kwh, effect_tariff_sek_kw_month)
                    plan_created_for_date = current_date
                    if new_plan:
                        print(f"✅ Plan created with {len(new_plan)} hourly decisions for {tomorrow}")

            consumption = df.loc[idx, 'consumption_kwh']
            solar = df.loc[idx, 'solar_kwh']
            spot_price = df.loc[idx, 'spot_price_sek_kwh']

            # Debug: Print high consumption hours (disabled for performance)
            # if consumption > 8.0:
            #     print(f"DEBUG: Hour {idx}, consumption: {consumption:.2f} kW, solar: {solar:.2f} kW, SOC: {soc:.2f} kWh")

            # Net consumption (positive = need power, negative = excess solar)
            net = consumption - solar

            charge = 0
            discharge = 0

            # ========== BOSS AGENT SYSTEM PATH (RESERVE-BASED) ==========
            if enable_arbitrage and self.use_boss_agent and self.boss_agent:
                # Use Boss Agent (reserve-based) for decision making
                context = self._build_battery_context(df, idx, soc, grid_fee_sek_kwh,
                                                     energy_tax_sek_kwh, vat_rate)

                # Get Boss Agent decision
                boss_decision = self.boss_agent.analyze(context)

                if boss_decision:
                    decision = boss_decision
                    if decision.action == AgentAction.CHARGE:
                        charge_amount = min(
                            decision.kwh,
                            self.capacity - soc,
                            self.power
                        )
                        charge = charge_amount
                        discharge = 0
                        soc += charge * self.efficiency
                        grid_import = net + charge if net > 0 else charge
                        grid_export = 0 if net > 0 else 0
                        self_consumption = solar if net > 0 else solar

                        # DETAILED LOGGING: Track charging during E.ON measurement hours
                        current_hour = df.loc[idx, 'timestamp'].hour
                        if 6 <= current_hour <= 23:
                            print(f"\n⚠️  WARNING: CHARGING DURING E.ON HOURS!")
                            print(f"   Timestamp: {df.loc[idx, 'timestamp']}")
                            print(f"   Hour: {current_hour:02d}:00")
                            print(f"   SOC before: {soc - charge * self.efficiency:.1f} kWh")
                            print(f"   Charge amount: {charge:.2f} kWh")
                            print(f"   SOC after: {soc:.1f} kWh")
                            print(f"   Grid import: {grid_import:.2f} kW (includes charge)")
                            print(f"   Net consumption: {net:.2f} kW")
                            print(f"   Agent: {decision.chosen_agent}")
                            print(f"   Reasoning: {decision.reasoning}")
                            print(f"   Reserve: {decision.reserve_requirement.required_reserve_kwh:.1f} kWh")

                    elif decision.action == AgentAction.DISCHARGE:
                        discharge_amount = min(
                            decision.kwh,
                            soc,
                            self.power,
                            max(0, net)
                        )
                        discharge = discharge_amount
                        charge = 0
                        soc -= discharge

                        if discharge >= net:
                            grid_import = 0
                            grid_export = discharge - max(0, net)
                            self_consumption = solar + max(0, net)
                        else:
                            grid_import = max(0, net - discharge)
                            grid_export = 0
                            self_consumption = solar + discharge

                        # DETAILED LOGGING: Track discharging during high consumption
                        current_hour = df.loc[idx, 'timestamp'].hour
                        if 6 <= current_hour <= 23 and consumption > 15.0:
                            print(f"\n✅ DISCHARGE EVENT (E.ON hours, high consumption):")
                            print(f"   Timestamp: {df.loc[idx, 'timestamp']}")
                            print(f"   Consumption: {consumption:.2f} kW")
                            print(f"   Discharge: {discharge:.2f} kW")
                            print(f"   Grid import: {grid_import:.2f} kW (after discharge)")
                            print(f"   SOC: {soc:.1f} kWh (after discharge)")
                            print(f"   Agent: {decision.chosen_agent}")
                            print(f"   Reasoning: {decision.reasoning}")

                    elif decision.action == AgentAction.EXPORT:
                        discharge_amount = min(
                            decision.kwh,
                            soc,
                            self.power
                        )
                        discharge = discharge_amount
                        charge = 0
                        soc -= discharge
                        grid_import = max(0, net)
                        grid_export = discharge
                        self_consumption = solar

                    else:  # HOLD
                        if net > 0:
                            grid_import = net
                            grid_export = 0
                            self_consumption = solar
                        else:
                            grid_import = 0
                            grid_export = abs(net)
                            self_consumption = consumption

                        # DETAILED LOGGING: Track high consumption during E.ON hours
                        current_hour = df.loc[idx, 'timestamp'].hour
                        if 6 <= current_hour <= 23 and consumption > 15.0:
                            print(f"\n📊 HIGH CONSUMPTION EVENT (E.ON hours):")
                            print(f"   Timestamp: {df.loc[idx, 'timestamp']}")
                            print(f"   Consumption: {consumption:.2f} kW")
                            print(f"   Grid import: {grid_import:.2f} kW")
                            print(f"   SOC: {soc:.1f} kWh")
                            print(f"   Battery action: HOLD (no discharge)")
                            print(f"   Agent: {decision.chosen_agent}")
                            print(f"   Reasoning: {decision.reasoning}")

                else:
                    # No decision from Boss Agent - fallback
                    if net > 0:
                        grid_import = net
                        grid_export = 0
                        self_consumption = solar
                    else:
                        grid_import = 0
                        grid_export = abs(net)
                        self_consumption = consumption

            # ========== MULTI-AGENT SYSTEM PATH ==========
            elif enable_arbitrage and self.use_multi_agent and self.multi_agent_orchestrator:
                # Use multi-agent system for decision making
                context = self._build_battery_context(df, idx, soc, grid_fee_sek_kwh,
                                                     energy_tax_sek_kwh, vat_rate)

                # Get orchestrator decision
                decision = self.multi_agent_orchestrator.analyze(context)

                if decision:
                    if decision.action == AgentAction.CHARGE:
                        # Charge battery
                        charge_amount = min(
                            decision.kwh,
                            self.capacity - soc,
                            self.power
                        )
                        charge = charge_amount
                        discharge = 0
                        soc += charge * self.efficiency
                        grid_import = net + charge if net > 0 else charge
                        grid_export = 0 if net > 0 else 0
                        self_consumption = solar if net > 0 else solar

                    elif decision.action == AgentAction.DISCHARGE:
                        # Discharge battery
                        discharge_amount = min(
                            decision.kwh,
                            soc,
                            self.power,
                            max(0, net)  # Can't discharge more than consumption
                        )
                        discharge = discharge_amount
                        charge = 0
                        soc -= discharge

                        if discharge >= net:
                            # Discharged more than needed - export excess
                            grid_import = 0
                            grid_export = discharge - max(0, net)
                            self_consumption = solar + max(0, net)
                        else:
                            # Discharged less than needed - still import from grid
                            grid_import = max(0, net - discharge)
                            grid_export = 0
                            self_consumption = solar + discharge

                    elif decision.action == AgentAction.EXPORT:
                        # Export to grid (arbitrage opportunity)
                        discharge_amount = min(
                            decision.kwh,
                            soc,
                            self.power
                        )
                        discharge = discharge_amount
                        charge = 0
                        soc -= discharge
                        grid_import = max(0, net)
                        grid_export = discharge
                        self_consumption = solar

                    else:  # HOLD
                        # No action - normal operation
                        if net > 0:
                            grid_import = net
                            grid_export = 0
                            self_consumption = solar
                        else:
                            grid_import = 0
                            grid_export = abs(net)
                            self_consumption = consumption

                else:
                    # No decision from orchestrator - fallback to normal operation
                    if net > 0:
                        grid_import = net
                        grid_export = 0
                        self_consumption = solar
                    else:
                        grid_import = 0
                        grid_export = abs(net)
                        self_consumption = consumption

                # Update peak tracker with grid import AFTER battery action
                month_key = df.loc[idx, 'timestamp'].strftime('%Y-%m')
                self.peak_tracker.update(df.loc[idx, 'timestamp'], grid_import)

            # ========== GPT / RULE-BASED PATH (existing code) ==========
            elif net > 0:
                # Need to consume power
                current_hour = df.loc[idx, 'timestamp'].hour
                is_peak_hours = 6 <= current_hour <= 23
                is_night_hours = 0 <= current_hour <= 5

                # If GPT is enabled, check if we have a plan for today
                current_plan = self.daily_plans.get(current_date, {})

                # Debug: Show plan lookup for specific hours
                if enable_arbitrage and self.use_gpt_arbitrage and self.gpt_agent and current_hour in [17, 18] and current_date.day in [2, 3]:
                    has_plan = len(current_plan) > 0
                    print(f"🔍 Hour {current_hour}:00 on {current_date}: Looking for plan... Found: {has_plan}, Available dates: {list(self.daily_plans.keys())}")

                if enable_arbitrage and self.use_gpt_arbitrage and self.gpt_agent and current_plan:
                    # Get planned action for this hour
                    hour_of_day = current_hour
                    planned_action = current_plan.get(hour_of_day, {'action': 'hold', 'amount_kwh': 0})

                    if planned_action['action'] == 'charge':
                        # Plan says charge
                        charge_amount = min(
                            planned_action['amount_kwh'],
                            self.capacity - soc,
                            self.power
                        )
                        charge = charge_amount
                        discharge = 0
                        soc += charge * self.efficiency
                        grid_import = net + charge
                        grid_export = 0
                        self_consumption = solar

                    elif planned_action['action'] == 'discharge':
                        # Plan says discharge
                        discharge_amount = min(
                            planned_action['amount_kwh'],
                            soc,
                            self.power
                        )
                        discharge = discharge_amount
                        charge = 0
                        soc -= discharge
                        if discharge >= net:
                            grid_import = 0
                            grid_export = discharge - net
                            self_consumption = solar + net
                        else:
                            grid_import = net - discharge
                            grid_export = 0
                            self_consumption = solar + discharge

                        # Debug: Log discharge actions during peak hours
                        if current_hour in [17, 18] and current_date.day in [2, 3]:
                            print(f"⚡ Hour {current_hour}:00 on {current_date}: Planned discharge {planned_action['amount_kwh']:.2f} kW, SOC: {soc+discharge:.2f} kWh, Actual discharge: {discharge:.2f} kW, Consumption: {consumption:.2f} kW, Grid import: {grid_import:.2f} kW")

                    else:  # hold
                        # Plan says hold - just cover consumption minimally
                        available_discharge = min(soc, self.power, net)
                        discharge = available_discharge
                        charge = 0
                        soc -= discharge
                        grid_import = net - discharge
                        grid_export = 0
                        self_consumption = solar + discharge

                # PRIORITY 1: Smart peak shaving during E.ON peak hours (06:00-23:00)
                # Target: Reduce peaks to 5 kW to minimize effect tariff
                # Strategy: Don't eliminate peaks, just flatten them to target level
                # This saves battery for multiple peak events throughout the month!
                elif is_peak_hours and soc > 0:
                    TARGET_PEAK_KW = 5.0  # Target grid import level

                    # Calculate what grid import would be without battery
                    grid_import_without_battery = max(0, net)  # net = consumption - solar

                    # Only discharge if we're above target
                    if grid_import_without_battery > TARGET_PEAK_KW:
                        # Discharge just enough to reach target peak, not more!
                        needed_discharge = grid_import_without_battery - TARGET_PEAK_KW
                        available_discharge = min(soc, self.power, needed_discharge)
                        discharge = available_discharge
                        soc -= discharge

                        # Calculate final grid import after discharge
                        grid_import = grid_import_without_battery - discharge
                        grid_export = 0
                        self_consumption = solar + discharge
                    else:
                        # Already at or below target, no need to discharge
                        discharge = 0
                        grid_import = grid_import_without_battery
                        grid_export = 0
                        self_consumption = solar

                # PRIORITY 2: AGGRESSIVE night charging for peak shaving
                # Charge EVERY night to ensure battery is full for next day's peaks
                elif is_night_hours and soc < self.capacity * 0.95:
                    # ALWAYS charge at night, regardless of price!
                    # Cost of charging is worth it for peak shaving savings
                    target_soc = self.capacity * 0.95
                    charge_amount = min(
                        target_soc - soc,  # Space to target SOC
                        self.power,        # Max charge rate
                        self.capacity - soc  # Total available space
                    )
                    if charge_amount > 0:
                        charge = charge_amount
                        soc += charge * self.efficiency
                        # Still need to cover consumption from grid
                        grid_import = net + charge
                        discharge = 0
                        grid_export = 0
                        self_consumption = solar
                    else:
                        # Battery full, just cover consumption
                        available_discharge = min(soc, self.power, net)
                        discharge = available_discharge
                        soc -= discharge
                        grid_import = net - discharge
                        grid_export = 0
                        self_consumption = solar + discharge

                # PRIORITY 3: Normal consumption coverage (but conserve battery for peaks!)
                else:
                    # Only use battery for moderate loads (>3 kW) to preserve charge for peaks
                    if consumption > 3.0 and soc > self.capacity * 0.3:
                        # Use battery for moderate consumption, but keep at least 30% reserve
                        max_discharge = min(soc - self.capacity * 0.3, self.power, net)
                        discharge = max(0, max_discharge)
                        soc -= discharge
                        grid_import = net - discharge
                        grid_export = 0
                        self_consumption = solar + discharge
                    else:
                        # Low consumption - don't waste battery, import from grid
                        discharge = 0
                        grid_import = net
                        grid_export = 0
                        self_consumption = solar
                
            else:
                # Excess solar production
                excess = abs(net)
                self_consumption = consumption  # All consumption covered by solar
                
                # Charge battery with excess
                charge_capacity = min(
                    self.capacity - soc,  # Available space
                    self.power,  # Max charge rate
                    excess  # Available excess solar
                )
                charge = charge_capacity
                soc += charge * self.efficiency  # Account for charging losses

                # Export remaining excess to grid
                grid_export = excess - charge
                grid_import = 0  # No grid import when we have excess solar

            # OLD GPT CODE REMOVED - Now using daily planning instead
            # GPT creates a 24-hour plan once per day at 13:00-14:00

            # Fallback to rule-based arbitrage if GPT and multi-agent are not enabled
            if enable_arbitrage and not self.use_gpt_arbitrage and not self.use_multi_agent:
                # Enhanced rule-based arbitrage with aggressive peak shaving
                current_hour = df.loc[idx, 'timestamp'].hour
                is_peak_hours = 6 <= current_hour <= 23
                
                # PRIORITY 1: Peak shaving during peak hours (06:00-23:00)
                if is_peak_hours and consumption > 5.0 and soc > self.capacity * 0.1:
                    # Aggressive peak shaving - discharge to keep consumption under 5 kW
                    target_consumption = 5.0
                    needed_discharge = max(0, consumption - target_consumption)
                    discharge_amount = min(soc - self.capacity * 0.05, self.power, needed_discharge)
                    if discharge_amount > 0:
                        discharge += discharge_amount
                        soc -= discharge_amount
                        grid_export += discharge_amount
                        print(f"PEAK SHAVING: {consumption:.2f} kW -> {consumption-discharge_amount:.2f} kW (discharge {discharge_amount:.2f} kWh)")
                
                # PRIORITY 2: Charge during night hours for next day's peaks
                elif not is_peak_hours and soc < self.capacity * 0.95:
                    if spot_price < 0.5:  # Very cheap night prices
                        charge_amount = min((self.capacity * 0.95 - soc) / self.efficiency, self.power)
                        if charge_amount > 0:
                            charge += charge_amount
                            soc += charge_amount * self.efficiency
                            grid_import += charge_amount
                            print(f"NIGHT CHARGING: SOC {soc-charge_amount*self.efficiency:.1f} kWh -> {soc:.1f} kWh (price: {spot_price:.3f})")
                    elif spot_price < 0.8:  # Moderately cheap
                        charge_amount = min((self.capacity * 0.8 - soc) / self.efficiency, self.power * 0.7)
                        if charge_amount > 0:
                            charge += charge_amount
                            soc += charge_amount * self.efficiency
                            grid_import += charge_amount
                
                # PRIORITY 3: Arbitrage opportunities (only if no peak shaving needed)
                elif not is_peak_hours and spot_price < 0.3 and soc < self.capacity * 0.8:
                    # Very cheap - charge for arbitrage
                    charge_amount = min((self.capacity * 0.8 - soc) / self.efficiency, self.power)
                    if charge_amount > 0:
                        charge += charge_amount
                        soc += charge_amount * self.efficiency
                        grid_import += charge_amount
                elif not is_peak_hours and spot_price > 2.0 and soc > self.capacity * 0.2:
                    # Very expensive - discharge for arbitrage
                    discharge_amount = min(soc - self.capacity * 0.05, self.power)
                    if discharge_amount > 0:
                        discharge += discharge_amount
                        soc -= discharge_amount
                        grid_export += discharge_amount
            
            # Record state
            df.loc[idx, 'battery_soc_kwh'] = soc
            df.loc[idx, 'battery_charge_kwh'] = charge
            df.loc[idx, 'battery_discharge_kwh'] = discharge
            df.loc[idx, 'grid_import_kwh'] = grid_import
            df.loc[idx, 'grid_export_kwh'] = grid_export
            df.loc[idx, 'self_consumption_kwh'] = self_consumption

            # Daily summary reporting (every 24 hours)
            if (idx + 1) % 24 == 0:
                day_start = idx - 23
                day_df = df.loc[day_start:idx]
                day_date = day_df.iloc[0]['timestamp'].date()

                # Calculate daily metrics
                daily_consumption = day_df['consumption_kwh'].sum()
                daily_solar = day_df['solar_kwh'].sum()
                daily_battery_discharge = day_df['battery_discharge_kwh'].sum()
                daily_battery_charge = day_df['battery_charge_kwh'].sum()
                daily_grid_import = day_df['grid_import_kwh'].sum()
                daily_self_consumption = day_df['self_consumption_kwh'].sum()

                # Peak shaving metrics
                eon_hours_day = day_df[(day_df['timestamp'].dt.hour >= 6) & (day_df['timestamp'].dt.hour <= 23)]
                daily_peak_without = eon_hours_day['consumption_kwh'].max()
                daily_peak_with = eon_hours_day['grid_import_kwh'].max()
                daily_peak_reduction = daily_peak_without - daily_peak_with

                # Print daily summary
                print(f"\n📊 Day {day_date} Summary:")
                print(f"  ⚡ Consumption: {daily_consumption:.1f} kWh | Solar: {daily_solar:.1f} kWh | Self-consumption: {daily_self_consumption:.1f} kWh")
                print(f"  🔋 Battery: Charged {daily_battery_charge:.1f} kWh | Discharged {daily_battery_discharge:.1f} kWh | SOC: {soc:.1f} kWh")
                print(f"  📈 Peak (06-23): Without battery {daily_peak_without:.1f} kW → With battery {daily_peak_with:.1f} kW (↓{daily_peak_reduction:.1f} kW)")
                print(f"  🏠 Grid import: {daily_grid_import:.1f} kWh")

        # Calculate costs with battery
        df['spot_cost_import'] = df['grid_import_kwh'] * df['spot_price_sek_kwh']

        # Export revenue: spot price minus transfer fee (same as import grid fee)
        # User configures grid_fee_sek_kwh in frontend
        df['spot_revenue_export'] = df['grid_export_kwh'] * (df['spot_price_sek_kwh'] - grid_fee_sek_kwh)
        # Don't export at a loss if spot price < transfer fee
        df['spot_revenue_export'] = df['spot_revenue_export'].clip(lower=0)

        df['grid_fee_cost'] = df['grid_import_kwh'] * grid_fee_sek_kwh
        df['energy_tax_cost'] = df['grid_import_kwh'] * energy_tax_sek_kwh
        
        df['net_cost_hour'] = (df['spot_cost_import'] + df['grid_fee_cost'] + 
                               df['energy_tax_cost'] - df['spot_revenue_export'])
        df['total_cost_with_vat'] = df['net_cost_hour'] * (1 + vat_rate)
        
        # Calculate effect tariff savings (based on monthly peak reduction)
        effect_savings = 0
        if effect_tariff_sek_kw_month > 0:
            # Group by month and find peak power per month
            df['month'] = df['timestamp'].dt.to_period('M')
            df['hour'] = df['timestamp'].dt.hour

            # E.ON measures peaks only during 06:00-23:00, so filter to those hours
            eon_hours = df[(df['hour'] >= 6) & (df['hour'] <= 23)]

            # Calculate monthly peaks during E.ON hours only - method depends on grid owner
            if effect_tariff_method == 'top3_average':
                # E.ON method: Average of top 3 peaks per month
                def get_top3_average(series):
                    top3 = series.nlargest(3)
                    return top3.mean() if len(top3) > 0 else 0

                monthly_peaks_without = eon_hours.groupby('month')['consumption_kwh'].apply(get_top3_average)
                monthly_peaks_with = eon_hours.groupby('month')['grid_import_kwh'].apply(get_top3_average)
                print(f"Effect tariff calculation method: Top 3 peaks average (E.ON)")
            else:
                # Default method: Single highest peak per month
                monthly_peaks_without = eon_hours.groupby('month')['consumption_kwh'].max()
                monthly_peaks_with = eon_hours.groupby('month')['grid_import_kwh'].max()
                print(f"Effect tariff calculation method: Single highest peak")

            # Calculate peak reduction per month
            monthly_peak_reductions = []
            for month in monthly_peaks_without.index:
                peak_without = monthly_peaks_without[month]
                peak_with = monthly_peaks_with[month]

                peak_reduction = peak_without - peak_with
                monthly_peak_reductions.append(max(0, peak_reduction))
                print(f"  Month {month}: Peak WITHOUT battery: {peak_without:.2f} kW, WITH battery: {peak_with:.2f} kW, Reduction: {peak_reduction:.2f} kW")

            # Calculate annual savings
            avg_monthly_reduction = sum(monthly_peak_reductions) / len(monthly_peak_reductions)
            effect_savings = avg_monthly_reduction * effect_tariff_sek_kw_month * 12

            print(f"  Average monthly peak reduction: {avg_monthly_reduction:.2f} kW")
            print(f"  Monthly tariff: {effect_tariff_sek_kw_month} SEK/kW")
            print(f"  Annual savings: {effect_savings:.0f} SEK")
        
        # Summary statistics
        total_cost_with_battery = df['total_cost_with_vat'].sum()
        total_export_revenue = df['spot_revenue_export'].sum() * (1 + vat_rate)
        total_self_consumption = df['self_consumption_kwh'].sum()
        
        results = {
            'total_cost_sek': total_cost_with_battery,
            'export_revenue_sek': total_export_revenue,
            'net_cost_sek': total_cost_with_battery - total_export_revenue,
            'total_self_consumption_kwh': total_self_consumption,
            'self_consumption_rate': total_self_consumption / df['consumption_kwh'].sum(),
            'effect_tariff_savings_sek': effect_savings,
            'peak_import_without_battery_kw': monthly_peaks_without.max() if effect_tariff_sek_kw_month > 0 else df['consumption_kwh'].max(),
            'peak_import_with_battery_kw': monthly_peaks_with.max() if effect_tariff_sek_kw_month > 0 else df['grid_import_kwh'].max()
        }

        # Add multi-agent performance metrics if enabled
        if self.use_multi_agent and self.multi_agent_orchestrator:
            agent_metrics = self.multi_agent_orchestrator.get_performance_metrics()
            results['multi_agent_metrics'] = agent_metrics
            print(f"\n🤖 Multi-Agent Performance:")
            print(f"  Total decisions: {agent_metrics['decisions_count']}")
            print(f"  Conflicts resolved: {agent_metrics['conflicts_resolved']}")
            print(f"  Vetos applied: {agent_metrics['vetos_applied']}")
            for agent_name, metrics in agent_metrics.get('agent_performance', {}).items():
                if metrics['recommendations_count'] > 0:
                    print(f"  {agent_name}: {metrics['recommendations_count']} recommendations, {metrics['total_value_sek']:.0f} SEK total value")
        
        # Debug: Print arbitrage statistics
        if enable_arbitrage and hasattr(self, '_arbitrage_stats'):
            stats = self._arbitrage_stats
            print(f"Arbitrage Debug Stats:")
            print(f"  Charge decisions: {stats['charge_decisions']} times, {stats['total_charge_kwh']:.1f} kWh total")
            print(f"  Discharge decisions: {stats['discharge_decisions']} times, {stats['total_discharge_kwh']:.1f} kWh total")
            print(f"  Net arbitrage energy: {stats['total_discharge_kwh'] - stats['total_charge_kwh']:.1f} kWh")
        
        return df, results
    
    def _prepare_gpt_context(self, df: pd.DataFrame, current_idx: int, current_soc: float,
                            current_price: float, solar: float, consumption: float,
                            grid_fee_sek_kwh: float, energy_tax_sek_kwh: float, 
                            effect_tariff_sek_kw_month: float = 0) -> Dict:
        """
        Prepare context data for GPT arbitrage agent
        """
        # Get current timestamp
        current_time = df.loc[current_idx, 'timestamp']
        
        # Calculate SOC percentage
        soc_percent = (current_soc / self.capacity) * 100
        
        # Get price history (last 24 hours)
        start_idx = max(0, current_idx - 24)
        price_history = df.loc[start_idx:current_idx, ['timestamp', 'spot_price_sek_kwh']].tail(24)
        price_history_str = "\n".join([
            f"{row['timestamp']}: {row['spot_price_sek_kwh']:.3f} SEK/kWh" 
            for _, row in price_history.iterrows()
        ])
        
        # Get 24-HOUR FORECAST (next 24 hours) - CRITICAL FOR STRATEGIC PLANNING
        end_idx = min(len(df) - 1, current_idx + 24)
        
        # Price forecast with peak hour indicators
        price_forecast = df.loc[current_idx:end_idx, ['timestamp', 'spot_price_sek_kwh']].head(24)
        price_forecast_str = "\n".join([
            f"{row['timestamp']}: {row['spot_price_sek_kwh']:.3f} SEK/kWh (peak: {6 <= row['timestamp'].hour <= 23})" 
            for _, row in price_forecast.iterrows()
        ])
        
        # Consumption forecast with peak hour indicators
        consumption_forecast = df.loc[current_idx:end_idx, ['timestamp', 'consumption_kwh']].head(24)
        consumption_forecast_str = "\n".join([
            f"{row['timestamp']}: {row['consumption_kwh']:.2f} kW (peak: {6 <= row['timestamp'].hour <= 23})" 
            for _, row in consumption_forecast.iterrows()
        ])
        
        # Solar forecast
        solar_forecast = df.loc[current_idx:end_idx, ['timestamp', 'solar_kwh']].head(24)
        solar_forecast_str = "\n".join([
            f"{row['timestamp']}: {row['solar_kwh']:.2f} kWh" 
            for _, row in solar_forecast.iterrows()
        ])
        
        # Get consumption pattern (last 24 hours)
        consumption_pattern = df.loc[start_idx:current_idx, ['timestamp', 'consumption_kwh']].tail(24)
        consumption_pattern_str = "\n".join([
            f"{row['timestamp']}: {row['consumption_kwh']:.2f} kWh" 
            for _, row in consumption_pattern.iterrows()
        ])
        
        # Analyze peak consumption patterns (06:00-23:00 only)
        current_hour = df.loc[current_idx, 'timestamp'].hour
        is_peak_hours = 6 <= current_hour <= 23
        
        # Find historical peaks in same time period
        historical_peaks = []
        for i in range(max(0, current_idx - 168), current_idx):  # Last 7 days
            hist_hour = df.loc[i, 'timestamp'].hour
            if 6 <= hist_hour <= 23:  # Only peak hours
                hist_consumption = df.loc[i, 'consumption_kwh']
                if hist_consumption > 8.0:  # High consumption
                    historical_peaks.append(f"{df.loc[i, 'timestamp']}: {hist_consumption:.2f} kW")
        
        peak_pattern_str = "\n".join(historical_peaks[-10:]) if historical_peaks else "No historical peaks found"

        return {
            'current_time': current_time,
            'current_price': current_price,
            'soc': current_soc,
            'soc_percent': soc_percent,
            'solar': solar,
            'consumption': consumption,
            'battery_capacity': self.capacity,
            'battery_power': self.power,
            'efficiency': self.efficiency,
            'grid_fee': grid_fee_sek_kwh,
            'energy_tax': energy_tax_sek_kwh,
            'transfer_fee': grid_fee_sek_kwh,  # Same as grid fee (user configurable)
            'effect_tariff_sek_kw_month': effect_tariff_sek_kw_month,
            'price_history': price_history_str,
            'price_forecast': price_forecast_str,
            'consumption_forecast': consumption_forecast_str,
            'solar_forecast': solar_forecast_str,
            'consumption_pattern': consumption_pattern_str,
            'is_peak_hours': is_peak_hours,
            'current_hour': current_hour,
            'historical_peaks': peak_pattern_str
        }

    def _calculate_peak_shaving_charge(self, df: pd.DataFrame, current_idx: int, 
                                     current_consumption: float, current_soc: float) -> float:
        """
        Calculate if we need to charge battery for peak shaving
        """
        # Look ahead 6 hours to see if high consumption is coming
        lookahead_hours = 6
        end_idx = min(len(df) - 1, current_idx + lookahead_hours)
        
        if end_idx <= current_idx:
            return 0
        
        # Check future consumption
        future_consumption = df.loc[current_idx:end_idx, 'consumption_kwh'].max()
        
        # If future consumption is high (>7 kW) and we have low SOC, charge for peak shaving
        if future_consumption > 7.0 and current_soc < self.capacity * 0.6:
            # Charge up to 80% SOC for peak shaving
            target_soc = self.capacity * 0.8
            needed_charge = target_soc - current_soc
            
            # Charge if price is reasonable (<1.0 SEK/kWh) or we have excess solar
            current_price = df.loc[current_idx, 'spot_price_sek_kwh']
            current_solar = df.loc[current_idx, 'solar_kwh']
            
            # More aggressive charging for peak shaving
            if current_price < 1.0 or current_solar > 0:
                return min(needed_charge, self.power)
        
        return 0

    def _analyze_arbitrage_opportunity(self, df: pd.DataFrame, current_idx: int, current_soc: float, 
                                     current_price: float, grid_fee_sek_kwh: float, energy_tax_sek_kwh: float) -> Dict:
        """
        Analyze arbitrage opportunity over next 24 hours of known prices
        """
        # Look at next 24 hours (or remaining hours in dataset)
        lookahead_hours = min(24, len(df) - current_idx - 1)
        if lookahead_hours <= 0:
            return {'action': 'none', 'max_charge_kwh': 0, 'max_discharge_kwh': 0}
        
        # Get prices for next 24 hours
        future_prices = df.loc[current_idx + 1:current_idx + lookahead_hours, 'spot_price_sek_kwh'].values
        
        # Calculate total cost to buy electricity (spot + fees + taxes)
        total_buy_cost = current_price + grid_fee_sek_kwh + energy_tax_sek_kwh

        # Calculate net revenue from selling (spot - transfer_fee)
        net_sell_revenue = max(0, current_price - grid_fee_sek_kwh)

        # Find best arbitrage opportunities
        best_charge_windows = []
        best_discharge_windows = []

        # Look for charging opportunities (buy low)
        for i, future_price in enumerate(future_prices):
            future_total_cost = future_price + grid_fee_sek_kwh + energy_tax_sek_kwh

            # Charge if future price is significantly lower (minimum 0.2 SEK/kWh difference)
            price_difference = total_buy_cost - future_total_cost
            if price_difference > 0.2:  # Minimum 0.2 SEK/kWh profit margin
                best_charge_windows.append({
                    'hour_offset': i + 1,
                    'price': future_price,
                    'total_cost': future_total_cost,
                    'profit_margin': price_difference
                })

        # Look for discharging opportunities (sell high)
        for i, future_price in enumerate(future_prices):
            future_net_revenue = max(0, future_price - grid_fee_sek_kwh)
            
            # Discharge if future price is significantly higher (minimum 0.2 SEK/kWh difference)
            price_difference = future_net_revenue - net_sell_revenue
            if price_difference > 0.2:  # Minimum 0.2 SEK/kWh profit margin
                best_discharge_windows.append({
                    'hour_offset': i + 1,
                    'price': future_price,
                    'net_revenue': future_net_revenue,
                    'profit_margin': price_difference
                })
        
        # Sort by profit margin (highest first)
        best_charge_windows.sort(key=lambda x: x['profit_margin'], reverse=True)
        best_discharge_windows.sort(key=lambda x: x['profit_margin'], reverse=True)
        
        # Decision logic
        action = 'none'
        max_charge_kwh = 0
        max_discharge_kwh = 0
        
        # PRIORITY 1: Peak shaving logic (highest priority)
        current_hour = df.loc[current_idx, 'timestamp'].hour
        is_peak_hours = 6 <= current_hour <= 23
        
        # Get current consumption for peak shaving
        current_consumption = df.loc[current_idx, 'consumption_kwh']
        
        if is_peak_hours and current_consumption > 6.0 and current_soc > self.capacity * 0.1:
            # Aggressive peak shaving during peak hours
            target_consumption = 6.0
            needed_discharge = max(0, current_consumption - target_consumption)
            max_discharge_kwh = min(current_soc - self.capacity * 0.05, self.power, needed_discharge)
            if max_discharge_kwh > 0:
                action = 'discharge'
                print(f"PEAK SHAVING: {current_consumption:.2f} kW -> {current_consumption-max_discharge_kwh:.2f} kW (discharge {max_discharge_kwh:.2f} kWh)")
        
        # PRIORITY 2: Night charging for next day's peaks
        elif not is_peak_hours and current_soc < self.capacity * 0.9:
            if current_price < 0.6:  # Very cheap night prices
                max_charge_kwh = min((self.capacity * 0.95 - current_soc) / self.efficiency, self.power)
                action = 'charge'
                print(f"NIGHT CHARGING: SOC {current_soc:.1f} kWh -> {current_soc+max_charge_kwh:.1f} kWh (price: {current_price:.3f})")
            elif current_price < 0.8:  # Moderately cheap
                max_charge_kwh = min((self.capacity * 0.8 - current_soc) / self.efficiency, self.power * 0.7)
                action = 'charge'
        
        # PRIORITY 3: Smart AI arbitrage logic for extreme price volatility (only if no peak shaving needed)
        if action == 'none' and best_charge_windows and current_soc < self.capacity * 0.95:
            best_charge_margin = best_charge_windows[0]['profit_margin']
            
            # Be aggressive with charging when prices are very low or negative
            if best_charge_margin > 1.0:  # Very profitable (>1 SEK/kWh profit)
                action = 'charge'
                max_charge_kwh = min(
                    (self.capacity * 0.95 - current_soc) / self.efficiency,
                    self.power * 6  # Charge for up to 6 hours
                )
            elif best_charge_margin > 0.5:  # Moderately profitable
                action = 'charge'
                max_charge_kwh = min(
                    (self.capacity * 0.8 - current_soc) / self.efficiency,
                    self.power * 4  # Charge for up to 4 hours
                )
            elif best_charge_margin > 0.2:  # Small profit
                action = 'charge'
                max_charge_kwh = min(
                    (self.capacity * 0.6 - current_soc) / self.efficiency,
                    self.power * 2  # Charge for up to 2 hours
                )
        
        # Smart discharging logic (only if no peak shaving needed)
        if action == 'none' and best_discharge_windows and current_soc > self.capacity * 0.05:
            best_discharge_margin = best_discharge_windows[0]['profit_margin']
            
            # Be aggressive with discharging when prices are very high
            if best_discharge_margin > 2.0:  # Very profitable (>2 SEK/kWh profit)
                action = 'discharge'
                max_discharge_kwh = min(
                    current_soc - self.capacity * 0.05,
                    self.power * 6  # Discharge for up to 6 hours
                )
            elif best_discharge_margin > 1.0:  # Moderately profitable
                action = 'discharge'
                max_discharge_kwh = min(
                    current_soc - self.capacity * 0.1,
                    self.power * 4  # Discharge for up to 4 hours
                )
            elif best_discharge_margin > 0.5:  # Small profit
                action = 'discharge'
                max_discharge_kwh = min(
                    current_soc - self.capacity * 0.2,
                    self.power * 2  # Discharge for up to 2 hours
                )
        
        return {
            'action': action,
            'max_charge_kwh': max_charge_kwh,
            'max_discharge_kwh': max_discharge_kwh,
            'charge_opportunities': len(best_charge_windows),
            'discharge_opportunities': len(best_discharge_windows)
        }
    
    def calculate_roi(self, cost_without_battery: float, cost_with_battery: float,
                     effect_savings: float, stodtjanster_revenue: float = 0) -> Dict:
        """
        Calculate ROI metrics for battery investment with degradation
        """
        # Calculate NPV with 3% discount rate and battery degradation
        discount_rate = 0.03
        npv = -self.cost
        total_savings_lifetime = 0
        
        for year in range(1, self.lifetime + 1):
            # Battery degradation: 100% -> 95% -> 90% -> 85% -> 80% -> 75% -> 70%
            if year <= 5:
                degradation_factor = 1.0
            elif year <= 10:
                degradation_factor = 1.0 - (year - 5) * 0.01  # 1% per year
            else:
                degradation_factor = 0.95 - (year - 10) * 0.02  # 2% per year after year 10
            
            # Degradation reduces savings (battery can't store as much energy)
            annual_savings_degraded = (cost_without_battery - cost_with_battery + effect_savings + stodtjanster_revenue) * degradation_factor
            
            npv += annual_savings_degraded / ((1 + discount_rate) ** year)
            total_savings_lifetime += annual_savings_degraded
        
        # Use first year savings for payback calculation (before degradation)
        annual_savings = cost_without_battery - cost_with_battery + effect_savings + stodtjanster_revenue
        payback_years = self.cost / annual_savings if annual_savings > 0 else float('inf')
        
        roi_percentage = ((total_savings_lifetime - self.cost) / self.cost) * 100
        
        return {
            'battery_cost_sek': self.cost,
            'annual_savings_sek': annual_savings,
            'payback_period_years': payback_years,
            'lifetime_years': self.lifetime,
            'total_lifetime_savings_sek': total_savings_lifetime,
            'net_profit_sek': total_savings_lifetime - self.cost,
            'roi_percentage': roi_percentage,
            'npv_sek': npv,
            'profitable': bool(npv > 0)
        }
    
    def generate_report(self, df: pd.DataFrame, cost_without: Dict, 
                       results_with: Dict, roi: Dict) -> Dict:
        """
        Generate comprehensive analysis report
        """
        # Monthly aggregations
        df['month'] = df['timestamp'].dt.to_period('M')
        monthly = df.groupby('month').agg({
            'consumption_kwh': 'sum',
            'solar_kwh': 'sum',
            'grid_import_kwh': 'sum',
            'grid_export_kwh': 'sum',
            'self_consumption_kwh': 'sum',
            'total_cost_with_vat': 'sum'
        }).reset_index()
        monthly['month'] = monthly['month'].astype(str)
        
        # Convert any numpy types to Python native types for JSON serialization
        for col in monthly.columns:
            if monthly[col].dtype == 'object':
                continue
            monthly[col] = monthly[col].astype(float)
        
        report = {
            'summary': {
                'without_battery': cost_without,
                'with_battery': results_with,
                'roi': roi
            },
            'monthly_data': monthly.to_dict('records'),
            'savings_breakdown': {
                'spot_price_savings_sek': cost_without['total_cost_sek'] - results_with['net_cost_sek'],
                'effect_tariff_savings_sek': results_with.get('effect_tariff_savings_sek', 0),
                'export_revenue_sek': results_with.get('export_revenue_sek', 0),
                'total_annual_savings_sek': roi['annual_savings_sek']
            }
        }
        
        return report


def main():
    """
    Example usage of the battery simulator
    """
    # Example configuration
    simulator = BatteryROISimulator(
        battery_capacity_kwh=10,
        battery_power_kw=5,
        battery_efficiency=0.95,
        battery_cost_sek=80000,
        battery_lifetime_years=15
    )
    
    print("Battery ROI Simulator for Swedish Market")
    print("=" * 50)
    print(f"Battery Configuration:")
    print(f"  Capacity: {simulator.capacity} kWh")
    print(f"  Power: {simulator.power} kW")
    print(f"  Efficiency: {simulator.efficiency * 100}%")
    print(f"  Cost: {simulator.cost:,.0f} SEK")
    print(f"  Lifetime: {simulator.lifetime} years")
    print()
    print("Ready to process Tibber CSV data...")


if __name__ == "__main__":
    main()
