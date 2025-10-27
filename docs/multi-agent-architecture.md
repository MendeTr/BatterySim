# Multi-Agent Battery Optimization Architecture

**Date:** 2025-10-24
**Status:** Design Proposal
**Purpose:** Reference document for future implementation of intelligent battery planning system

---

## Table of Contents
1. [Problem Statement](#problem-statement)
2. [Proposed Architecture](#proposed-architecture)
3. [Dynamic Priority System](#dynamic-priority-system)
4. [Economic Calculations](#economic-calculations)
5. [Simulation Modes](#simulation-modes)
6. [Cost Analysis](#cost-analysis)
7. [Implementation Options](#implementation-options)
8. [Expected Results](#expected-results)
9. [Open Questions](#open-questions)

---

## Problem Statement

### Current Issues:
- **Single GPT doing everything**: One prompt trying to handle peak shaving + arbitrage + self-consumption + learning
- **Fixed priorities**: Peak shaving always wins, even when self-consumption is more valuable
- **Cheating in simulation**: GPT sees tomorrow's actual consumption (unrealistic)
- **Poor decisions**: Battery spreads discharge across 11 hours instead of concentrating on top 3 peaks
- **Hard to debug**: Can't tell which part of the logic failed

### Example Failure (Feb 22):
```
GPT Plan: Discharge during hours [12,13,14,15,16,17,18,19,20,21,22]
Result: 25 kWh spread across 11 hours = 2.3 kWh per hour
Problem: Peak at Hour 18 (12.1 kW) not reduced → 0 SEK savings

Should have been:
- Reserve 18 kWh for hours 17-19 (top 3 peaks)
- Use remaining 7 kWh for other hours
- Result: Peaks reduced to 5 kW → 4,500 SEK/year savings
```

---

## Proposed Architecture

### Multi-Agent System Design

```
┌────────────────────────────────────────────────────────────┐
│         GPT ORCHESTRATOR (Value Maximizer)                 │
│                                                            │
│  Input: All agent recommendations + prices + constraints   │
│  Task: Calculate SEK value for each option, pick best     │
│  Output: Final 24h plan with reasoning                    │
└─────────────────┬──────────────────────────────────────────┘
                  │
      ┌───────────┼───────────┬────────────────┐
      │           │           │                │
┌─────▼─────┐ ┌──▼────┐ ┌────▼──────┐ ┌──────▼──────┐
│Peak Agent │ │Arbit. │ │Solar Agent│ │Peak Tracker │
│           │ │Agent  │ │           │ │(Real-time)  │
└───────────┘ └───────┘ └───────────┘ └─────────────┘
```

### Component Responsibilities

#### 1. Peak Shaving Agent (GPT-4o-mini)
**Input:**
- Historical consumption patterns (7-30 days, hourly averages)
- E.ON measurement hours (06:00-23:00)

**Task:**
> "Identify the 3 hours that historically have highest consumption during E.ON hours (06:00-23:00). For each hour, estimate how much battery discharge would be needed to reduce to 5 kW target. Add 30% safety buffer for day-to-day variation."

**Output:**
```json
{
  "top_3_peak_hours": [
    {
      "hour": 18,
      "avg_consumption": 10.2,
      "estimated_discharge": 6.8,
      "confidence": "high"
    },
    {
      "hour": 17,
      "avg_consumption": 9.1,
      "estimated_discharge": 5.3,
      "confidence": "medium"
    },
    {
      "hour": 19,
      "avg_consumption": 8.5,
      "estimated_discharge": 4.6,
      "confidence": "high"
    }
  ],
  "total_battery_needed": 16.7
}
```

#### 2. Arbitrage Agent (GPT-4o-mini)
**Input:**
- 24-48h price forecast
- Night charging cost (avg 00:00-05:00 price)
- Battery efficiency (95%)

**Task:**
> "Find profitable arbitrage opportunities. Calculate profit = (discharge_price - charge_price) × kwh × 0.95. Only recommend if profit > 3 SEK/hour to account for battery degradation."

**Output:**
```json
{
  "opportunities": [
    {
      "hour": 14,
      "price": 2.8,
      "recommended_discharge": 5,
      "charge_cost": 0.6,
      "profit": 11.0,
      "profit_per_kwh": 2.2
    },
    {
      "hour": 16,
      "price": 3.2,
      "recommended_discharge": 8,
      "charge_cost": 0.6,
      "profit": 16.8,
      "profit_per_kwh": 2.1
    }
  ],
  "total_battery_needed": 13
}
```

#### 3. Solar Self-Consumption Agent (GPT-4o-mini)
**Input:**
- Solar forecast (24h, estimated based on season)
- Historical consumption patterns
- Battery state

**Task:**
> "Maximize solar usage. Recommend when to charge from solar, when to use solar directly, when to discharge battery to complement solar production."

**Output:**
```json
{
  "recommendations": [
    {
      "hour": 10,
      "action": "charge_from_solar",
      "amount": 6,
      "reasoning": "Solar 8kW > consumption 2kW, store excess"
    },
    {
      "hour": 14,
      "action": "discharge_with_solar",
      "amount": 3,
      "reasoning": "Solar 4kW + battery 3kW = cover 7kW consumption"
    }
  ]
}
```

#### 4. Peak Tracker (Algorithm, not GPT)
**Purpose:** Track current month's top 3 peaks in real-time during simulation

**Implementation:**
```python
class PeakTracker:
    def __init__(self):
        self.monthly_peaks = {}  # {month: [peak1, peak2, peak3, ...]}

    def update(self, timestamp, grid_import_kw):
        month = timestamp.strftime('%Y-%m')
        if month not in self.monthly_peaks:
            self.monthly_peaks[month] = []

        self.monthly_peaks[month].append({
            'timestamp': timestamp,
            'kw': grid_import_kw
        })

    def get_top3_threshold(self, month):
        """Returns the current 3rd highest peak for the month"""
        if month not in self.monthly_peaks:
            return 0

        peaks = sorted([p['kw'] for p in self.monthly_peaks[month]], reverse=True)
        return peaks[2] if len(peaks) >= 3 else (peaks[-1] if peaks else 0)

    def would_improve_top3(self, month, current_kw, reduced_kw):
        """Check if reducing current_kw to reduced_kw would improve top 3 average"""
        threshold = self.get_top3_threshold(month)
        return current_kw > threshold  # Only valuable if current peak is in top 3
```

**Provides to Orchestrator:**
```json
{
  "current_month": "2025-02",
  "top_3_peaks": [11.2, 10.8, 9.5],
  "threshold": 9.5,
  "message": "Reducing any peak > 9.5 kW will improve your monthly average"
}
```

#### 5. GPT Orchestrator (GPT-4o or GPT-4o-mini)
**Input:**
- All specialist agent recommendations
- Peak tracker real-time data
- Current battery SOC
- Battery capacity and power constraints
- Simulation mode (realistic vs perfect_knowledge)

**Task:**
> "You have a 25 kWh battery with 12 kW max power. For each hour tomorrow (00:00-23:00), calculate the SEK value of different discharge strategies:
>
> **Peak Shaving Value:**
> - Check if this hour would be in top 3 peaks (ask Peak Tracker)
> - If YES: value = kW_reduction × 60 SEK/kW/month ÷ 30 days
> - If NO: value = 0 (won't affect effect tariff)
>
> **Self-Consumption Value:**
> - value = price_sek_kwh × discharge_kwh
> - During extreme prices (>5 SEK/kWh), this can be MORE valuable than peak shaving!
>
> **Arbitrage Value:**
> - value = (current_price - night_charge_price) × discharge_kwh × 0.95
>
> **IMPORTANT RULES:**
> 1. During high price hours (>2.5 SEK/kWh), self-consumption can beat peak shaving
> 2. You can do BOTH peak shaving AND self-consumption in the same hour
>    - Example: Discharge 12 kW to cover full consumption → eliminates peak AND maximizes self-consumption
> 3. Calculate total value = peak_value + self_consumption_value + arbitrage_value
> 4. Allocate battery to maximize total SEK value across the day
> 5. Respect battery capacity constraint (can't discharge more than available SOC)
>
> Select the combination that maximizes total value while respecting battery capacity."

**Output:**
```json
{
  "plan": [
    {
      "hour": 0,
      "action": "charge",
      "amount": 12,
      "reasoning": "Cheapest hour (0.45 SEK/kWh), charge for tomorrow"
    },
    {
      "hour": 14,
      "action": "discharge",
      "amount": 5,
      "reasoning": "Arbitrage: profit = (2.8 - 0.6) × 5 = 11 SEK. Peak not affected (consumption only 6 kW, below top-3 threshold)"
    },
    {
      "hour": 18,
      "action": "discharge",
      "amount": 12,
      "reasoning": "COMBINED VALUE: Peak shaving (12→5 kW saves 7×60/30=14 SEK) + Self-consumption (7 kW @ 3.2 SEK saves 22 SEK) = 36 SEK total. Highest value hour! Current top-3 threshold is 9.5 kW, so reducing this 12 kW peak is critical."
    }
  ],
  "total_estimated_savings": 87.5,
  "battery_usage": {
    "charged": 24,
    "discharged": 23.5,
    "final_soc": 12.2
  }
}
```

---

## Dynamic Priority System

### OLD (Fixed Priority) - WRONG:
```
Priority 1: Peak Shaving (always wins)
Priority 2: Arbitrage
Priority 3: Self-consumption
```

**Problem:** On a 6 SEK/kWh day, self-consumption saves 30 SEK/hour, but peak shaving only saves 2 SEK/day. Fixed priority wastes value!

### NEW (Value-Based Priority) - CORRECT:

**For each hour, calculate SEK value:**

```python
def calculate_hour_value(hour_data, peak_tracker, battery_soc):
    consumption = hour_data['consumption']
    price = hour_data['price']
    solar = hour_data['solar']

    # Option 1: Do nothing
    cost_without_battery = consumption × price + peak_cost

    # Option 2: Peak shaving only (discharge just enough to hit 5 kW)
    if consumption > 5:
        peak_discharge = consumption - solar - 5
        is_in_top3 = peak_tracker.would_improve_top3(consumption)
        peak_value = (consumption - 5) × 60 / 30 if is_in_top3 else 0
        cost_option2 = 5 × price + peak_discharge × charge_cost + reduced_peak_cost
        savings_option2 = cost_without_battery - cost_option2

    # Option 3: Full self-consumption (discharge to cover ALL consumption)
    full_discharge = consumption - solar
    if full_discharge <= battery_soc:
        self_consumption_value = (consumption - solar) × price
        peak_elimination_value = consumption × 60 / 30 if is_in_top3 else 0
        cost_option3 = full_discharge × charge_cost
        savings_option3 = cost_without_battery - cost_option3

    # Option 4: Arbitrage only (discharge during expensive hours, ignore peaks)
    arbitrage_value = (price - night_charge_price) × discharge_kwh × 0.95

    # Pick the option with MAXIMUM savings
    return max(savings_option1, savings_option2, savings_option3, savings_option4)
```

### Example Calculations

#### Scenario 1: Normal Day (1.2 SEK/kWh)
```
Hour 18: 12 kW consumption, 1.2 SEK/kWh, 0 solar
Current top-3 peaks: [11.2, 10.8, 9.5] kW

Option A: Do nothing
  - Cost: 12 × 1.2 = 14.4 SEK
  - Peak tariff: 12 kW → 60 SEK/month = 2 SEK/day
  - Total: 16.4 SEK

Option B: Peak shaving (discharge 7 kW → 5 kW grid import)
  - Grid cost: 5 × 1.2 = 6 SEK
  - Battery cost: 7 × 0.6 = 4.2 SEK
  - Peak tariff: 5 kW → 10 SEK/month = 0.33 SEK/day
  - Total: 10.53 SEK
  - Savings: 5.87 SEK ✓

Option C: Full self-consumption (discharge 12 kW → 0 kW grid)
  - Grid cost: 0 SEK
  - Battery cost: 12 × 0.6 = 7.2 SEK
  - Peak tariff: 0 kW → 0 SEK
  - Total: 7.2 SEK
  - Savings: 9.2 SEK ✓✓ BEST!

Decision: Discharge 12 kW (full self-consumption wins)
```

#### Scenario 2: Extreme Price Spike (5.8 SEK/kWh)
```
Hour 14: 8 kW consumption, 5.8 SEK/kWh, 0 solar
Current top-3 peaks: [11.2, 10.8, 9.5] kW (Hour 14 won't be in top 3)

Option A: Do nothing
  - Cost: 8 × 5.8 = 46.4 SEK
  - Peak tariff: 0 SEK (not in top 3)
  - Total: 46.4 SEK

Option B: Peak shaving (discharge 3 kW → 5 kW grid import)
  - Grid cost: 5 × 5.8 = 29 SEK
  - Battery cost: 3 × 0.6 = 1.8 SEK
  - Peak tariff: 0 SEK (8 kW < 9.5 kW threshold)
  - Total: 30.8 SEK
  - Savings: 15.6 SEK ✓

Option C: Full self-consumption (discharge 8 kW → 0 kW grid)
  - Grid cost: 0 SEK
  - Battery cost: 8 × 0.6 = 4.8 SEK
  - Peak tariff: 0 SEK
  - Total: 4.8 SEK
  - Savings: 41.6 SEK ✓✓✓ MASSIVE WIN!

Decision: Discharge 8 kW (self-consumption saves 41.6 SEK vs peak shaving's 15.6 SEK)
```

**Key Insight:** At 5.8 SEK/kWh, self-consumption saves **2.7x more** than peak shaving!

---

## Simulation Modes

### Mode 1: Realistic (Real-world simulation)

**What GPT sees:**
- ✅ Historical consumption patterns (7-30 day averages per hour)
- ✅ Price forecast (known at 13:00 day-ahead)
- ✅ Solar forecast (estimated based on season/weather)
- ❌ Tomorrow's actual consumption (UNKNOWN in real life)

**How it plans:**
```python
# At 13:00 on Feb 21, planning for Feb 22

historical_pattern = {
    'hour_18_avg': 10.2 kW,  # Average of past 7-30 days
    'hour_18_std': 2.1 kW,   # Standard deviation
}

# GPT estimates with 30% buffer
estimated_discharge_needed = (10.2 - 0 - 5) × 1.3 = 6.76 kW

# On Feb 22, actual consumption might be:
# - 8 kW (low day) → over-reserved battery ✓ still works
# - 12 kW (high day) → under-reserved battery ✗ peak not fully reduced

# This is REALISTIC - you can't predict perfectly!
```

**Purpose:** Shows what a real battery system would achieve with AI planning

### Mode 2: Perfect Knowledge (Theoretical maximum)

**What GPT sees:**
- ✅ Historical consumption patterns
- ✅ Price forecast
- ✅ Solar forecast
- ✅ Tomorrow's ACTUAL consumption (cheating for simulation purposes)

**How it plans:**
```python
# At 13:00 on Feb 21, planning for Feb 22

actual_consumption = {
    'hour_18': 12.1 kW,  # ACTUAL value from Tibber data (cheating!)
}

# GPT plans with perfect knowledge
discharge_needed = 12.1 - 0 - 5 = 7.1 kW (exact)

# On Feb 22, actual consumption is 12.1 kW → perfect reduction to 5 kW ✓
```

**Purpose:** Shows theoretical maximum savings if AI could predict perfectly

### Comparison in Results

```
═══════════════════════════════════════════════════
            BATTERY ROI ANALYSIS 2024-2025
═══════════════════════════════════════════════════

📊 SIMULATION MODE: Realistic (Historical Patterns)

💰 POTENTIAL SAVINGS (your past year):

Peak Shaving (Top 3 Average):
  ├─ Without Battery: 11.2 kW average
  ├─ With Battery:     6.8 kW average
  ├─ Reduction:        4.4 kW
  └─ Annual Savings:   3,168 SEK

Arbitrage Trading:
  ├─ Charge cycles:    312
  ├─ Discharge cycles: 287
  └─ Annual Savings:   4,075 SEK

Self-Consumption:
  └─ Annual Savings:   1,200 SEK

📈 TOTAL ANNUAL SAVINGS:    8,443 SEK

💵 ROI CALCULATION:
  ├─ Battery Cost:        80,000 SEK
  ├─ Annual Savings:       8,443 SEK
  └─ Simple Payback:      9.5 years

═══════════════════════════════════════════════════
📊 COMPARISON: Perfect Knowledge Mode
═══════════════════════════════════════════════════

With perfect AI prediction:
  ├─ Peak Shaving:        4,512 SEK (+1,344 SEK) = 42% better
  ├─ Arbitrage:           5,230 SEK (+1,155 SEK) = 28% better
  ├─ Self-consumption:    1,450 SEK (+250 SEK) = 21% better
  └─ Total:              11,192 SEK

Your "AI improvement gap": 2,749 SEK/year (32.6%)

This shows potential savings with better prediction algorithms.

═══════════════════════════════════════════════════

💡 Missing from calculation:
   • Stödtjänster (FCR-N/D): 5,000-15,000 SEK/year potential
   • Backup power value during outages
   • Future electricity price increases

   With 10,000 SEK/year from FCR:
   Total savings: 18,443 SEK/year
   Payback: 4.3 years ✅
```

---

## Cost Analysis

### Current Design (4 AI calls/day)

**API costs per year:**
```
Peak Agent:     365 × $0.0003 = $0.11
Arbitrage Agent: 365 × $0.0003 = $0.11
Solar Agent:    365 × $0.0003 = $0.11
Orchestrator:   365 × $0.003  = $1.10
─────────────────────────────────────
TOTAL:                          $1.43/year (~15 SEK/year)
```

**Not bad!** But can be cheaper...

### Optimized Hybrid (1 AI call/day)

**Use algorithms for 90% of work:**
- Peak Tracker: Algorithm (find top 3 max values)
- Arbitrage Calculator: Algorithm (simple profit math)
- Solar Optimizer: Algorithm (greedy allocation)

**Use GPT only for orchestration:**
```
Orchestrator: 365 × $0.0003 (GPT-4o-mini) = $0.11/year (~1 SEK/year)
```

### Alternative AI Providers

| Provider | Model | Cost/year | Speed | Quality |
|----------|-------|-----------|-------|---------|
| OpenAI | GPT-4o-mini | $0.11 | Fast | Excellent |
| Anthropic | Claude 3.5 Haiku | $0.03 | Very fast | Excellent |
| Groq | Llama 3.1 70B | FREE | Very fast | Good |
| Google | Gemini Flash | FREE | Fast | Good |
| Ollama | Llama 3 (local) | FREE | Medium | Good |
| None | Pure algorithm | FREE | Instant | Limited |

### Recommendation: Support Multiple Backends

```javascript
// In UI config
<select name="ai_provider">
  <option value="openai-gpt4o-mini">OpenAI GPT-4o-mini (1 SEK/år, bäst kvalitet)</option>
  <option value="anthropic-haiku">Claude 3.5 Haiku (0.3 SEK/år, snabbast)</option>
  <option value="groq-llama">Groq Llama 3.1 (GRATIS, snabb)</option>
  <option value="ollama-local">Ollama Local (GRATIS, offline, långsammare)</option>
  <option value="algorithm">Ingen AI - bara algoritm (GRATIS, begränsad)</option>
</select>

<div className="info">
  💡 GPT-4o-mini rekommenderas för bästa resultat (kostar ~1 SEK/år).
  För gratis alternativ, testa Groq Llama eller ren algoritm.
</div>
```

---

## Implementation Options

### Option A: Full Multi-Agent (Recommended for v2)
```
✅ 4 specialist agents + 1 orchestrator
✅ Best decision quality
✅ Easy to debug each component
✅ Extensible (add more agents later)
❌ More complex code
❌ 5 AI calls/day (but still only $1.43/year)
```

### Option B: Hybrid (Recommended for v1)
```
✅ Algorithms for specialists + GPT orchestrator
✅ 1 AI call/day ($0.11/year)
✅ 90% of the benefit, 20% of the cost
✅ Simpler implementation
✓ Good balance of cost/quality
```

### Option C: Pure Algorithm (Backup option)
```
✅ Zero AI cost
✅ Instant planning (no API calls)
✅ Deterministic (easy to test)
❌ No learning/adaptation
❌ Can't handle edge cases
❌ Fixed logic (no intelligence)
```

### Recommended Path Forward:

**Phase 1 (Quick Win):**
1. Implement hybrid approach (algorithms + 1 GPT orchestrator)
2. Support OpenAI GPT-4o-mini + pure algorithm mode
3. Implement both simulation modes (realistic + perfect)
4. Test on February data first (fast iteration)

**Phase 2 (Full System):**
1. Add specialist agents (peak, arbitrage, solar)
2. Add more AI provider options (Claude, Groq, Ollama)
3. Implement learning agent (adapts buffers based on past performance)
4. Add real-time peak tracking
5. Run full year simulation

**Phase 3 (Production):**
1. Real-time mode (not simulation)
2. Integration with actual battery system
3. Live price feeds
4. Mobile app/notifications
5. Multi-user support

---

## Expected Results

### Realistic Mode (Historical Patterns + 30% Buffer):

```
Peak Shaving:
- Top 3 average reduced from 11.2 kW → 6.8 kW
- Reduction: 4.4 kW
- Annual savings: 4.4 × 60 × 12 = 3,168 SEK

Arbitrage:
- ~250 profitable cycles/year
- Avg profit: 15 SEK/cycle
- Annual savings: 3,750 SEK

Self-Consumption:
- During extreme prices (>3 SEK/kWh): ~1,500 SEK
- During normal prices: ~800 SEK
- Annual savings: 2,300 SEK

TOTAL: 9,218 SEK/year
Payback: 80,000 / 9,218 = 8.7 years
```

### Perfect Knowledge Mode (Theoretical Maximum):

```
Peak Shaving:
- Top 3 average reduced from 11.2 kW → 5.0 kW (perfect)
- Reduction: 6.2 kW
- Annual savings: 6.2 × 60 × 12 = 4,464 SEK

Arbitrage:
- ~300 profitable cycles/year (optimal timing)
- Avg profit: 18 SEK/cycle
- Annual savings: 5,400 SEK

Self-Consumption:
- Perfectly timed discharge during price spikes
- Annual savings: 3,200 SEK

TOTAL: 13,064 SEK/year
Payback: 80,000 / 13,064 = 6.1 years

"AI gap": 13,064 - 9,218 = 3,846 SEK/year (42% improvement possible)
```

### With FCR Revenue (salesmen's claim):

```
Realistic Mode:  9,218 + 10,000 (FCR) = 19,218 SEK/year → 4.2 years ✅
Perfect Mode:   13,064 + 10,000 (FCR) = 23,064 SEK/year → 3.5 years ✅

Conclusion: Salesmen's "3-4 years" is achievable IF:
  1. You participate in FCR-N/D markets (~10,000 SEK/year)
  2. Battery planning is decent (doesn't need to be perfect)
  3. Electricity prices remain similar to 2024-2025
```

---

## Open Questions

### Before Implementation:

1. **Which architecture to start with?**
   - [ ] Option A: Full multi-agent (4 specialists + orchestrator)
   - [ ] Option B: Hybrid (algorithms + 1 orchestrator)  ← Recommended
   - [ ] Option C: Pure algorithm (no AI)

2. **Which AI provider(s) to support initially?**
   - [ ] OpenAI GPT-4o-mini only (simplest)
   - [ ] OpenAI + Algorithm toggle ← Recommended
   - [ ] Multiple providers from day 1

3. **Learning/Adaptation:**
   - [ ] Static planning (7-30 day average, no learning)
   - [ ] Simple adaptation (adjust buffers based on past week)
   - [ ] Full learning agent (ML-based prediction improvement)

4. **Testing strategy:**
   - [ ] Keep date range filter for fast iteration (Feb only)
   - [ ] Run full year immediately
   - [ ] Add A/B testing mode (compare strategies side-by-side)

5. **Peak tracking:**
   - [ ] Implement real-time peak tracker (recommended)
   - [ ] Simple post-hoc calculation (easier but less accurate)

6. **UI changes needed:**
   - [ ] Add simulation mode toggle (realistic vs perfect)
   - [ ] Add AI provider selector
   - [ ] Add "AI gap" visualization in results
   - [ ] Show decision reasoning per hour (debug mode)

### User Decisions Needed:

- **Priority:** Speed to working solution vs. perfect architecture?
- **Budget:** Willing to pay $1-2/year for better AI, or must be free?
- **Complexity:** Comfortable with multi-agent code, or prefer simpler algorithm?
- **Testing:** Want to test on Feb data first, or run full year now?

---

## Next Steps

Once decisions are made:

1. **Create new branch:** `feature/multi-agent-battery-planning`
2. **Implement chosen architecture** (likely Option B: Hybrid)
3. **Add simulation mode toggle** in UI
4. **Test on February 2025 data** (high peak month)
5. **Compare realistic vs perfect mode** results
6. **Run full year simulation** if results look good
7. **Add FCR revenue estimates** to ROI calculation
8. **Document findings** and compare to salesmen's claims

---

**End of Architecture Reference Document**

*This document should be updated as implementation proceeds and new insights are discovered.*
