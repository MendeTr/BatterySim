# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Battery ROI Calculator** for the Swedish electricity market. It consists of:
1. A web application that simulates battery performance using real Tibber data
2. Advanced battery optimization algorithms (rule-based and GPT-powered)
3. Swedish market-specific calculations (effect tariffs, grid fees, stödtjänster)

The project aims to help Swedish homeowners evaluate battery investments and potentially expand to a hardware dongle product (similar to Sigen.ai).

## Development Commands

### Starting the Application
```bash
# Quick start (creates venv, installs deps, starts server)
./start.sh

# Manual start
python app.py
# Server runs on http://localhost:5001

# Open the web interface
# Simply open index.html in your browser (connects to localhost:5001)
```

### Installing Dependencies
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt
```

### Testing
```bash
# API health check
curl http://localhost:5001/api/health

# Test with sample data
# Upload sample_tibber_data.csv through the web interface
```

## Architecture

### Tech Stack
- **Backend**: Flask REST API (app.py)
- **Simulation Engine**: Pure Python with NumPy/Pandas (battery_simulator.py)
- **Frontend**: Single-page React app embedded in index.html with TailwindCSS
- **Optional**: GPT-4o-mini integration for intelligent arbitrage decisions

### Key Components

#### 1. Flask API (app.py)
- **Port**: 5001 (hardcoded in line 415)
- **Main endpoints**:
  - `POST /api/upload` - Upload Tibber CSV files
  - `POST /api/simulate` - Run battery simulation
  - `POST /api/stodtjanster/estimate` - Estimate FCR revenue
  - `GET /api/battery/presets` - Get battery configurations
  - `GET /api/network-operators` - Get Swedish grid operator data

#### 2. Battery Simulator (battery_simulator.py)
Two main classes:
- **BatteryROISimulator**: Core simulation engine
  - Simulates hour-by-hour battery operation (8760 hours/year)
  - Handles solar production, grid import/export, battery charging/discharging
  - Calculates effect tariff savings, ROI, payback period

- **GPTArbitrageAgent**: AI-powered arbitrage optimization (optional)
  - Requires `OPENAI_API_KEY` environment variable
  - Makes intelligent charge/discharge decisions
  - Falls back to rule-based system if API key missing

#### 3. Frontend (index.html)
- Single HTML file with embedded React components
- Uses TailwindCSS CDN for styling
- Connects to backend API via fetch()

### Data Flow

```
1. User uploads Tibber CSV → /api/upload → Stored in /tmp/uploads
2. User configures battery → Frontend form
3. User clicks "Beräkna ROI" → POST /api/simulate
4. Simulator loads CSV → Parses timestamps, consumption, spot prices
5. Adds solar production (real data or estimates)
6. Simulates 8760 hours:
   - Priority 1: Solar self-consumption
   - Priority 2: Peak shaving (reduce effect tariff)
   - Priority 3: Arbitrage (charge low, discharge high)
7. Calculates costs, ROI, payback period
8. Returns JSON report → Frontend displays results
```

### Battery Optimization Logic

The simulator uses a **priority-based strategy**:

1. **Self-consumption first**: Use solar energy directly when available
2. **Battery storage**: Charge battery from excess solar
3. **Peak shaving**: Discharge battery during high consumption (>7 kW) in peak hours (06:00-23:00)
4. **Night charging**: Charge battery during cheap night hours (00:00-06:00) to prepare for next day's peaks
5. **Arbitrage**: Only if GPT mode enabled or rule-based conditions met (price < 0.3 SEK/kWh to charge, > 2.0 SEK/kWh to discharge)
6. **Grid export**: Export excess solar when battery is full

**Critical insight**: Effect tariff savings are often larger than arbitrage gains. The battery power rating (kW) determines peak shaving capability.

### Swedish Market Specifics

- **Spot prices**: From Nord Pool (via Tibber CSV)
- **Grid fees**: ~0.38-0.48 SEK/kWh (varies by operator)
- **Energy tax**: ~0.40 SEK/kWh
- **VAT**: 25% on all electricity costs
- **Effect tariff**: 45-60 SEK/kW/month (measured during 06:00-23:00)
- **Export rate**: ~37.7% of spot price (realistic based on actual data)
- **Stödtjänster (FCR-N/D)**: 2000-2500 SEK/MW/hour market price, 70% availability, minus 25% aggregator fee

### Tibber CSV Format

Expected columns (multiple formats supported):
```
# Swedish format
Från, Till, Förbrukning, Kostnad, Spotpris

# English format
timestamp, consumption_kwh, spot_price_sek_kwh

# Extended format (with solar)
timestamp, consumption_kwh, spot_price_sek_kwh, solar_kwh, cost_sek, export_profit_sek
```

The simulator automatically detects and maps column names (see `load_tibber_data()` in battery_simulator.py:249-296).

## Important Implementation Details

### Battery Simulation Loop (battery_simulator.py:388-733)

The core simulation happens in `simulate_battery_operation()`:
- **State tracking**: Battery SOC (State of Charge) is tracked hour by hour
- **Efficiency losses**: Charging efficiency factor (default 0.95) applied
- **Power constraints**: Charge/discharge limited by battery power rating (kW)
- **Capacity constraints**: SOC stays between 0 and capacity (kWh)

**Peak shaving implementation** (lines 423-439):
```python
if consumption > 7.0 and is_peak_hours and soc > 0:
    available_discharge = min(soc, self.power)
    discharge = available_discharge
```

This is a simplified approach. For production, should consider:
- Historical peak patterns
- Forecasted consumption
- SOC preservation for later peaks

### GPT Arbitrage Agent (battery_simulator.py:9-214)

**Prompt engineering** (lines 71-155):
- Provides 24-hour price/consumption/solar forecasts
- Includes Swedish market context (fees, taxes, export rates)
- Uses structured decision framework with priorities
- Requests JSON output format

**Decision parsing** (lines 157-184):
- Extracts JSON from GPT response
- Validates action (charge/discharge/hold)
- Limits amount to battery power constraints
- Falls back to rule-based on parse failure

**Cost consideration**: GPT calls are expensive. Currently rate-limited to every 72 hours (line 487). Consider:
- Caching decisions for multiple hours
- Using smaller/cheaper models
- Only calling GPT for significant events (price spikes, high consumption forecasts)

### Effect Tariff Calculation (battery_simulator.py:681-708)

**Implementation**:
1. Group data by month
2. Find monthly peak consumption (without battery)
3. Find monthly peak grid import (with battery)
4. Calculate peak reduction per month (limited by battery power)
5. Average across months
6. Multiply by tariff rate (SEK/kW/month) × 12

**Important**: Effect tariff is measured 06:00-23:00 only, not 24/7.

### ROI Calculation (battery_simulator.py:1003-1044)

**Includes degradation model**:
- Years 1-5: 100% capacity (no degradation)
- Years 6-10: 1% degradation per year
- Years 11-15: 2% degradation per year

**Uses NPV (Net Present Value)** with 3% discount rate to account for time value of money.

## Configuration Files

- **requirements.txt**: Python dependencies (Flask, Pandas, NumPy, etc.)
- **start.sh**: Startup script for macOS/Linux
- **.env**: Optional file for OPENAI_API_KEY (for GPT arbitrage mode)

## Testing with Sample Data

The repository includes `sample_tibber_data.csv` for testing. It contains:
- 12 months of hourly data (8760 rows)
- Realistic Swedish consumption patterns
- Nord Pool spot prices
- Some solar production data

## Common Issues & Solutions

### Port Already in Use
If port 5001 is taken, change line 415 in app.py:
```python
app.run(debug=True, host='0.0.0.0', port=5001)  # Change 5001 to another port
```

### Missing OpenAI API Key
GPT arbitrage will fall back to rule-based system. This is expected behavior. To enable GPT:
```bash
export OPENAI_API_KEY=your_key_here
# or create .env file with: OPENAI_API_KEY=your_key_here
```

### CSV Upload Fails
- Check file encoding is UTF-8
- Verify column names match expected formats (see Tibber CSV Format section)
- Ensure timestamps are parseable by pandas

### Unrealistic Results
Common causes:
- Incorrect grid fees or effect tariff (verify with your network operator)
- Battery cost should include installation (~80,000-120,000 SEK total)
- Solar capacity in kWp (peak power), not annual kWh production

## Future Development (Hardware Dongle)

See HARDWARE_DESIGN.md for complete specifications. Key components:
- ESP32 microcontroller
- Modbus/RS485 interface for battery communication
- WiFi connectivity for cloud backend
- Target cost: ~1,000 SEK/unit
- Target retail price: 2,000-3,000 SEK

## Project Context

**Market**: Swedish home battery owners (50,000+ installations, growing 10,000/year)

**Competition**: Sigen.ai (Norway, ~5,000 SEK), but no Swedish equivalent yet

**Revenue potential**: Hardware sales (20M SEK/year) + subscriptions (2.4M SEK/year) + stödtjänster commission (2.5M SEK/year)

## Code Style Notes

- Debug logging uses `print()` statements (see battery_simulator.py:484-506)
- Some debug logging writes to `debug.log` file
- API responses use consistent JSON format with `success` boolean
- Error handling with try/catch and appropriate HTTP status codes
- Comments are in English, but user-facing text in Swedish (index.html)
