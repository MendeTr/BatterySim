# 🔌 Battery Optimization Dongle - Hardware Design Document

## Overview
This document outlines the design for a plug-and-play hardware device (dongle) that enables real-time battery monitoring and optimization for Swedish homes, similar to Sigen.ai.

## Hardware Components

### Core Processing Unit
**Option 1: ESP32 (Recommended for v1.0)**
- **Model**: ESP32-WROOM-32
- **CPU**: Dual-core 240MHz
- **RAM**: 520KB
- **Flash**: 4MB
- **Connectivity**: WiFi, Bluetooth
- **Cost**: ~150 SEK
- **Pros**: Low cost, excellent WiFi, large community
- **Cons**: Limited processing power for complex ML

**Option 2: Raspberry Pi Zero 2 W (Alternative)**
- **CPU**: Quad-core ARM Cortex-A53 1GHz
- **RAM**: 512MB
- **Connectivity**: WiFi, Bluetooth
- **Cost**: ~300 SEK
- **Pros**: More powerful, runs full Linux
- **Cons**: Higher power consumption, more expensive

### Battery Communication Interface

**Modbus RTU/RS485 Interface**
- **Chip**: MAX485/MAX3485
- **Protocol**: Modbus RTU over RS485
- **Baud Rate**: 9600-115200 bps
- **Cost**: ~100 SEK
- **Purpose**: Read battery SoC, voltage, current, temperature

**Supported Battery Brands (via Modbus)**:
- Tesla Powerwall (via Gateway)
- Huawei Luna 2000
- LG RESU
- Sonnen Eco
- BYD Battery-Box
- Pylontech US2000/US3000

**CAN Bus Interface (Optional - v2.0)**
- **Chip**: MCP2515 CAN Controller
- **Transceiver**: MCP2551
- **Cost**: ~150 SEK
- **Purpose**: Direct communication with some batteries

### Power Supply
- **Input**: 230V AC (Swedish standard)
- **Converter**: HLK-5M05 (5V 1A)
- **Cost**: ~50 SEK
- **Output**: 5V DC for ESP32/Pi
- **Protection**: Fuse, TVS diode

**Alternative: USB Power**
- Powered via USB-C (5V 2A)
- Simpler, safer for DIY installation
- Recommended for v1.0

### Additional Sensors (Optional)

**CT Clamp Current Sensor**
- **Model**: SCT-013-000
- **Range**: 0-100A
- **Cost**: ~150 SEK
- **Purpose**: Measure grid import/export
- **Connection**: Analog input via voltage divider

**Temperature Sensor**
- **Model**: DS18B20
- **Cost**: ~30 SEK
- **Purpose**: Monitor ambient temperature

### Connectivity Options

**Primary: WiFi**
- Built-in to ESP32/Pi
- Connects to home network
- MQTT/HTTPS to cloud server

**Backup: 4G LTE (v2.0)**
- **Module**: SIM7600E
- **Cost**: ~400 SEK
- **Purpose**: Redundancy if WiFi fails
- **Subscription**: ~50 SEK/month

### Enclosure
- **Material**: Plastic (ABS)
- **Type**: DIN rail mountable
- **Dimensions**: 100mm x 70mm x 40mm
- **Rating**: IP20 (indoor use)
- **Cost**: ~100 SEK
- **Features**: 
  - LED status indicators
  - Reset button
  - Terminal blocks for RS485

## System Architecture

```
┌─────────────────────────────────────────────────┐
│                   Home Network                   │
│                                                  │
│  ┌──────────┐         WiFi         ┌─────────┐ │
│  │  Router  │◄──────────────────────►  Dongle │ │
│  └──────────┘                       └─────────┘ │
│       │                                  │      │
│       │                                  │      │
│   Internet                          RS485/Modbus│
│       │                                  │      │
│       ▼                                  ▼      │
│  ┌──────────────┐              ┌──────────────┐│
│  │ Cloud Server │              │   Battery    ││
│  │   (AWS/GCP)  │              │   System     ││
│  └──────────────┘              └──────────────┘│
│       │                                         │
│       ▼                                         │
│  ┌──────────────┐                              │
│  │  Web/Mobile  │                              │
│  │     App      │                              │
│  └──────────────┘                              │
└─────────────────────────────────────────────────┘
```

## Software Architecture

### Firmware (ESP32)
**Language**: C++ (Arduino framework) or MicroPython

**Core Functions**:
1. **Battery Monitor**: Read SoC, power, voltage via Modbus
2. **Grid Monitor**: Measure import/export via CT clamp
3. **Data Logger**: Store readings locally (circular buffer)
4. **MQTT Client**: Publish data to cloud every 10 seconds
5. **OTA Updates**: Remote firmware updates
6. **Watchdog**: Auto-restart if hung

**Libraries**:
- ModbusMaster (for Modbus RTU)
- PubSubClient (for MQTT)
- ArduinoJson (for JSON parsing)
- WiFiManager (for easy WiFi setup)

### Cloud Backend
**Infrastructure**: AWS or Azure

**Services**:
- **MQTT Broker**: AWS IoT Core or Azure IoT Hub
- **Database**: TimescaleDB (PostgreSQL for time-series)
- **API**: FastAPI (Python)
- **ML Model**: TensorFlow Lite for predictions
- **Queue**: Redis for job processing

**Functions**:
1. **Data Ingestion**: Receive MQTT messages from dongles
2. **Storage**: Store time-series data in TimescaleDB
3. **Analysis**: Real-time analytics and optimization
4. **Prediction**: Forecast solar, consumption, prices
5. **Control**: Send optimization commands to dongles
6. **Stödtjänster**: Bid management for FCR/aFRR

### Control Algorithm

**Optimization Goals** (in priority order):
1. **Reliability**: Always have enough charge for home
2. **Cost Savings**: Minimize electricity costs
3. **Peak Shaving**: Reduce effect tariff charges
4. **Stödtjänster Revenue**: Maximize grid services income
5. **Battery Longevity**: Avoid deep cycles, overcharge

**Algorithm**:
```python
def optimize_battery():
    # Get current state
    soc = battery.get_soc()
    grid_power = grid.get_power()
    solar_power = solar.get_power()
    
    # Get predictions (next 24 hours)
    solar_forecast = predict_solar()
    consumption_forecast = predict_consumption()
    price_forecast = get_spot_prices()
    
    # Calculate optimal schedule
    schedule = optimize_schedule(
        soc=soc,
        solar=solar_forecast,
        consumption=consumption_forecast,
        prices=price_forecast,
        constraints={
            'min_soc': 0.2,  # Keep 20% reserve
            'max_power': battery_max_power,
            'stodtjanster_availability': 0.7
        }
    )
    
    # Execute next action
    action = schedule[0]
    battery.set_power(action['power'])
    
    return schedule
```

## Installation Process

### DIY Installation (v1.0 - Simple)
1. **Connect to Battery**: 
   - Plug RS485 into battery's Modbus port
   - Most modern batteries have accessible Modbus terminals
   
2. **Power the Dongle**:
   - Plug into USB power adapter (5V 2A)
   - Or connect to AC using built-in converter
   
3. **WiFi Setup**:
   - Dongle creates WiFi hotspot on first boot
   - Connect phone to "BatteryDongle-XXXX"
   - Enter home WiFi credentials
   - Dongle connects to cloud automatically
   
4. **Optional: CT Clamp**:
   - Clip around main grid cable (non-invasive)
   - Plug into dongle's analog input
   
5. **Verification**:
   - Open web app
   - See real-time battery data
   - Done!

**Installation Time**: 15-30 minutes

### Professional Installation (v2.0 - Advanced)
For customers wanting more advanced features:
- Hardwired power connection
- Multiple CT clamps (solar, grid, loads)
- CAN bus integration
- 4G backup connection

## Data Flow

### Real-Time Monitoring
```
Battery → Modbus → Dongle → MQTT → Cloud → Database
  ↓                  ↓                ↓
SoC, V, I        Process           Store & Analyze
Power            Optimize          Update Dashboard
Temp             Log               Trigger Alerts
```

**Update Frequency**:
- Battery metrics: Every 10 seconds
- Grid power: Every 1 second (CT clamp)
- Solar power: Every 5 seconds
- Cloud sync: Every 10 seconds

### Control Commands
```
Cloud → MQTT → Dongle → Modbus → Battery
  ↓              ↓         ↓
Optimization   Execute   Charge/Discharge
Schedule       Command   at X kW
```

## Security

### Device Security
1. **Secure Boot**: Verify firmware signature
2. **Encrypted Storage**: Store WiFi credentials encrypted
3. **TLS/SSL**: All MQTT communication encrypted
4. **Authentication**: JWT tokens for API access
5. **Firmware Signing**: Only install signed updates

### Cloud Security
1. **Device Certificates**: Each dongle has unique cert
2. **API Gateway**: Rate limiting, DDoS protection
3. **Database Encryption**: At-rest and in-transit
4. **Access Control**: Role-based permissions
5. **Audit Logging**: Track all configuration changes

## Regulatory Compliance

### Sweden (Elsäkerhetsverket)
- ✅ Low voltage device (<50V DC internally)
- ✅ USB power = no electrical certification needed
- ⚠️ AC power version needs certification
- ✅ Non-invasive installation (no grid connection)

### CE Marking (EU)
- **EMC Directive**: Electromagnetic compatibility
- **RoHS Directive**: No hazardous substances
- **WEEE Directive**: Recycling obligations

### Battery Communication
- ✅ Read-only Modbus (safe, no risk)
- ⚠️ Write access needs battery manufacturer approval
- ✅ Most batteries allow read access by default

## Cost Breakdown (v1.0)

| Component | Cost (SEK) |
|-----------|------------|
| ESP32 Module | 150 |
| MAX485 RS485 Interface | 100 |
| USB-C Power | 50 |
| CT Clamp (optional) | 150 |
| PCB Manufacturing | 200 |
| Enclosure | 100 |
| Cables & Connectors | 100 |
| Assembly | 150 |
| **Total BOM** | **1000** |
| Markup (2x) | 1000 |
| **Retail Price** | **2000 SEK** |

## Business Model

### Hardware Sales
- **Retail Price**: 2,000-3,000 SEK
- **Margin**: ~50%
- **Target**: 10,000 units in Year 1

### Subscription (Optional)
- **Basic**: Free - Dashboard + monitoring
- **Premium**: 99 SEK/month
  - Advanced optimization
  - Predictive analytics
  - Stödtjänster automation
  - Priority support
- **Pro**: 199 SEK/month
  - Everything in Premium
  - API access
  - Custom integrations
  - White-label option

### Stödtjänster Commission
- **Revenue Share**: 10-15% of FCR/aFRR earnings
- **Avg Customer**: 10,000 SEK/year in stödtjänster
- **Our Cut**: 1,000-1,500 SEK/year per customer

### Revenue Projections (Year 1)
```
Hardware: 10,000 units × 2,000 SEK = 20M SEK
Premium Subscriptions: 2,000 users × 99 SEK × 12 = 2.4M SEK
Stödtjänster Commission: 2,000 users × 1,250 SEK = 2.5M SEK
──────────────────────────────────────────────────
Total Revenue: ~25M SEK
```

## Development Timeline

### Phase 1: Prototype (Q1 2025)
- ✅ Design hardware schematic
- ✅ Order components
- ☐ Assemble prototype (10 units)
- ☐ Basic firmware (read battery data)
- ☐ Test with 3 different battery brands
- **Deliverable**: Working prototype

### Phase 2: Cloud Platform (Q2 2025)
- ☐ Set up AWS/Azure infrastructure
- ☐ Develop MQTT broker integration
- ☐ Create TimescaleDB schema
- ☐ Build REST API
- ☐ Develop web dashboard
- **Deliverable**: End-to-end system

### Phase 3: Optimization (Q3 2025)
- ☐ Implement ML models for prediction
- ☐ Develop optimization algorithm
- ☐ Add spot price integration (Nord Pool)
- ☐ Test optimization in real homes (10 beta users)
- **Deliverable**: Smart optimization working

### Phase 4: Stödtjänster (Q4 2025)
- ☐ Partner with aggregator (Checkwatt/Flower)
- ☐ Implement FCR bid management
- ☐ Automated enrollment and availability
- ☐ Get grid services certification
- **Deliverable**: Revenue from stödtjänster

### Phase 5: Production (Q1 2026)
- ☐ Design for manufacturing (DFM)
- ☐ CE certification
- ☐ Find manufacturing partner in EU
- ☐ Order 1,000 units
- ☐ Launch marketing campaign
- **Deliverable**: Product ready to sell

## Technical Challenges

### Challenge 1: Battery Compatibility
**Problem**: Different batteries use different protocols
**Solution**: 
- Start with most common brands (Tesla, Huawei)
- Use Modbus RTU (most common standard)
- Add CAN bus support later
- Maintain compatibility database

### Challenge 2: Prediction Accuracy
**Problem**: Weather and consumption are hard to predict
**Solution**:
- Use external APIs (SMHI, Nord Pool)
- Train models on user's historical data
- Combine multiple models (ensemble)
- Conservative estimates (better safe than sorry)

### Challenge 3: Network Reliability
**Problem**: WiFi can be unreliable
**Solution**:
- Local buffer (store 24h of data)
- Automatic reconnection
- Fall back to simple rules if offline
- 4G backup (v2.0)

### Challenge 4: Battery Warranty
**Problem**: Will we void warranties by connecting?
**Solution**:
- Read-only access (safe)
- Get explicit approval from manufacturers
- Work with installers/dealers
- Offer installation by certified partners

## Competition Analysis

### Sigen.ai (Norway)
- **Strengths**: First mover, good software
- **Weaknesses**: Norway-only, expensive (€500)
- **Our Advantage**: Swedish market, lower price, stödtjänster

### Tibber (Sweden/Norway)
- **Strengths**: Large user base, brand recognition
- **Weaknesses**: No hardware yet, focuses on smart charging
- **Our Advantage**: Battery-specific, real-time optimization

### Ferroamp (Sweden)
- **Strengths**: Complete system (battery + inverter)
- **Weaknesses**: Expensive (>150,000 SEK), closed ecosystem
- **Our Advantage**: Works with any battery, affordable

## Go-to-Market Strategy

### Target Customers (Year 1)
1. **Solar + Battery Owners**: 50,000 in Sweden (growing 10,000/year)
2. **Early Adopters**: Tech-savvy homeowners
3. **ROI Seekers**: People who want to optimize their investment

### Marketing Channels
1. **SEO/Content**: Blog posts about battery optimization
2. **Social Media**: Facebook groups (Solceller Sverige)
3. **Partnerships**: Solar installers, battery dealers
4. **Affiliates**: YouTubers, energy bloggers
5. **Events**: Allt om Stockholm, Elmässan

### Pricing Strategy
- **Launch Price**: 1,999 SEK (special offer)
- **Regular Price**: 2,499 SEK
- **Bundle**: Dongle + 6 months Premium for 2,799 SEK

### Distribution
- **Direct**: Online store (www.batteryoptimizer.se)
- **Installers**: 20% commission
- **Retail**: Kjell & Company, NetOnNet (potential)

## Success Metrics

### Technical KPIs
- Battery read success rate: >99%
- Data latency: <30 seconds
- Prediction accuracy: >85% for next-day solar
- Optimization savings: >15% vs no optimization

### Business KPIs
- Units sold: 10,000 in Year 1
- Churn rate: <5% per year
- Customer satisfaction (NPS): >50
- Revenue: 25M SEK in Year 1

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Battery incompatibility | High | Medium | Test top 5 brands, maintain database |
| Regulatory issues | High | Low | Get legal advice, CE certification |
| Cloud costs too high | Medium | Medium | Optimize data storage, compression |
| Customer acquisition cost | Medium | High | Focus on partnerships, content marketing |
| Competition from Tibber | High | Medium | Move fast, better product, lower price |

## Next Steps

1. **Immediate (This week)**:
   - Order ESP32 and components (500 SEK)
   - Set up GitHub repository
   - Create development board

2. **Short-term (This month)**:
   - Build first prototype
   - Test with one battery system
   - Create firmware v0.1

3. **Medium-term (Q1 2025)**:
   - Test with 10 beta users
   - Develop cloud platform
   - Refine hardware design

4. **Long-term (2025)**:
   - Manufacturing partnership
   - CE certification
   - Launch marketing campaign

---

**Questions to decide**:
1. USB power or AC power for v1.0? (Recommend USB)
2. ESP32 or Raspberry Pi? (Recommend ESP32)
3. Cloud provider: AWS or Azure? (Recommend AWS)
4. Freemium or paid-only? (Recommend freemium)
5. DIY or professional installation? (Recommend DIY first)

Ready to start building! 🚀
