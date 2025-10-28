# Multi-Agent Battery Optimization - Implementation Roadmap

**Project:** Battery ROI Calculator - Multi-Agent Architecture
**Start Date:** 2025-10-24
**Last Updated:** 2025-10-28
**Status:** Active Development - Sigenergy 24h Planning

---

## Overview

This roadmap outlines the implementation plan for transitioning from single-GPT planning to a multi-agent architecture with dynamic value-based decision making.

**Goal:** Improve peak shaving effectiveness from 936 SEK/year to 3,000-4,500 SEK/year through intelligent battery planning.

**NEW (2025-10-28)**: Implementing Sigenergy-style 24-hour proactive planning based on analysis of their AI system. See `docs/sigenergy-24h-planning.md` for full details.

---

## 🚀 Epic 0: Sigenergy 24h Planning Architecture (CURRENT PRIORITY)

**Goal:** Implement 24-hour proactive optimization inspired by Sigenergy's AI approach

**Background:** Previous attempts at peak shaving were reactive (hour-by-hour decisions). Sigenergy's analysis shows they plan the entire 24 hours at once when next-day prices are known (13:00 daily). This allows:
- Pre-positioning battery for known peak windows
- Charging at absolute cheapest hour (not just "cheap enough")
- Global optimization across 24 hours (not greedy local decisions)

**Reference Documents:**
- `docs/sigenai.txt` - Detailed analysis of Sigenergy's AI system
- `docs/Analysis_sig_vs_roi.txt` - Comparison of their approach vs ours
- `docs/sigenergy-24h-planning.md` - Implementation plan

### Story 0.1: Create 24h Optimizer ✅ COMPLETED
**Status:** ✅ Done (2025-10-28)

- [x] **Task 0.1.1:** Create `agents/daily_optimizer.py`
  - Implements 24-hour optimization problem
  - Input: 24h forecasts (consumption, solar, prices)
  - Output: Hour-by-hour charge/discharge schedule
  - Algorithm: Heuristic approach (identify cheap charging hours + peak discharge hours)
  - File: Created `agents/daily_optimizer.py`

### Story 0.2: Revert Reactive Logic 🔄 IN PROGRESS
**Status:** ✅ 80% Done (2025-10-28)

- [x] **Task 0.2.1:** Remove continuous discharge from `peak_shaving_agent.py`
  - Removed lines 97-136 (reactive hourly discharge logic)
  - This was a mistake - broke the 24h planning architecture

- [x] **Task 0.2.2:** Restore 24h forecast horizon
  - Changed from 3 hours → 24 hours look-ahead
  - Allows proper planning for entire day

- [ ] **Task 0.2.3:** Keep improvements that work
  - 10 kWh peak reserve ✅
  - No charging during E.ON hours ✅
  - No self-consumption discharge during E.ON hours ✅

### Story 0.3: Integrate 24h Planning with Boss Agent 🔄 NEXT
**Status:** 🔄 In Progress (2025-10-28)

- [ ] **Task 0.3.1:** Add `create_daily_plan()` method to `boss_agent.py`
  - Called at 13:00 each day when prices known
  - Uses DailyOptimizer to solve 24h problem
  - Stores plan for execution

- [ ] **Task 0.3.2:** Modify `analyze()` to execute planned actions
  - Check if plan exists for current hour
  - Execute: Charge X kWh or Discharge Y kWh
  - Fall back to hourly logic if no plan

- [ ] **Task 0.3.3:** Add real-time override capability
  - Detect when actual consumption >> forecast (spike)
  - Override plan: Emergency discharge
  - Log override for learning

### Story 0.4: Testing & Validation 📅 PENDING
**Status:** 📅 To Do

- [ ] **Task 0.4.1:** Create test script `test_daily_optimizer.py`
  - Test optimizer with sample 24h data
  - Verify: Charges at cheap hours, discharges at peaks
  - Check: Respects constraints

- [ ] **Task 0.4.2:** Test Boss Agent with 24h planning
  - Run `test_boss_agent.py` with real data
  - Compare: 24h planning vs hourly reactive
  - Target: 2-3 kW average monthly peak reduction (2x-3x improvement)

- [ ] **Task 0.4.3:** Generate comparison report
  - Baseline: Current reactive system (1.09 kW reduction, 785 SEK/year)
  - Target: 24h planning (2-3 kW reduction, 1500-2000 SEK/year)
  - Document: Battery utilization, arbitrage effectiveness, peak timing

### Story 0.5: Documentation & Commit 📅 PENDING
**Status:** 🔄 Partial

- [x] **Task 0.5.1:** Document plan in `docs/sigenergy-24h-planning.md` ✅
- [x] **Task 0.5.2:** Update this roadmap ✅
- [ ] **Task 0.5.3:** Commit & push to GitHub
- [ ] **Task 0.5.4:** Create summary of improvements

### 🎯 Success Metrics for Epic 0
- [ ] Peak reduction: 2-3 kW average (currently 1.09 kW)
- [ ] Annual savings: 1500-2000 SEK (currently 785 SEK)
- [ ] Battery pre-positioned for evening peaks (17-21)
- [ ] Charges at absolute cheapest hour (not first "cheap enough")

---

## Epic 1: Foundation & Architecture Setup

### Story 1.1: Fix Current Simulation Issues ⚠️ HIGH PRIORITY
**Goal:** Remove "cheating" from simulation and make it realistic

- [ ] **Task 1.1.1:** Remove actual consumption forecast from GPT prompt
  - File: `battery_simulator.py` line 448-449
  - Change: Remove `consumption_forecast` from context
  - Keep only: historical patterns, prices, solar forecast
  - Status: ✅ COMPLETED (already done)

- [ ] **Task 1.1.2:** Update GPT prompt to use historical patterns only
  - Change all references from "tomorrow's forecast" to "historical patterns"
  - Add 30% buffer instructions for uncertainty
  - Emphasize learning from past 7-30 days
  - Status: ✅ COMPLETED (already done)

- [ ] **Task 1.1.3:** Test realistic mode on February 2025 data
  - Clear date range: 2025-02-01 to 2025-02-28
  - Run simulation with new prompt
  - Check if peak shaving improves (target: >2,000 SEK for Feb)
  - Status: ⏸️ PENDING USER

- [ ] **Task 1.1.4:** Document baseline results
  - Save Feb results (realistic mode)
  - Note: peak reduction, arbitrage, self-consumption
  - This becomes the "before multi-agent" baseline
  - Status: ⏸️ PENDING

- [x] **Task 1.1.5:** Fix export revenue calculation to use user-configurable transfer fee
  - File: `battery_simulator.py` lines 1192-1193, 1340, 1414-1415
  - Current (WRONG): `export_rate = 0.377` (hardcoded 37.7%)
  - Change to (CORRECT): `export_revenue = spot_price - grid_fee_sek_kwh`
  - Use `grid_fee_sek_kwh` parameter from frontend (user enters their actual rate)
  - Clip to zero if spot < transfer fee (don't export at a loss)
  - Status: ✅ COMPLETED

**Acceptance Criteria:**
- GPT plans without seeing actual future consumption ✅
- Simulation represents realistic battery performance ✅
- Export revenue calculated correctly (spot - transfer fee) ✅
- Baseline metrics documented for comparison ⏸️

---

### Story 1.2: Add Simulation Mode Toggle
**Goal:** Allow comparison between realistic and perfect knowledge modes

- [ ] **Task 1.2.1:** Add `simulation_mode` parameter to API
  - File: `app.py`
  - Add parameter: `simulation_mode` (values: "realistic" | "perfect_knowledge")
  - Pass to simulator
  - Status: ⏸️ PENDING

- [ ] **Task 1.2.2:** Implement mode switching in simulator
  - File: `battery_simulator.py`
  - If mode = "realistic": use historical patterns only
  - If mode = "perfect_knowledge": include actual consumption forecast
  - Add flag to GPT context
  - Status: ⏸️ PENDING

- [ ] **Task 1.2.3:** Add UI toggle in frontend
  - File: `index.html`
  - Add dropdown: "Realistisk" vs "Perfekt kunskap"
  - Show explanation tooltip
  - Status: ⏸️ PENDING

- [ ] **Task 1.2.4:** Update results display to show mode
  - Add badge: "📊 Simuleringsläge: Realistisk"
  - Show both modes side-by-side in results
  - Calculate "AI gap" percentage
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- User can toggle between realistic and perfect modes
- Results clearly show which mode was used
- Both modes can be compared in results view

---

### Story 1.3: Create Project Structure for Multi-Agent System
**Goal:** Set up clean architecture for specialist agents

- [ ] **Task 1.3.1:** Create agents directory structure
  ```
  agents/
    __init__.py
    base_agent.py          # Base class for all agents
    peak_agent.py          # Peak shaving specialist
    arbitrage_agent.py     # Arbitrage specialist
    solar_agent.py         # Solar self-consumption specialist
    orchestrator.py        # Main decision maker
    peak_tracker.py        # Real-time peak tracking (algorithm)
  ```
  - Status: ⏸️ PENDING

- [ ] **Task 1.3.2:** Create base agent interface
  - File: `agents/base_agent.py`
  - Abstract class with: `plan()`, `get_recommendations()`
  - Common utilities: token counting, error handling
  - Status: ⏸️ PENDING

- [ ] **Task 1.3.3:** Add agent configuration
  - File: `config.py` or `agents/config.py`
  - Settings: AI provider, model, temperature, max_tokens
  - Support multiple providers: OpenAI, Anthropic, Groq, Ollama
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Clean directory structure created
- Base classes defined
- Configuration system in place

---

## Epic 2: Implement Specialist Agents

### Story 2.1: Peak Tracker (Algorithm-based)
**Goal:** Track monthly top-3 peaks in real-time during simulation

- [ ] **Task 2.1.1:** Implement PeakTracker class
  - File: `agents/peak_tracker.py`
  - Methods:
    - `update(timestamp, grid_import_kw)` - Add new data point
    - `get_top3(month)` - Get top 3 peaks for month
    - `get_top3_threshold(month)` - Get 3rd highest peak
    - `would_improve_top3(month, current_kw)` - Check if reduction helps
  - Status: ⏸️ PENDING

- [ ] **Task 2.1.2:** Integrate PeakTracker into simulator
  - File: `battery_simulator.py`
  - Initialize tracker at simulation start
  - Update after each hour
  - Pass current threshold to orchestrator
  - Status: ⏸️ PENDING

- [ ] **Task 2.1.3:** Add peak tracker output to daily summary
  - Show current top-3 peaks in terminal output
  - Display threshold: "Current top-3 threshold: 9.5 kW"
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Peak tracker correctly identifies top 3 peaks per month
- Threshold updates in real-time during simulation
- Orchestrator knows if reducing a peak actually helps

---

### Story 2.2: Peak Shaving Agent (GPT-based)
**Goal:** Identify typical peak hours and recommend discharge strategy

- [ ] **Task 2.2.1:** Create PeakAgent class
  - File: `agents/peak_agent.py`
  - Inherits from BaseAgent
  - Input: historical consumption patterns (7-30 days)
  - Output: Top 3 peak hours + discharge recommendations
  - Status: ⏸️ PENDING

- [ ] **Task 2.2.2:** Write peak agent GPT prompt
  - Focus: "Find 3 hours with highest historical consumption during 06:00-23:00"
  - Calculate discharge needed to reach 5 kW target
  - Add 30% safety buffer
  - Output structured JSON
  - Status: ⏸️ PENDING

- [ ] **Task 2.2.3:** Test peak agent standalone
  - Feed Feb historical data
  - Verify it identifies hours 17-19 as top peaks
  - Check discharge calculations are correct
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Peak agent correctly identifies top 3 historical peak hours
- Discharge calculations are accurate (+30% buffer)
- Returns structured JSON recommendations

---

### Story 2.3: Arbitrage Agent (GPT or Algorithm)
**Goal:** Find profitable charge/discharge opportunities based on prices

**Decision Point:** Should this be GPT-based or algorithm-based?
- Algorithm: Faster, deterministic, free
- GPT: Can consider complex factors, learn patterns

**Recommended:** Start with algorithm, add GPT enhancement later

- [ ] **Task 2.3.1:** Create ArbitrageAgent class
  - File: `agents/arbitrage_agent.py`
  - Input: 24-48h price forecast, night charge cost
  - Output: Profitable discharge opportunities
  - Status: ⏸️ PENDING

- [ ] **Task 2.3.2:** Implement profit calculation
  - Formula: `profit = (discharge_price - charge_price) × kwh × 0.95`
  - Filter: Only recommend if profit > 3 SEK/hour
  - Sort by profit density (SEK per kWh)
  - Status: ⏸️ PENDING

- [ ] **Task 2.3.3:** Test arbitrage agent standalone
  - Feed Feb price data
  - Verify it finds high-price hours (>2 SEK/kWh)
  - Check profit calculations
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Agent identifies profitable arbitrage opportunities
- Profit calculations are accurate
- Recommendations sorted by value density

---

### Story 2.4: Solar Self-Consumption Agent (GPT or Algorithm)
**Goal:** Maximize solar usage and minimize grid import

**Note:** User currently has no solar, so this is lower priority

- [ ] **Task 2.4.1:** Create SolarAgent class (stub for now)
  - File: `agents/solar_agent.py`
  - Return empty recommendations if solar_capacity = 0
  - Status: ⏸️ PENDING (Low priority)

- [ ] **Task 2.4.2:** Implement solar logic (future)
  - Charge from excess solar
  - Discharge to complement solar
  - Maximize self-consumption
  - Status: 🔮 FUTURE

**Acceptance Criteria:**
- Stub agent returns empty recommendations (no solar)
- Architecture supports future solar implementation

---

## Epic 3: Implement Orchestrator

### Story 3.1: Value Calculator (Core Logic)
**Goal:** Calculate SEK value for different discharge strategies

- [ ] **Task 3.1.1:** Create ValueCalculator class
  - File: `agents/value_calculator.py`
  - Methods:
    - `calculate_peak_value(kw_reduction, is_in_top3)` → SEK
    - `calculate_self_consumption_value(discharge_kwh, price)` → SEK
    - `calculate_arbitrage_value(discharge_kwh, price_diff)` → SEK
    - `calculate_total_value(hour_data, strategies)` → SEK
  - Status: ⏸️ PENDING

- [ ] **Task 3.1.2:** Implement peak shaving value calculation
  - If `is_in_top3`: value = kw_reduction × 60 SEK/kW/month ÷ 30 days
  - If not in top 3: value = 0
  - Status: ⏸️ PENDING

- [ ] **Task 3.1.3:** Implement self-consumption value calculation
  - Value = price_sek_kwh × discharge_kwh
  - Consider battery charge cost
  - Net value = (price - charge_cost) × discharge_kwh
  - Status: ⏸️ PENDING

- [ ] **Task 3.1.4:** Test value calculator with examples
  - Scenario 1: Normal day (1.2 SEK/kWh, 12 kW peak)
  - Scenario 2: Extreme price (5.8 SEK/kWh, 8 kW load)
  - Verify calculations match expected values from architecture doc
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Value calculator produces accurate SEK values
- All three value types calculated correctly
- Test scenarios pass

---

### Story 3.2: Orchestrator Agent (GPT-based)
**Goal:** Combine all recommendations and make final decisions

**Decision Point:** GPT-based or Algorithm-based orchestrator?
- **Recommended:** Start with GPT (flexible, handles edge cases)
- Future: Add algorithm fallback option

- [ ] **Task 3.2.1:** Create Orchestrator class
  - File: `agents/orchestrator.py`
  - Input: All agent recommendations + peak tracker + constraints
  - Output: Final 24h plan with reasoning
  - Status: ⏸️ PENDING

- [ ] **Task 3.2.2:** Write orchestrator GPT prompt
  - Focus: "Calculate SEK value for each strategy, pick maximum"
  - Include peak value, self-consumption value, arbitrage value
  - Respect battery capacity constraints
  - Return structured 24h plan
  - Status: ⏸️ PENDING

- [ ] **Task 3.2.3:** Implement constraint checking
  - Battery capacity limit (25 kWh)
  - Power limit (12 kW)
  - SOC limits (5-95%)
  - Ensure no over-allocation
  - Status: ⏸️ PENDING

- [ ] **Task 3.2.4:** Add reasoning/explanation output
  - For each hour, explain why action was chosen
  - Example: "Hour 18: Discharge 12 kW. Peak value (14 SEK) + Self-consumption (22 SEK) = 36 SEK total"
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Orchestrator receives all agent inputs
- Makes value-maximizing decisions
- Respects all constraints
- Provides clear reasoning

---

### Story 3.3: Integration with Main Simulator
**Goal:** Replace single GPT call with multi-agent system

- [ ] **Task 3.3.1:** Create multi-agent coordinator
  - File: `battery_simulator.py` - add new method `_create_multi_agent_plan()`
  - Call all agents in sequence
  - Collect recommendations
  - Pass to orchestrator
  - Return final plan
  - Status: ⏸️ PENDING

- [ ] **Task 3.3.2:** Add feature flag for multi-agent mode
  - Config: `use_multi_agent` (default: False for now)
  - If False: use old single-GPT approach
  - If True: use new multi-agent approach
  - Status: ⏸️ PENDING

- [ ] **Task 3.3.3:** Update daily planning call
  - Replace `_create_daily_plan()` logic
  - Use multi-agent coordinator when enabled
  - Keep backward compatibility
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Multi-agent system integrates with existing simulator
- Feature flag allows A/B testing
- Old approach still works (backward compatible)

---

## Epic 4: Testing & Optimization

### Story 4.1: Compare Single-GPT vs Multi-Agent
**Goal:** Measure improvement from multi-agent architecture

- [ ] **Task 4.1.1:** Run baseline simulation (current single-GPT)
  - Date: Feb 2025 (27 days)
  - Mode: Realistic
  - Record: Peak savings, arbitrage, self-consumption
  - Status: ⏸️ PENDING

- [ ] **Task 4.1.2:** Run multi-agent simulation (same period)
  - Date: Feb 2025 (27 days)
  - Mode: Realistic
  - Record: Peak savings, arbitrage, self-consumption
  - Status: ⏸️ PENDING

- [ ] **Task 4.1.3:** Compare results side-by-side
  - Create comparison table
  - Calculate improvement percentage
  - Identify which strategy improved most
  - Status: ⏸️ PENDING

- [ ] **Task 4.1.4:** Document findings
  - File: `docs/results-comparison.md`
  - Include metrics, charts, insights
  - Decision: Keep multi-agent or revert?
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Both approaches tested on same data
- Results compared objectively
- Decision documented

---

### Story 4.2: Optimize Prompts and Logic
**Goal:** Fine-tune agent prompts for better performance

- [ ] **Task 4.2.1:** Analyze failed decisions
  - Find days where peak shaving failed (0 kW reduction)
  - Check what orchestrator decided
  - Identify prompt improvements
  - Status: ⏸️ PENDING

- [ ] **Task 4.2.2:** Tune safety buffers
  - Test different buffer values: 20%, 30%, 40%
  - Find optimal balance between over/under reservation
  - Status: ⏸️ PENDING

- [ ] **Task 4.2.3:** Optimize value calculations
  - Verify peak value formula matches actual savings
  - Adjust if needed
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Prompts refined based on real results
- Buffers optimized for best performance
- Value calculations validated

---

### Story 4.3: Full Year Simulation
**Goal:** Test multi-agent system on complete annual data

- [ ] **Task 4.3.1:** Run full year simulation (realistic mode)
  - Clear date range filters
  - Use all available Tibber data
  - Runtime: ~2-3 hours
  - Status: ⏸️ PENDING

- [ ] **Task 4.3.2:** Run full year simulation (perfect knowledge mode)
  - Same data, perfect mode
  - Compare to realistic mode
  - Calculate "AI gap"
  - Status: ⏸️ PENDING

- [ ] **Task 4.3.3:** Analyze annual results
  - Total peak shaving savings
  - Total arbitrage savings
  - Total self-consumption savings
  - Monthly breakdown
  - Status: ⏸️ PENDING

- [ ] **Task 4.3.4:** Calculate final ROI
  - Annual savings (without FCR)
  - Add FCR estimate (10,000 SEK/year)
  - Calculate payback period
  - Compare to salesmen's "3-4 years" claim
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Full year simulated successfully
- Annual savings calculated
- ROI matches or beats salesmen's claims (with FCR)

---

## Epic 5: UI/UX Improvements

### Story 5.1: Enhanced Results Display
**Goal:** Show detailed breakdown of savings and decisions

- [ ] **Task 5.1.1:** Add monthly breakdown table
  - Show peak shaving by month
  - Show arbitrage by month
  - Highlight best/worst months
  - Status: ⏸️ PENDING

- [ ] **Task 5.1.2:** Add value breakdown pie chart
  - Peak shaving: X SEK (%)
  - Arbitrage: Y SEK (%)
  - Self-consumption: Z SEK (%)
  - Status: ⏸️ PENDING

- [ ] **Task 5.1.3:** Add "AI gap" visualization
  - Bar chart: Realistic vs Perfect
  - Show improvement potential
  - Status: ⏸️ PENDING

- [ ] **Task 5.1.4:** Add decision explanation view
  - Show hourly decisions with reasoning
  - Example: "Hour 18: Discharged 12 kW because peak (14 SEK) + self-consumption (22 SEK) = 36 SEK value"
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- Results are visually clear and informative
- User understands where savings come from
- Decision reasoning is transparent

---

### Story 5.2: Configuration UI
**Goal:** Allow user to configure multi-agent system

- [ ] **Task 5.2.1:** Add multi-agent toggle
  - Checkbox: "Använd multi-agent system (experimentell)"
  - Explanation tooltip
  - Status: ⏸️ PENDING

- [ ] **Task 5.2.2:** Add AI provider selector
  - Dropdown: OpenAI / Claude / Groq / Ollama / Algorithm
  - Show cost estimate per provider
  - Status: ⏸️ PENDING

- [ ] **Task 5.2.3:** Add advanced settings (collapsible)
  - Safety buffer percentage
  - Peak threshold (5 kW configurable)
  - Minimum arbitrage profit (3 SEK configurable)
  - Status: ⏸️ PENDING

**Acceptance Criteria:**
- User can enable/disable multi-agent
- User can choose AI provider
- Advanced settings available but not overwhelming

---

## Epic 6: Production Readiness (Future)

### Story 6.1: Multiple AI Provider Support
**Goal:** Support OpenAI, Anthropic, Groq, Ollama

- [ ] **Task 6.1.1:** Abstract AI client interface
- [ ] **Task 6.1.2:** Implement OpenAI client
- [ ] **Task 6.1.3:** Implement Anthropic client (Claude)
- [ ] **Task 6.1.4:** Implement Groq client (Llama)
- [ ] **Task 6.1.5:** Implement Ollama client (local)
- [ ] **Task 6.1.6:** Add fallback logic (if one fails, try another)

**Status:** 🔮 FUTURE

---

### Story 6.2: Learning Agent
**Goal:** Adapt predictions based on past performance

- [ ] **Task 6.2.1:** Track prediction accuracy
- [ ] **Task 6.2.2:** Implement buffer adjustment logic
- [ ] **Task 6.2.3:** Create learning agent
- [ ] **Task 6.2.4:** Integrate with orchestrator

**Status:** 🔮 FUTURE

---

### Story 6.3: FCR Revenue Integration
**Goal:** Add stödtjänster revenue to ROI calculation

- [ ] **Task 6.3.1:** Research FCR-N/D requirements
- [ ] **Task 6.3.2:** Calculate eligibility (25 kWh battery qualifies)
- [ ] **Task 6.3.3:** Estimate annual revenue (5,000-15,000 SEK)
- [ ] **Task 6.3.4:** Add to ROI calculation
- [ ] **Task 6.3.5:** Add toggle: "Include FCR revenue estimate"

**Status:** 🔮 FUTURE

---

## Progress Tracking

### Current Sprint: Foundation & Baseline

**Completed:**
- ✅ Architecture design documented
- ✅ Removed consumption forecast from GPT prompt (realistic mode)
- ✅ Updated GPT prompt to use historical patterns

**In Progress:**
- ⏸️ Waiting for user to run February baseline test

**Next Up:**
- Implement simulation mode toggle
- Create agents directory structure
- Implement Peak Tracker

---

## Success Metrics

### Phase 1 Success (Baseline):
- [ ] Simulation runs in realistic mode (no cheating)
- [ ] February peak shaving > 2,000 SEK
- [ ] Battery discharges during actual peak hours (not spread across 11 hours)

### Phase 2 Success (Multi-Agent):
- [ ] Peak shaving improves by 50%+ vs single-GPT
- [ ] Battery concentrates discharge on top 3 peaks
- [ ] Self-consumption activated during extreme prices (>3 SEK/kWh)

### Phase 3 Success (Full Year):
- [ ] Annual savings > 8,000 SEK (without FCR)
- [ ] Annual savings > 18,000 SEK (with FCR estimate)
- [ ] Payback period: 4-5 years (matches salesmen's claim)
- [ ] "AI gap" < 30% (realistic mode achieves 70%+ of perfect mode)

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Multi-agent worse than single-GPT | High | Keep feature flag, easy rollback |
| GPT API costs too high | Medium | Support algorithm fallback mode |
| Simulation takes too long (full year) | Low | Add progress streaming, partial saves |
| Historical patterns not predictive | High | Implement learning agent, adjust buffers |
| Orchestrator makes poor trade-offs | High | Add decision logging, manual review mode |

---

## Notes

- User has no solar panels currently (solar agent low priority)
- User's peaks are from household consumption during E.ON hours (06:00-23:00)
- Tesla charging happens at night (00:00-06:00, outside E.ON measurement)
- E.ON uses top-3 average method for effect tariff calculation
- Battery: 25 kWh Dyness Stack 100 + Solis 12 kW inverter
- Target grid import: 5 kW during E.ON hours

---

**Last Updated:** 2025-10-24
**Next Review:** After baseline testing complete
