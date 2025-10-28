# Sigenergy-Style 24-Hour Planning Architecture

**Date**: 2025-10-28
**Status**: In Progress
**Goal**: Implement Sigenergy-inspired 24-hour optimization for battery management

---

## Executive Summary

This document describes the implementation of a **24-hour proactive planning system** inspired by Sigenergy's AI approach (analyzed in `docs/sigenai.txt` and `docs/Analysis_sig_vs_roi.txt`).

**Key Change**: From **hourly reactive decisions** → **daily proactive optimization**

---

## Problem with Previous Approach

### What Was Wrong
1. **Hour-by-hour planning**: Agents decided independently each hour
2. **Reactive logic**: Waited for consumption to exceed threshold before acting
3. **Short forecast horizon**: Peak Shaving Agent only looked 3 hours ahead
4. **No global optimization**: Could miss better opportunities (e.g., charge at 0.35 SEK instead of 0.45 SEK)

### Real-World Issue
**You told me**: "We get the prices for next day each day at 13:00, so at 13:00 we know the prices already for next day and should be able to plan accordingly."

**I mistakenly**: Added "continuous discharge every hour" logic instead of keeping 24h planning.

---

## Sigenergy's Approach (What We're Copying)

### Daily Planning Cycle

```
13:00 Each Day (when Nordpool releases next-day prices):
├─ STEP 1: Generate 24h Forecasts
│  ├─ Consumption forecast (historical patterns + weather)
│  ├─ Solar forecast (weather API)
│  └─ Price forecast (already known from Nordpool)
│
├─ STEP 2: Solve Global Optimization
│  ├─ Objective: Minimize total cost over 24 hours
│  ├─ Constraints:
│  │  ├─ Battery capacity/power limits
│  │  ├─ Reserve requirements (10 kWh for peaks)
│  │  ├─ No charging during E.ON hours (06-23)
│  │  └─ Energy balance (consumption = grid + battery ± solar)
│  │
│  └─ Output: Hour-by-hour charge/discharge schedule
│
└─ STEP 3: Store 24h Plan
   └─ Execute plan hour-by-hour with real-time adjustments
```

### Hourly Execution

```
Each Hour (00-23):
├─ Check today's plan: "Hour 18: Discharge 6 kWh"
├─ Measure actual consumption vs forecast
├─ IF deviation < 30%:
│  └─ Execute planned action
├─ ELSE (spike detected):
│  └─ Real-time override: Emergency discharge
└─ Log actual vs predicted for learning
```

### Key Insight from Sigenergy

> "By considering the whole upcoming day, it avoids discharging too early and having no energy left for a later peak price, or over-charging and wasting solar potential. This strategic scheduling is a step beyond simple rules."

**Example**: If prices are [0.45, 0.40, 0.35, 0.50] SEK/kWh overnight, the 24h optimizer charges at 0.35 (hour 3), not 0.45 (hour 1). Hour-by-hour logic would charge at first "cheap enough" hour.

---

## Implementation Plan

### Component 1: Daily Optimizer (`agents/daily_optimizer.py`)

**Purpose**: Solve 24h optimization problem at 13:00 each day

**Input**:
- 24h consumption forecast (from historical patterns)
- 24h solar forecast (from historical or weather API)
- 24h price forecast (from Nordpool, known at 13:00)
- Current battery SOC
- Peak threshold for month
- Battery constraints (capacity, power, efficiency)

**Output**:
- `charge_schedule`: List[24] - kWh to charge each hour
- `discharge_schedule`: List[24] - kWh to discharge each hour
- `soc_schedule`: List[24] - Expected SOC trajectory
- `expected_cost`: Total cost for 24h period
- `expected_peak_kw`: Expected peak during E.ON hours
- `reasoning`: Human-readable plan explanation

**Algorithm** (Heuristic approach, upgrade to LP/MIP later):
1. Identify cheapest charging hours (night, outside E.ON, <1 SEK/kWh)
2. Identify peak hours (high consumption during E.ON, >5 kW)
3. Plan charging: Fill battery to 60% at cheapest hours
4. Plan discharging: Reduce peaks to <5 kW during E.ON hours
5. Respect 10 kWh reserve for unexpected spikes

**Status**: ✅ Created `agents/daily_optimizer.py`

---

### Component 2: Boss Agent with 24h Planning

**Modification to `agents/boss_agent.py`**:

```python
class BossAgent:
    def __init__(self, ...):
        self.optimizer = DailyOptimizer()
        self.daily_plan = None  # Stores current 24h plan
        self.plan_created_date = None

    def create_daily_plan(self, context: BatteryContext) -> DailyPlanOutput:
        """Called at 13:00 when next-day prices available."""

        # Build optimization inputs
        inputs = DailyPlanInput(
            consumption_forecast=context.consumption_forecast,  # 24h
            solar_forecast=context.solar_forecast,  # 24h
            price_forecast=context.spot_prices,  # 24h
            current_soc_kwh=context.soc_kwh,
            capacity_kwh=context.capacity_kwh,
            # ... other params
        )

        # Solve optimization
        plan = self.optimizer.optimize_24h(inputs)

        # Store plan
        self.daily_plan = plan
        self.plan_created_date = context.timestamp.date()

        return plan

    def analyze(self, context: BatteryContext) -> Optional[BossDecision]:
        """Called every hour to execute plan."""

        # Check if we need to create new plan (13:00 daily)
        if context.hour == 13 and context.timestamp.date() != self.plan_created_date:
            self.create_daily_plan(context)

        # If no plan, fall back to hourly logic
        if not self.daily_plan:
            return self._analyze_hourly(context)  # Existing logic

        # Execute planned action for this hour
        hour_of_day = context.hour
        planned_charge = self.daily_plan.charge_schedule[hour_of_day]
        planned_discharge = self.daily_plan.discharge_schedule[hour_of_day]

        # Check for real-time override (spike detected)
        if self._should_override_plan(context):
            return self._emergency_override(context)

        # Execute plan
        if planned_charge > 0:
            return BossDecision(action=AgentAction.CHARGE, kwh=planned_charge, ...)
        elif planned_discharge > 0:
            return BossDecision(action=AgentAction.DISCHARGE, kwh=planned_discharge, ...)
        else:
            return BossDecision(action=AgentAction.HOLD, ...)
```

**Status**: 🔄 Next step

---

### Component 3: Real-Time Override

**Purpose**: Handle unexpected deviations from plan

**Logic**:
```python
def _should_override_plan(self, context: BatteryContext) -> bool:
    """Detect if actual consumption significantly exceeds forecast."""
    hour = context.hour
    planned_consumption = self.consumption_forecast[hour]  # What we expected
    actual_consumption = context.consumption_kw  # What's happening

    # If actual > 1.3x forecast, spike detected!
    return actual_consumption > planned_consumption * 1.3

def _emergency_override(self, context: BatteryContext) -> BossDecision:
    """Emergency discharge to prevent peak."""
    # Peak Shaving Agent takes over
    emergency_rec = self.peak_shaving_agent.analyze(context)
    if emergency_rec:
        return BossDecision(
            action=emergency_rec.action,
            kwh=emergency_rec.kwh,
            reasoning=f"OVERRIDE: {emergency_rec.reasoning}",
            ...
        )
```

**Status**: 🔄 To be implemented

---

### Component 4: Learning Loop (Future)

**Purpose**: Improve forecasts over time

```python
def update_consumption_model(self, actual, predicted):
    """Learn from prediction errors."""
    error = actual - predicted

    # Update hourly bias
    self.hourly_adjustment[hour] = 0.9 * self.hourly_adjustment[hour] + 0.1 * error

    # Retrain ML model weekly
    if days_since_training > 7:
        self.retrain_consumption_predictor()
```

**Status**: 📅 Deferred to future iteration

---

## What We Keep From Previous Work

### ✅ Improvements to Keep
1. **10 kWh peak reserve** - Ensures capacity always available
2. **No charging during E.ON hours** - Fixed RealTimeOverride bug
3. **No self-consumption discharge during E.ON hours** - Preserves capacity for peaks
4. **Percentile-based reserves** - Reserve Calculator still valid
5. **Multi-agent validation** - Agents can review the plan

### ❌ Changes to Revert
1. **Continuous discharge every hour** - Removed from peak_shaving_agent.py
2. **3-hour forecast limit** - Restored to 24 hours
3. **Hourly reactive planning** - Replaced with daily proactive planning

---

## Expected Results

### Current Performance (Hourly Reactive)
- Average monthly peak reduction: **1.09 kW**
- Annual savings: **785 SEK/year**
- Battery usage: Reactive, sometimes too late

### Target Performance (24h Planning)
- Average monthly peak reduction: **2-3 kW** (2x-3x improvement)
- Annual savings: **1500-2000 SEK/year**
- Battery usage: Pre-positioned for known peaks
- Better arbitrage: Charges at absolute cheapest hour

### Why This Should Work

**Example Scenario** (Feb 18, evening peak):
- **Old approach (reactive)**:
  - Hour 18: Consumption 15 kW → Discharge 10 kW → Still 5 kW peak
  - Hour 20: Consumption 27 kW → Battery already empty → 27 kW peak! ❌

- **New approach (24h planning)**:
  - At 13:00 day before: "I see consumption will be high 18-20. Let me reserve 12 kWh."
  - Charges to 18 kWh at night (cheap 0.35 SEK/kWh)
  - Hour 18: Discharge 6 kWh, SOC now 12 kWh
  - Hour 20: Discharge 12 kWh maximum → Reduces 27 kW to 15 kW ✅

---

## Testing Plan

### Phase 1: Implement & Test Optimizer Alone
```bash
python test_daily_optimizer.py
```
- Input: Sample 24h forecast
- Output: Verify charge/discharge schedule makes sense
- Check: Charges at cheap hours, discharges at peak hours

### Phase 2: Integrate with Boss Agent
```bash
python test_boss_agent.py
```
- Compare: 24h planning vs hourly reactive
- Metrics: Peak reduction, cost savings, battery utilization

### Phase 3: Full Year Simulation
```bash
python test_boss_agent.py --full-year
```
- Test on full year of real data
- Verify: Consistent improvement across all months
- Generate: ROI comparison report

---

## Implementation Status

- [x] Revert continuous discharge logic
- [x] Create `agents/daily_optimizer.py`
- [ ] Modify `agents/boss_agent.py` for 24h planning
- [ ] Add real-time override capability
- [ ] Test on sample data
- [ ] Test on full year data
- [ ] Commit & push to GitHub

---

## References

1. **docs/sigenai.txt** - Detailed analysis of Sigenergy's AI system
2. **docs/Analysis_sig_vs_roi.txt** - Comparison of approaches
3. **battery_simulator.py:516-615** - Original GPT 24h planning code
4. **Nordpool** - Day-ahead prices released at 13:00 CET

---

## Questions & Decisions

### Q1: Optimization Library?
**Decision**: Start with heuristic approach (no external library). Upgrade to pulp/cvxpy later if needed.

### Q2: Weather Integration?
**Decision**: Deferred. Use historical patterns for now. Add weather API later.

### Q3: Keep GPT Mode?
**Decision**: Keep as separate mode. Boss Agent with optimizer is deterministic alternative.

### Q4: Learning Loop?
**Decision**: Deferred to future iteration. Focus on 24h planning first.

---

## Next Steps

1. ✅ Document plan (this file)
2. 🔄 Update implementation roadmap
3. 🔄 Modify Boss Agent to use optimizer
4. Test & iterate

**Timeline**: Complete by end of day (2025-10-28)
