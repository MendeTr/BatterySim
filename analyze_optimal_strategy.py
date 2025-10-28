#!/usr/bin/env python3
"""
Optimal Strategy Analyzer
==========================

Calculates which reserve strategy maximizes total ROI by analyzing:
1. Peak shaving savings at different reserve levels
2. Arbitrage profit at different reserve levels  
3. Total ROI = peak_shaving + arbitrage + self_consumption

The goal: Find the optimal balance between:
- Reserving capacity for unpredictable peaks (peak shaving value)
- Using capacity for arbitrage (arbitrage profit)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys

# E.ON effect tariff parameters
EFFECT_TARIFF_SEK_KW_MONTH = 60.0  # 60 SEK per kW per month
EON_HOURS = range(6, 23)  # 06:00-22:59 measurement hours

class StrategyAnalyzer:
    """Analyzes different battery reserve strategies to find optimal ROI"""
    
    def __init__(self, df: pd.DataFrame, battery_capacity_kwh: float = 25.0):
        """
        Initialize analyzer with consumption data
        
        Args:
            df: DataFrame with columns: timestamp_local, load_kwh, price_sek_per_kwh
            battery_capacity_kwh: Battery capacity in kWh
        """
        self.df = df.copy()
        self.capacity = battery_capacity_kwh
        
        # Convert timestamp to datetime if needed
        if 'timestamp_local' in self.df.columns:
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp_local'])
        else:
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
            
        self.df['hour'] = self.df['timestamp'].dt.hour
        self.df['month'] = self.df['timestamp'].dt.to_period('M')
        
        # Calculate consumption in kW (assuming hourly data)
        self.df['consumption_kw'] = self.df['load_kwh']
        
        # Filter E.ON measurement hours
        self.df['is_eon_hour'] = self.df['hour'].isin(EON_HOURS)
        
    def calculate_baseline_peaks(self) -> dict:
        """Calculate current peak situation without battery"""
        
        # Get E.ON hour consumption only
        eon_df = self.df[self.df['is_eon_hour']].copy()
        
        # Calculate monthly top-3 averages
        monthly_peaks = {}
        for month in eon_df['month'].unique():
            month_data = eon_df[eon_df['month'] == month]
            top3 = month_data.nlargest(3, 'consumption_kw')['consumption_kw'].mean()
            monthly_peaks[str(month)] = top3
            
        avg_peak = np.mean(list(monthly_peaks.values()))
        
        # Annual cost
        annual_cost = avg_peak * EFFECT_TARIFF_SEK_KW_MONTH * 12
        
        return {
            'monthly_peaks': monthly_peaks,
            'average_peak_kw': avg_peak,
            'annual_cost_sek': annual_cost
        }
    
    def simulate_strategy(self, 
                         reserve_percentile: float = 80,
                         night_charge_threshold: float = 0.50,
                         target_soc_percent: float = 0.60) -> dict:
        """
        Simulate a specific battery strategy
        
        Args:
            reserve_percentile: What percentile of consumption to reserve for (80 = 80th percentile)
            night_charge_threshold: Max price to charge at night (SEK/kWh)
            target_soc_percent: Target SOC after night charging (0.60 = 60%)
            
        Returns:
            Dictionary with:
                - peak_shaving_sek: Annual savings from peak reduction
                - arbitrage_sek: Annual profit from arbitrage
                - total_savings_sek: Combined savings
                - avg_peak_with_battery: Average peak with this strategy
                - num_missed_peaks: Number of peaks that weren't reduced
        """
        
        # Calculate reserve capacity needed based on percentile
        eon_consumption = self.df[self.df['is_eon_hour']]['consumption_kw']
        reserve_threshold_kw = np.percentile(eon_consumption, reserve_percentile)
        reserve_needed_kwh = max(0, reserve_threshold_kw - 5.0)  # Reserve to reduce to 5 kW target
        
        # Simulate battery operation
        soc_kwh = 0  # Start empty
        monthly_peaks_with_battery = {}
        total_arbitrage_profit = 0
        missed_peaks = 0
        
        daily_data = self.df.groupby(self.df['timestamp'].dt.date)
        
        for date, day_df in daily_data:
            day_df = day_df.sort_values('hour')
            
            # Night charging phase (00:00-05:59)
            night_hours = day_df[day_df['hour'] < 6]
            cheapest_night_price = night_hours['price_sek_per_kwh'].min() if len(night_hours) > 0 else 999
            
            if cheapest_night_price <= night_charge_threshold:
                # Charge to target, but leave room for reserves
                target_soc = self.capacity * target_soc_percent
                can_charge = min(
                    target_soc - soc_kwh,  # Room to target
                    12.0 * len(night_hours)  # Power limit × hours
                )
                
                if can_charge > 0:
                    # Calculate arbitrage potential
                    charge_cost = cheapest_night_price * can_charge
                    soc_kwh += can_charge
                    
                    # Estimate discharge profit (use day's avg price as estimate)
                    day_hours = day_df[day_df['hour'].isin(EON_HOURS)]
                    avg_day_price = day_hours['price_sek_per_kwh'].mean()
                    
                    # Simple arbitrage: (discharge_price - charge_price) × kWh × efficiency
                    if avg_day_price > cheapest_night_price:
                        potential_profit = (avg_day_price - cheapest_night_price) * can_charge * 0.95
                        # But only count if we actually discharge for arbitrage (not peak shaving)
                        # For now, assume 30% goes to arbitrage
                        total_arbitrage_profit += potential_profit * 0.3
            
            # Day operation (06:00-22:59) - Peak shaving focus
            day_hours = day_df[day_df['is_eon_hour']].copy()
            
            for idx, row in day_hours.iterrows():
                consumption_kw = row['consumption_kw']
                
                # Should we discharge to reduce peak?
                if consumption_kw > 5.0 and soc_kwh > 0:
                    # How much do we need to discharge?
                    needed_discharge = consumption_kw - 5.0
                    
                    # How much can we discharge?
                    available = min(
                        soc_kwh,  # What we have
                        needed_discharge,  # What we need
                        12.0  # Power limit
                    )
                    
                    # Discharge
                    soc_kwh -= available
                    reduced_consumption = consumption_kw - available
                else:
                    reduced_consumption = consumption_kw
                
                # Track peak for this month
                month = row['month']
                if month not in monthly_peaks_with_battery:
                    monthly_peaks_with_battery[month] = []
                monthly_peaks_with_battery[month].append(reduced_consumption)
                
                # Did we miss a peak? (consumption still > 8 kW)
                if reduced_consumption > 8.0:
                    missed_peaks += 1
        
        # Calculate monthly top-3 averages with battery
        monthly_top3_with_battery = {}
        for month, consumptions in monthly_peaks_with_battery.items():
            top3 = sorted(consumptions, reverse=True)[:3]
            monthly_top3_with_battery[str(month)] = np.mean(top3)
        
        avg_peak_with_battery = np.mean(list(monthly_top3_with_battery.values()))
        
        # Calculate peak shaving savings
        baseline = self.calculate_baseline_peaks()
        peak_reduction_kw = baseline['average_peak_kw'] - avg_peak_with_battery
        peak_shaving_annual = peak_reduction_kw * EFFECT_TARIFF_SEK_KW_MONTH * 12
        
        # Total savings
        total_savings = peak_shaving_annual + total_arbitrage_profit
        
        return {
            'reserve_percentile': reserve_percentile,
            'night_charge_threshold': night_charge_threshold,
            'target_soc_percent': target_soc_percent,
            'reserve_needed_kwh': reserve_needed_kwh,
            'peak_shaving_sek': peak_shaving_annual,
            'arbitrage_sek': total_arbitrage_profit,
            'total_savings_sek': total_savings,
            'avg_peak_baseline': baseline['average_peak_kw'],
            'avg_peak_with_battery': avg_peak_with_battery,
            'peak_reduction_kw': peak_reduction_kw,
            'num_missed_peaks': missed_peaks
        }
    
    def find_optimal_strategy(self) -> pd.DataFrame:
        """
        Test multiple strategies to find the optimal one
        
        Returns:
            DataFrame with all strategies sorted by total_savings_sek
        """
        
        strategies = []
        
        # Test different combinations
        for reserve_pct in [70, 75, 80, 85, 90, 95]:
            for charge_threshold in [0.35, 0.40, 0.45, 0.50, 0.55]:
                for target_soc in [0.50, 0.60, 0.70, 0.80]:
                    
                    result = self.simulate_strategy(
                        reserve_percentile=reserve_pct,
                        night_charge_threshold=charge_threshold,
                        target_soc_percent=target_soc
                    )
                    strategies.append(result)
        
        # Convert to DataFrame and sort
        results_df = pd.DataFrame(strategies)
        results_df = results_df.sort_values('total_savings_sek', ascending=False)
        
        return results_df


def main():
    """Run optimal strategy analysis"""
    
    print("=" * 80)
    print("OPTIMAL BATTERY STRATEGY ANALYZER")
    print("=" * 80)
    print()
    
    # Load data
    print("📊 Loading Tibber consumption data...")
    try:
        df = pd.read_csv('tibber_no_ev.csv')
        print(f"   ✓ Loaded {len(df)} hours of data")
    except FileNotFoundError:
        print("   ✗ Error: tibber_no_ev.csv not found")
        print("   Please ensure the data file is in the current directory")
        sys.exit(1)
    
    # Initialize analyzer
    analyzer = StrategyAnalyzer(df, battery_capacity_kwh=25.0)
    
    # Calculate baseline (no battery)
    print("\n🔍 Analyzing baseline (no battery)...")
    baseline = analyzer.calculate_baseline_peaks()
    print(f"   Average peak: {baseline['average_peak_kw']:.2f} kW")
    print(f"   Annual cost: {baseline['annual_cost_sek']:.0f} SEK")
    
    # Find optimal strategy
    print("\n🎯 Testing 120 different strategies...")
    print("   (This may take a minute...)")
    results = analyzer.find_optimal_strategy()
    
    # Show top 10 strategies
    print("\n" + "=" * 80)
    print("TOP 10 STRATEGIES (by total savings)")
    print("=" * 80)
    print()
    
    top10 = results.head(10)
    
    for i, row in top10.iterrows():
        print(f"\n{'=' * 80}")
        print(f"RANK #{len(top10) - len(top10[top10.index >= i]) + 1}")
        print(f"{'=' * 80}")
        print(f"Reserve Strategy:     {row['reserve_percentile']:.0f}th percentile (reserve {row['reserve_needed_kwh']:.1f} kWh)")
        print(f"Night Charge:         Only when price < {row['night_charge_threshold']:.2f} SEK/kWh")
        print(f"Target SOC:           {row['target_soc_percent']*100:.0f}% ({row['target_soc_percent']*25:.1f} kWh)")
        print()
        print(f"Results:")
        print(f"  Peak reduction:     {baseline['average_peak_kw']:.2f} → {row['avg_peak_with_battery']:.2f} kW ({row['peak_reduction_kw']:.2f} kW saved)")
        print(f"  Peak shaving:       {row['peak_shaving_sek']:.0f} SEK/year")
        print(f"  Arbitrage profit:   {row['arbitrage_sek']:.0f} SEK/year")
        print(f"  Missed peaks:       {row['num_missed_peaks']:.0f} times")
        print(f"  {'─' * 40}")
        print(f"  TOTAL SAVINGS:      {row['total_savings_sek']:.0f} SEK/year ⭐")
    
    # Save detailed results
    results.to_csv('strategy_analysis_results.csv', index=False)
    print(f"\n💾 Full results saved to: strategy_analysis_results.csv")
    
    # Show key insights
    print("\n" + "=" * 80)
    print("KEY INSIGHTS")
    print("=" * 80)
    
    best = results.iloc[0]
    current_result = analyzer.simulate_strategy(
        reserve_percentile=80,
        night_charge_threshold=0.50,
        target_soc_percent=0.80
    )
    
    improvement = best['total_savings_sek'] - current_result['total_savings_sek']
    improvement_pct = (improvement / current_result['total_savings_sek']) * 100
    
    print(f"\n📈 Your current strategy achieves: {current_result['total_savings_sek']:.0f} SEK/year")
    print(f"   Peak shaving: {current_result['peak_shaving_sek']:.0f} SEK")
    print(f"   Arbitrage: {current_result['arbitrage_sek']:.0f} SEK")
    
    print(f"\n🎯 Optimal strategy achieves: {best['total_savings_sek']:.0f} SEK/year")
    print(f"   Peak shaving: {best['peak_shaving_sek']:.0f} SEK")
    print(f"   Arbitrage: {best['arbitrage_sek']:.0f} SEK")
    
    print(f"\n💡 Potential improvement: +{improvement:.0f} SEK/year ({improvement_pct:.1f}% better)")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    if best['reserve_percentile'] > 85:
        print("\n✅ Your optimal strategy is CONSERVATIVE (high reserves)")
        print("   → You have many unpredictable peaks")
        print("   → Peak shaving is more valuable than arbitrage")
        print("   → Reserve more capacity for peak reduction")
    elif best['reserve_percentile'] < 75:
        print("\n✅ Your optimal strategy is AGGRESSIVE (low reserves)")
        print("   → Your peaks are predictable")
        print("   → Arbitrage is more valuable than extra peak shaving")
        print("   → Use capacity for trading, not just reserves")
    else:
        print("\n✅ Your optimal strategy is BALANCED")
        print("   → Mix of peak shaving and arbitrage")
        print("   → Reserve enough for common peaks")
        print("   → Use excess capacity for trading")
    
    print(f"\n📋 Configuration:")
    print(f"   - Reserve for {best['reserve_percentile']:.0f}th percentile peaks")
    print(f"   - Charge when price < {best['night_charge_threshold']:.2f} SEK/kWh")
    print(f"   - Target {best['target_soc_percent']*100:.0f}% SOC ({best['target_soc_percent']*25:.1f} kWh)")
    
    print("\n" + "=" * 80)
    print()


if __name__ == "__main__":
    main()
