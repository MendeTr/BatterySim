# Agent Tuning Guide

## Problem: Multi-Agent Creating New Peaks Instead of Reducing Them

**Observed Issue (February 2025):**
- Multi-Agent: Peak 8.43 kW → 8.90 kW (WORSE! -0.48 kW reduction)
- Rule-Based: Peak 8.43 kW → 5.00 kW (GOOD! +3.43 kW reduction)

**Root Cause:**
The Arbitrage Agent charges too aggressively during E.ON measurement hours (06:00-23:00), creating new peaks. Example:
- Feb 22: Charged 32.2 kWh, created 8.7 kW peak
- Feb 14: Peak went from 4.9 kW → 9.7 kW

---

## Fix 1: Stop Arbitrage Agent from Charging During Peak Hours

**Current Code** [agents/arbitrage_agent.py:90](agents/arbitrage_agent.py:90):
```python
def _analyze_charging(self, context):
    # Should we charge?
    if current_price >= self.night_charge_threshold:  # 0.70 SEK/kWh
        return None  # Too expensive

    # Charges even during 06:00-23:00!
```

**Fix:**
```python
def _analyze_charging(self, context):
    current_price = context.spot_price_sek_kwh
    hour = context.hour

    # CRITICAL: Never charge during E.ON measurement hours (06:00-23:00)
    # This creates peaks that cost 60 SEK/kW/month!
    if context.is_measurement_hour:
        return None  # Don't charge during peak tariff hours

    # Only charge during night (00:00-05:59)
    if current_price >= self.night_charge_threshold:
        return None  # Too expensive

    # ... rest of charging logic
```

---

## Fix 2: Increase Peak Shaving Agent Priority

**Current Priority System** [agents/base_agent.py:18](agents/base_agent.py:18):
```python
priority: int  # 1=critical, 2=high, 3=medium, 4=low
```

**Peak Shaving Agent** [agents/peak_shaving_agent.py:105]:
```python
priority = 1 if potential_peak_kw > threshold_kw * 1.1 else 2
```

**Arbitrage Agent** [agents/arbitrage_agent.py:170]:
```python
if current_price > 2.50:
    priority = 2  # High value hour
elif current_price > 1.50:
    priority = 3  # Medium value hour
else:
    priority = 4  # Low priority
```

**Problem:** Arbitrage at priority=3 can override peak shaving at priority=2

**Fix:** Boost peak shaving priority:
```python
# In PeakShavingAgent.analyze()
if potential_peak_kw > threshold_kw:
    priority = 1  # CRITICAL - in top 3 peaks
elif potential_peak_kw > threshold_kw * 0.9:
    priority = 1  # CRITICAL - approaching threshold
else:
    priority = 2  # HIGH - preventive action
```

---

## Fix 3: Reserve Battery Capacity for Peak Shaving

**Add to Arbitrage Agent** [agents/arbitrage_agent.py:90]:
```python
def _analyze_charging(self, context):
    # ... existing checks ...

    # Check if peak shaving agent needs capacity
    # Ask orchestrator for reserved capacity
    reserved_capacity = 10.0  # kWh - reserve for potential peaks

    # How much room do we have?
    target_soc = context.target_morning_soc_kwh - reserved_capacity
    room_to_charge = target_soc - context.soc_kwh

    if room_to_charge < 1.0:
        return None  # Leave room for peak shaving
```

---

## Fix 4: Add Peak Awareness to Self-Consumption Logic

**Current** [agents/arbitrage_agent.py:145]:
```python
def _analyze_self_consumption(self, context):
    # Discharge to cover consumption
    discharge_kwh = min(
        context.consumption_kw,
        available_discharge,
        context.max_discharge_kw
    )
```

**Problem:** Discharges even when creating peaks!

**Fix:**
```python
def _analyze_self_consumption(self, context):
    # If we're already at low grid import, don't discharge more
    # (it won't help peaks and wastes battery)
    if context.grid_import_kw < 2.0:  # Already very low
        return None

    # Calculate discharge needed
    discharge_kwh = min(
        context.consumption_kw,
        available_discharge,
        context.max_discharge_kw
    )

    # If discharging would create a peak, reduce amount
    if context.is_measurement_hour:
        # Check if this would be a new peak
        grid_import_after = context.grid_import_kw - discharge_kwh
        if grid_import_after > context.peak_threshold_kw * 0.8:
            # Reduce discharge to stay below threshold
            safe_discharge = context.grid_import_kw - (context.peak_threshold_kw * 0.75)
            discharge_kwh = max(0, safe_discharge)
```

---

## Recommended Parameter Changes

### Arbitrage Agent Initialization [battery_simulator.py:315](battery_simulator.py:315):

**Current:**
```python
arbitrage_agent = ArbitrageAgent(
    value_calculator=self.value_calculator,
    min_arbitrage_profit_sek=5.0,
    min_export_spot_price=3.0,
    night_charge_threshold=0.70  # ← TOO HIGH!
)
```

**Recommended:**
```python
arbitrage_agent = ArbitrageAgent(
    value_calculator=self.value_calculator,
    min_arbitrage_profit_sek=10.0,  # Higher bar for profit
    min_export_spot_price=3.5,      # Only export at very high prices
    night_charge_threshold=0.50      # Only charge when VERY cheap
)
```

### Peak Shaving Agent [battery_simulator.py:308](battery_simulator.py:308):

**Current:**
```python
peak_agent = PeakShavingAgent(
    peak_tracker=self.peak_tracker,
    value_calculator=self.value_calculator,
    target_peak_kw=5.0,
    aggressive_threshold_multiplier=0.9
)
```

**Recommended:**
```python
peak_agent = PeakShavingAgent(
    peak_tracker=self.peak_tracker,
    value_calculator=self.value_calculator,
    target_peak_kw=5.0,
    aggressive_threshold_multiplier=0.85  # Act earlier (85% of threshold)
)
```

### Real-Time Override [battery_simulator.py:303](battery_simulator.py:303):

**Current:**
```python
override_agent = RealTimeOverrideAgent(
    spike_threshold_kw=10.0,  # ← TOO HIGH!
    critical_peak_margin_kw=1.0
)
```

**Recommended:**
```python
override_agent = RealTimeOverrideAgent(
    spike_threshold_kw=7.0,   # Lower threshold (your Feb peaks were 7-11 kW)
    critical_peak_margin_kw=0.5  # Tighter margin
)
```

---

## Testing the Fixes

After applying fixes, re-run the test:
```bash
python test_multi_agent_simulation.py
```

**Expected Results:**
- Peak reduction: Should be positive (> 2 kW)
- Top 3 peaks average: Should be < 6 kW
- Peak shaving savings: Should be > 2,000 SEK/year

---

## Quick Fix Script

Want me to apply all these fixes automatically? I can:
1. Update ArbitrageAgent to not charge during peak hours
2. Adjust all agent parameters
3. Add capacity reservation logic
4. Re-run the test

Just say "apply fixes" and I'll do it!
