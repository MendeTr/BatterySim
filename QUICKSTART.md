# 🚀 Quick Start Guide - Battery ROI Calculator

## Installation (5 minutes)

### Step 1: Download the files
You should have these files:
- `app.py` - Backend server
- `battery_simulator.py` - Simulation engine
- `index.html` - Web interface
- `requirements.txt` - Dependencies
- `start.sh` - Startup script
- `sample_tibber_data.csv` - Example data
- `README.md` - Full documentation
- `HARDWARE_DESIGN.md` - Dongle design

### Step 2: Install Python dependencies

**On macOS/Linux:**
```bash
chmod +x start.sh
./start.sh
```

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Step 3: Open the web interface
1. Open your browser
2. Open `index.html` (double-click or drag into browser)
3. The interface will connect to `http://localhost:5000`

## Using the Application

### Get Your Tibber Data
1. Open Tibber app on your phone
2. Go to "Användning" (Usage)
3. Tap "Exportera" (Export)
4. Select date range (12 months recommended)
5. Download CSV file
6. Upload to the web app

### Configure Your System

**Battery Settings:**
- Choose a preset (Tesla Powerwall, Huawei Luna, etc.)
- Or enter custom capacity (kWh) and power (kW)
- Enter the cost of your battery system

**Network Operator:**
- Select your nätbolag from the list
- Or enter custom grid fees and effect tariff

**Solar (Optional):**
- Enter your solar panel capacity in kWp
- Leave at 0 if you don't have solar panels

**Stödtjänster (Optional):**
- Click "Uppskatta FCR-N" to estimate revenue
- The app will calculate if your battery qualifies
- Add the estimated revenue to see impact on ROI

### View Results
The app will show:
- ✅ Payback period in years
- 💰 Annual savings in SEK
- 📊 Monthly breakdown
- 💡 Personalized insights and recommendations
- 📈 ROI percentage and NPV

## Test with Sample Data

Want to test first? Use the included `sample_tibber_data.csv`:
1. Upload this file
2. Use default settings:
   - Battery: 10 kWh, 5 kW, 80,000 SEK
   - Grid fee: 0.45 SEK/kWh
   - Effect tariff: 50 SEK/kW/month
   - Solar: 10 kWp
3. Click "Beräkna ROI"

## Troubleshooting

### "Connection refused" error
- Make sure Flask server is running (`python app.py`)
- Check that port 5000 is not blocked by firewall
- Try accessing `http://127.0.0.1:5000/api/health` in browser

### "No module named 'flask'" error
- Activate virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

### CSV upload fails
- Make sure CSV has these columns: timestamp, consumption, spot price
- File should be UTF-8 encoded
- Swedish column names: "Från", "Förbrukning", "Spotpris"
- Or English: "timestamp", "consumption_kwh", "spot_price_sek_kwh"

### Results seem unrealistic
- Check that your grid fees are correct for your area
- Verify battery cost includes installation
- Make sure effect tariff is per kW per month (not per year)
- Solar capacity should be in kWp (not total annual production)

## Tips for Best Results

1. **Use Real Data**: At least 12 months of Tibber data
2. **Accurate Costs**: Include installation in battery cost
3. **Check Your Tariffs**: Verify with your nätbolag
4. **Solar Production**: Use actual installed capacity
5. **Consider Stödtjänster**: Can improve ROI by 20-40%

## Next Steps

### Want to Build the Hardware Dongle?
See `HARDWARE_DESIGN.md` for:
- Complete component list
- Circuit diagrams
- Firmware code
- Installation instructions
- Business model

### Need Help?
- Read `README.md` for full documentation
- Check API documentation in `README.md`
- Create an issue on GitHub
- Contact support

## Common Questions

**Q: Can I use this with any battery brand?**
A: The calculator works with any battery. The dongle (hardware) supports most brands via Modbus.

**Q: Will this work in other Nordic countries?**
A: The calculator is designed for Sweden but can be adapted for Norway, Denmark, Finland with different tax rates and grid fees.

**Q: How accurate are the predictions?**
A: Historical simulations are very accurate (based on real data). Future predictions depend on weather and consumption patterns.

**Q: Can I sell the dongles commercially?**
A: Yes! The code is MIT licensed. See `HARDWARE_DESIGN.md` for business model suggestions.

**Q: Does this void my battery warranty?**
A: The dongle only reads data (doesn't control the battery), which is generally safe and doesn't void warranties.

**Q: How much can I really save?**
A: Typical savings are 15-30% on electricity costs. With stödtjänster, add another 5,000-15,000 SEK/year.

---

**Ready to optimize your battery? Upload your Tibber data and see your ROI!** 🔋⚡
