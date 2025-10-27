# Critical Issue Analysis - Why Multi-Agent Creates Peaks

## Problem
Multi-Agent creates peaks (8.43 → 8.90 kW) while Rule-Based successfully reduces them (8.43 → 5.00 kW).

## Root Cause Identified

The issue is **NOT** that battery charges during peak hours (06:00-23:00). My fix prevents that.

The REAL problem is:

### **The Battery Fills Up Too Much at Night**

1. **Night (00:00-05:59):** Arbitrage Agent sees cheap prices (0.40-0.60 SEK)
2. **Arbitrage Agent recommends:** CHARGE to target_morning_soc (20 kWh)
3. **Battery charges:** 10-15 kWh during night
4. **Morning (06:00-08:00):** Consumption starts (coffee, lights, etc.)
5. **Peak Shaving Agent wants to help:** But battery is FULL or near-full!
6. **Result:** Can't discharge enough to reduce morning peaks

### **Why Rule-Based Works Better**

Rule-based system:
- Only charges at VERY cheap prices (< 0.50 SEK)
- Charges to 95% max (leaves room)
- **Aggressively** discharges during ANY consumption > 5 kW
- Keeps battery ready for peaks

Multi-agent system:
- Charges whenever < 0.50 SEK (after my fix)
- Fills to 80% target (20 kWh)
- Only discharges when approaching threshold
- **Too conservative** - waits until peak is already happening!

## Solutions

### Option 1: Make Peak Shaving Agent More Aggressive ✅ RECOMMENDED

```python
# In PeakShavingAgent.analyze()
# Current: Only act if potential_peak > threshold
# Fix: Act EARLIER, be more preventive

if potential_peak_kw > threshold_kw * 0.7:  # Act at 70% of threshold
    # Discharge preventively
```

### Option 2: Reduce Night Charging Target

```python
# In _build_battery_context()
target_morning_soc_kwh=self.capacity * 0.60  # Only 60% (15 kWh)
# Leaves 10 kWh capacity for peak shaving
```

### Option 3: Reserve Capacity for Peak Shaving

```python
# In ArbitrageAgent._analyze_charging()
# Before charging, check how much capacity peak shaving might need
reserved_for_peaks = 10.0  # kWh
target_soc = context.target_morning_soc_kwh - reserved_for_peaks
room_to_charge = target_soc - context.soc_kwh
```

### Option 4: Make Arbitrage Agent Understand Peak Hours Better

The Arbitrage Agent should:
1. **NOT** charge if upcoming hours (06:00-09:00) have high consumption forecasts
2. **NOT** fill battery if historical data shows morning peaks
3. **SAVE** capacity for likely peak hours

## Recommended Fix (Combination)

1. **Reduce night charging threshold** from 0.50 → 0.40 SEK (only charge when VERY cheap)
2. **Reduce target SOC** from 80% → 60% (15 kWh instead of 20 kWh)
3. **Make Peak Shaving Agent more aggressive** - act at 70% of threshold instead of 90%
4. **Add capacity reservation** - keep 8-10 kWh reserved during day for potential peaks

## Implementation

I'll apply these fixes now and test again.
