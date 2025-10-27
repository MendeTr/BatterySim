# Battery Economics & Cost Model

**Date:** 2025-10-24
**Purpose:** Document correct cost calculations for arbitrage, self-consumption, and export

---

## Current Issues

### Problem 1: Export Transfer Fee Not Applied
**Current code (line 1193):**
```python
export_rate = 0.377  # Based on actual export revenue data
df['spot_revenue_export'] = df['grid_export_kwh'] * df['spot_price_sek_kwh'] * export_rate
```

**Issue:** This applies a flat 37.7% reduction, but the user specified they pay **0.40 SEK/kWh transfer fee** for exports.

**User's statement:**
> "For every kWh sold I pay 0.4 kr transfer, so arbitrage should be considered carefully. Same with solar - if I sell during summer I always sell current price - transfer rate."

### Problem 2: Self-Consumption vs Arbitrage Economics Unclear

Need to clarify the economics of:
1. **Self-consumption (discharge to cover own usage)** - saves full cost
2. **Arbitrage (discharge to export back to grid)** - earns spot price minus transfer fee
3. **Peak shaving (discharge to reduce grid import)** - saves effect tariff

---

## Swedish Electricity Cost Structure

### When IMPORTING from grid (buying electricity):
```
Total cost = Spot price + Grid fee + Energy tax + VAT
```

**Example with 1.20 SEK/kWh spot price:**
```
Spot price:     1.20 SEK/kWh
Grid fee:       0.42 SEK/kWh  (överföringsavgift)
Energy tax:     0.40 SEK/kWh  (energiskatt)
────────────────────────────
Subtotal:       2.02 SEK/kWh
VAT (25%):      0.51 SEK/kWh
────────────────────────────
Total paid:     2.53 SEK/kWh
```

### When EXPORTING to grid (selling electricity):
```
Revenue = Spot price - Transfer fee
```

**Example with 1.20 SEK/kWh spot price:**
```
Spot price:         1.20 SEK/kWh
Transfer fee:      -0.42 SEK/kWh  (överföringsavgift för export - SAME as import!)
────────────────────────────────
Net revenue:        0.78 SEK/kWh
```

**Important:**
- You do NOT get grid fee, energy tax, or VAT back when exporting!
- Transfer fee is the SAME for import and export (0.42 SEK/kWh in user's case)

### When SELF-CONSUMING (using battery instead of grid):
```
Savings = Full import cost (spot + grid fee + energy tax + VAT)
```

**Example with 1.20 SEK/kWh spot price:**
```
Avoided cost:   2.53 SEK/kWh  (full import cost)
Battery cost:   0.60 SEK/kWh  (night charging cost)
────────────────────────────
Net savings:    1.93 SEK/kWh
```

---

## Corrected Cost Model

### 1. Grid Import Cost (Buying)
```python
def calculate_import_cost(spot_price, grid_fee, energy_tax, vat_rate):
    """Calculate total cost per kWh when importing from grid"""
    subtotal = spot_price + grid_fee + energy_tax
    total_with_vat = subtotal * (1 + vat_rate)
    return total_with_vat

# Example:
import_cost = calculate_import_cost(
    spot_price=1.20,
    grid_fee=0.42,
    energy_tax=0.40,
    vat_rate=0.25
)
# = (1.20 + 0.42 + 0.40) × 1.25 = 2.525 SEK/kWh
```

### 2. Grid Export Revenue (Selling)
```python
def calculate_export_revenue(spot_price, transfer_fee=0.42):
    """Calculate net revenue per kWh when exporting to grid"""
    net_revenue = spot_price - transfer_fee
    return max(0, net_revenue)  # Can't be negative!

# Example 1: Normal price
export_revenue = calculate_export_revenue(spot_price=1.20, transfer_fee=0.42)
# = 1.20 - 0.42 = 0.78 SEK/kWh

# Example 2: Very low price
export_revenue = calculate_export_revenue(spot_price=0.30, transfer_fee=0.42)
# = max(0, 0.30 - 0.42) = 0 SEK/kWh (don't export, too expensive!)
```

**Critical:** If spot price < 0.42 SEK/kWh, exporting LOSES money! Better to use battery for self-consumption.

### 3. Self-Consumption Savings
```python
def calculate_self_consumption_savings(spot_price, grid_fee, energy_tax, vat_rate, battery_charge_cost):
    """Calculate savings per kWh when using battery instead of grid import"""
    import_cost = calculate_import_cost(spot_price, grid_fee, energy_tax, vat_rate)
    net_savings = import_cost - battery_charge_cost
    return net_savings

# Example:
savings = calculate_self_consumption_savings(
    spot_price=1.20,
    grid_fee=0.42,
    energy_tax=0.40,
    vat_rate=0.25,
    battery_charge_cost=0.60  # Charged at night (0.50 spot + fees)
)
# = 2.525 - 0.60 = 1.925 SEK/kWh savings
```

### 4. Arbitrage Profit (Export strategy)
```python
def calculate_arbitrage_profit(discharge_price, charge_price, transfer_fee=0.40, efficiency=0.95):
    """Calculate profit per kWh from arbitrage (charge low, export high)"""
    export_revenue = max(0, discharge_price - transfer_fee)
    charge_cost = charge_price  # Simplified (should include grid fee + tax)
    profit = (export_revenue - charge_cost) * efficiency
    return profit

# Example: Good arbitrage opportunity
profit = calculate_arbitrage_profit(
    discharge_price=3.00,  # High price hour
    charge_price=0.60,     # Night charging (spot + fees)
    transfer_fee=0.40,
    efficiency=0.95
)
# = (3.00 - 0.40 - 0.60) × 0.95 = 1.90 SEK/kWh profit

# Example: Marginal arbitrage
profit = calculate_arbitrage_profit(
    discharge_price=1.20,
    charge_price=0.60,
    transfer_fee=0.40,
    efficiency=0.95
)
# = (1.20 - 0.40 - 0.60) × 0.95 = 0.19 SEK/kWh profit (barely worth it)

# Example: BAD arbitrage (loss!)
profit = calculate_arbitrage_profit(
    discharge_price=0.80,  # Low price
    charge_price=0.60,
    transfer_fee=0.40,
    efficiency=0.95
)
# = (0.80 - 0.40 - 0.60) × 0.95 = -0.19 SEK/kWh (LOSS!)
```

---

## Decision Rules for Battery Discharge

### Rule 1: When to discharge for SELF-CONSUMPTION (covering own usage)
```python
# Calculate value of using battery instead of grid import
self_consumption_value = import_cost - battery_charge_cost

# Example: 1.20 SEK/kWh spot price
import_cost = (1.20 + 0.42 + 0.40) × 1.25 = 2.53 SEK/kWh
battery_charge_cost = 0.60 SEK/kWh
self_consumption_value = 2.53 - 0.60 = 1.93 SEK/kWh

# Decision: ALWAYS discharge for self-consumption (unless saving for peak)
```

**Priority:** Self-consumption is almost ALWAYS profitable (1.93 SEK/kWh savings)

### Rule 2: When to discharge for ARBITRAGE (exporting to grid)
```python
# Calculate profit from exporting
export_revenue = spot_price - 0.40  # Transfer fee
arbitrage_profit = (export_revenue - battery_charge_cost) × 0.95

# Example: 3.00 SEK/kWh spot price
export_revenue = 3.00 - 0.40 = 2.60 SEK/kWh
arbitrage_profit = (2.60 - 0.60) × 0.95 = 1.90 SEK/kWh

# Decision: Only export if spot price > 1.50 SEK/kWh
# Below that, arbitrage profit < self-consumption value
```

**Threshold calculation:**
```
Break-even spot price for arbitrage:
(spot - 0.40 - 0.60) × 0.95 = 1.93  (self-consumption value)
spot - 1.00 = 1.93 / 0.95 = 2.03
spot = 3.03 SEK/kWh

Below 3.03 SEK/kWh: Self-consumption is better than arbitrage!
```

### Rule 3: When to discharge for PEAK SHAVING
```python
# Calculate value of reducing peak by 1 kW
peak_shaving_value_per_kw = 60 SEK/kW/month / 30 days = 2 SEK/kW/day

# Example: Reduce 12 kW peak to 5 kW (7 kW reduction)
peak_shaving_value = 7 kW × 2 SEK/kW/day = 14 SEK/day

# But you must discharge 7 kWh to achieve this:
battery_cost = 7 kWh × 0.60 SEK/kWh = 4.2 SEK
net_peak_shaving_value = 14 - 4.2 = 9.8 SEK

# Decision: ALWAYS prioritize peak shaving during E.ON hours if consumption > 8 kW
```

**Important:** Peak shaving value is PER DAY but counts toward monthly average!

---

## Combined Strategy Decision Tree

```
For each hour with consumption:

1. Is this during E.ON hours (06:00-23:00)?
   YES → Go to step 2
   NO → Go to step 4 (night hours)

2. Is consumption > 8 kW? (potential peak)
   YES → DISCHARGE for peak shaving (reduce to 5 kW target)
         Calculate: discharge = consumption - solar - 5
         Value = peak_shaving_value + self_consumption_value
   NO → Go to step 3

3. Is spot price > 3.00 SEK/kWh? (extreme price)
   YES → DISCHARGE for self-consumption (cover full consumption)
         Value = self_consumption_value (very high during extreme prices)
   NO → Is spot price > 1.50 SEK/kWh? (high price)
        YES → DISCHARGE for self-consumption (if battery available)
              Value = self_consumption_value
        NO → HOLD battery (save for peaks)

4. Night hours (00:00-05:59):
   Is spot price < 0.70 SEK/kWh? (cheap charging)
   YES → CHARGE battery to 80-95% for next day
   NO → HOLD
```

---

## Corrected Calculation Example

### Scenario: Hour 18 with 12 kW consumption, 3.00 SEK/kWh spot price

**Option A: Do nothing (buy from grid)**
```
Grid import: 12 kW
Cost: 12 × [(3.00 + 0.42 + 0.40) × 1.25] = 12 × 4.775 = 57.30 SEK
Peak tariff: 12 kW → 60 SEK/month = 2 SEK/day
Total cost: 59.30 SEK
```

**Option B: Discharge 7 kWh (reduce to 5 kW grid import)**
```
Grid import: 5 kW
Grid cost: 5 × 4.775 = 23.88 SEK
Battery cost: 7 kWh × 0.60 = 4.20 SEK
Peak tariff: 5 kW → 10 SEK/month = 0.33 SEK/day
Total cost: 28.41 SEK
Savings vs A: 59.30 - 28.41 = 30.89 SEK
```

**Option C: Discharge 12 kWh (full self-consumption, zero grid import)**
```
Grid import: 0 kW
Grid cost: 0 SEK
Battery cost: 12 kWh × 0.60 = 7.20 SEK
Peak tariff: 0 kW → 0 SEK
Total cost: 7.20 SEK
Savings vs A: 59.30 - 7.20 = 52.10 SEK ✅ BEST!
```

**Option D: Discharge 12 kWh + export 5 kWh (arbitrage)**
```
Grid import: 0 kW
Grid export: 5 kW
Grid cost: 0 SEK
Export revenue: 5 × (3.00 - 0.40) = 13.00 SEK
Battery cost: 17 kWh × 0.60 = 10.20 SEK
Peak tariff: 0 kW → 0 SEK
Total cost: 10.20 - 13.00 = -2.80 SEK (net revenue!)
Savings vs A: 59.30 + 2.80 = 62.10 SEK ✅✅ EVEN BETTER!
```

**Conclusion:** At 3.00 SEK/kWh spot price:
1. Discharge to cover consumption (Option C)
2. If battery has extra capacity, export for arbitrage (Option D)
3. Both peak shaving AND self-consumption value combined!

---

## What Needs to Change in Code

### Change 1: Export Revenue Calculation
**Current (WRONG):**
```python
export_rate = 0.377
df['spot_revenue_export'] = df['grid_export_kwh'] * df['spot_price_sek_kwh'] * export_rate
```

**Should be (CORRECT):**
```python
# Use the grid_fee_sek_kwh parameter from frontend (user-configurable)
df['spot_revenue_export'] = df['grid_export_kwh'] * (df['spot_price_sek_kwh'] - grid_fee_sek_kwh)
# Clip to zero (don't export if spot < transfer fee)
df['spot_revenue_export'] = df['spot_revenue_export'].clip(lower=0)
```

**Key point:** `grid_fee_sek_kwh` is passed as a parameter from the frontend, so user can configure their actual transfer rate!

### Change 2: Arbitrage Decision Logic
**Should check:**
```python
# Only export for arbitrage if profitable
export_revenue_per_kwh = spot_price - 0.40
arbitrage_profit = (export_revenue_per_kwh - charge_cost) * 0.95

if arbitrage_profit > 3.0:  # At least 3 SEK profit to justify battery degradation
    # Discharge for arbitrage
```

### Change 3: Self-Consumption Priority
**Should prioritize:**
1. Peak shaving (during E.ON hours if consumption > 8 kW)
2. Self-consumption during high prices (> 2.50 SEK/kWh spot)
3. Arbitrage only if spot > 3.00 SEK/kWh AND battery has excess capacity

### Change 4: Don't Export if Spot Price Too Low
```python
# If spot price < 0.40 SEK/kWh, exporting loses money!
if spot_price < TRANSFER_FEE_SEK_KWH:
    # Don't export! Use battery for self-consumption or hold
    grid_export = 0
```

---

## Impact on ROI Calculation

### Current Calculation (likely WRONG):
- Assumes export revenue = spot price × 37.7%
- This understates arbitrage profit at high prices
- But overstates it at low prices

### Corrected Calculation:
- Export revenue = max(0, spot price - 0.40)
- More accurate arbitrage profit
- Will show that arbitrage is only profitable during extreme prices (>3 SEK/kWh)

### Expected Changes in Results:
1. **Arbitrage savings will DECREASE** (only profitable at very high prices)
2. **Self-consumption savings will INCREASE** (prioritized over arbitrage)
3. **Peak shaving + self-consumption combined** will be the main value driver
4. **ROI will be more accurate** (closer to reality)

---

## Solar Export (Future Consideration)

When user adds solar panels:

**Summer day scenario:**
- Solar produces 8 kW at hour 12
- Consumption only 3 kW
- Excess: 5 kW

**Options:**
1. **Export excess solar immediately:** 5 kW × (spot - 0.40) SEK/kWh
2. **Charge battery from solar:** Store 5 kWh, use later for self-consumption
3. **Combined:** Charge battery first (up to capacity), export remainder

**Economic decision:**
```python
export_value = (spot_price - 0.40) × 5 kWh
storage_value = future_import_cost × 5 kWh × 0.95  # Battery efficiency

if storage_value > export_value:
    # Store in battery for later self-consumption
else:
    # Export immediately
```

Typically, storing solar in battery is MORE valuable because:
- Export: (1.20 - 0.40) = 0.80 SEK/kWh revenue
- Storage + use at evening: (2.53) × 0.95 = 2.40 SEK/kWh savings

**Storage is 3x more valuable than export!**

---

## Summary of Key Economics

| Strategy | Value per kWh | When to use |
|----------|---------------|-------------|
| **Peak Shaving** | 2 SEK/kW/day ÷ discharge | Always during E.ON hours if consumption > 8 kW |
| **Self-Consumption** | 1.93 SEK/kWh | Always during consumption hours (if battery available) |
| **Arbitrage (Export)** | 0.19-1.90 SEK/kWh | Only if spot > 3.00 SEK/kWh AND no consumption to cover |
| **Solar Storage** | 2.40 SEK/kWh | Always better than exporting solar |

**Golden Rule:** Self-consumption beats arbitrage almost always!

**Exception:** During extreme price spikes (>5 SEK/kWh), exporting can be very profitable if you have excess battery capacity after covering consumption.

---

**End of Cost Model Documentation**

*This document should be used to correct the battery simulator's economic calculations.*
