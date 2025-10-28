from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import pandas as pd
import os
import json
from dotenv import load_dotenv
from battery_simulator import BatteryROISimulator

# Load environment variables from .env file
load_dotenv()
from werkzeug.utils import secure_filename
import traceback

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = '/tmp/uploads'
ALLOWED_EXTENSIONS = {'csv', 'xlsx'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Global progress tracking for SSE
simulation_progress = {
    'percent': 0,
    'message': 'Waiting to start...',
    'is_running': False
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'message': 'Battery ROI API is running'})

@app.route('/api/progress')
def progress_stream():
    """Server-Sent Events endpoint for simulation progress"""
    def generate():
        import time
        while True:
            # Send current progress
            data = json.dumps(simulation_progress)
            yield f"data: {data}\n\n"

            # Stop streaming if simulation is done
            if not simulation_progress['is_running'] and simulation_progress['percent'] >= 100:
                break

            time.sleep(1)  # Update every second

    return app.response_class(generate(), mimetype='text/event-stream')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload Tibber CSV file"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Try to parse the file to validate it
            try:
                df = pd.read_csv(filepath)
                row_count = len(df)
                columns = list(df.columns)
                
                return jsonify({
                    'success': True,
                    'filename': filename,
                    'rows': row_count,
                    'columns': columns,
                    'message': f'File uploaded successfully. {row_count} hours of data found.'
                })
            except Exception as e:
                return jsonify({'error': f'Failed to parse CSV: {str(e)}'}), 400
        
        return jsonify({'error': 'Invalid file type. Please upload CSV or XLSX'}), 400
    
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/simulate', methods=['POST'])
def simulate_battery():
    """
    Run battery simulation with provided parameters
    
    Expected JSON body:
    {
        "filename": "tibber_data.csv",
        "battery_capacity_kwh": 10,
        "battery_power_kw": 5,
        "battery_cost_sek": 80000,
        "battery_efficiency": 0.95,
        "battery_lifetime_years": 15,
        "grid_fee_sek_kwh": 0.45,
        "energy_tax_sek_kwh": 0.40,
        "effect_tariff_sek_kw_month": 50,
        "vat_rate": 0.25,
        "solar_capacity_kwp": 10,
        "enable_arbitrage": true,
        "use_gpt_arbitrage": false,
        "stodtjanster_revenue_sek_year": 0
    }
    """
    global simulation_progress

    try:
        data = request.json

        # Validate required fields
        required_fields = ['filename', 'battery_capacity_kwh', 'battery_power_kw',
                          'battery_cost_sek', 'grid_fee_sek_kwh', 'energy_tax_sek_kwh']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Get file path
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], data['filename'])
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found. Please upload file first.'}), 404

        # Progress callback to update global state
        def update_progress(progress_data):
            global simulation_progress
            simulation_progress.update(progress_data)
            simulation_progress['is_running'] = True
            print(f"📊 Progress: {progress_data['percent']:.1f}% - {progress_data['message']}")

        # Initialize simulator
        use_gpt = data.get('use_gpt_arbitrage', False)
        print(f"🔧 GPT Arbitrage enabled: {use_gpt}")

        # Reset progress
        simulation_progress = {'percent': 0, 'message': 'Starting simulation...', 'is_running': True}

        # Check if multi-agent mode is requested
        use_multi_agent = data.get('use_multi_agent', False)
        use_boss_agent = data.get('use_boss_agent', True)  # DEFAULT TO TRUE (24h planning enabled)
        print(f"🤖 Multi-Agent mode: {use_multi_agent}")
        print(f"👔 Boss Agent mode (24h planning): {use_boss_agent}")

        simulator = BatteryROISimulator(
            battery_capacity_kwh=data['battery_capacity_kwh'],
            battery_power_kw=data['battery_power_kw'],
            battery_efficiency=data.get('battery_efficiency', 0.95),
            battery_cost_sek=data['battery_cost_sek'],
            battery_lifetime_years=data.get('battery_lifetime_years', 15),
            use_gpt_arbitrage=use_gpt,
            use_multi_agent=use_multi_agent,
            use_boss_agent=use_boss_agent,  # Enable Boss Agent with 24h planning
            progress_callback=update_progress
        )
        
        # Load data
        df = simulator.load_tibber_data(filepath)
        
        # Calculate current costs (without battery)
        cost_without = simulator.calculate_current_costs(
            df,
            grid_fee_sek_kwh=data['grid_fee_sek_kwh'],
            energy_tax_sek_kwh=data['energy_tax_sek_kwh'],
            vat_rate=data.get('vat_rate', 0.25)
        )
        
        # Add solar production - use real data from CSV if available, otherwise generate estimates
        solar_kwp = data.get('solar_capacity_kwp', 0)
        if 'solar_kwh' in df.columns:
            # Use real solar production data from CSV
            print(f"Using real solar production data from CSV: {df['solar_kwh'].sum():.1f} kWh total")
            df['net_consumption_kwh'] = df['consumption_kwh'] - df['solar_kwh']
        elif solar_kwp > 0:
            # Generate estimated solar production
            print(f"Generating estimated solar production for {solar_kwp} kWp system")
            df = simulator.add_solar_production(df, solar_capacity_kwp=solar_kwp)
        else:
            df['solar_kwh'] = 0
            df['net_consumption_kwh'] = df['consumption_kwh']
        
        # Simulate battery operation
        df_with_battery, results_with = simulator.simulate_battery_operation(
            df,
            grid_fee_sek_kwh=data['grid_fee_sek_kwh'],
            energy_tax_sek_kwh=data['energy_tax_sek_kwh'],
            effect_tariff_sek_kw_month=data.get('effect_tariff_sek_kw_month', 0),
            vat_rate=data.get('vat_rate', 0.25),
            enable_arbitrage=data.get('enable_arbitrage', True),
            effect_tariff_method=data.get('effect_tariff_method', 'single_peak'),
            date_range_start=data.get('date_range_start'),
            date_range_end=data.get('date_range_end')
        )
        
        # Calculate ROI
        stodtjanster_revenue = data.get('stodtjanster_revenue_sek_year', 0)
        roi = simulator.calculate_roi(
            cost_without['total_cost_sek'],
            results_with['net_cost_sek'],
            results_with.get('effect_tariff_savings_sek', 0),
            stodtjanster_revenue
        )
        
        # Generate report
        report = simulator.generate_report(df_with_battery, cost_without, results_with, roi)

        # Add some additional insights
        report['insights'] = generate_insights(cost_without, results_with, roi, data)

        # Mark simulation as complete
        simulation_progress = {'percent': 100, 'message': 'Simulation complete!', 'is_running': False}

        return jsonify({
            'success': True,
            'report': report
        })

    except Exception as e:
        print(f"Simulation error: {traceback.format_exc()}")
        # Mark as failed
        simulation_progress = {'percent': 0, 'message': f'Error: {str(e)}', 'is_running': False}
        return jsonify({'error': f'Simulation failed: {str(e)}'}), 500

def generate_insights(cost_without, results_with, roi, params):
    """Generate human-readable insights from the simulation"""
    insights = []
    
    # Profitability check
    if roi['profitable']:
        insights.append({
            'type': 'success',
            'title': 'Profitable Investment',
            'message': f"This battery system will pay for itself in {roi['payback_period_years']:.1f} years and generate a net profit of {roi['net_profit_sek']:,.0f} SEK over its lifetime."
        })
    else:
        insights.append({
            'type': 'warning',
            'title': 'Not Profitable',
            'message': f"With current parameters, this battery system will not pay for itself within its {roi['lifetime_years']}-year lifetime. Consider a smaller/cheaper system or adding stödtjänster revenue."
        })
    
    # Self-consumption rate
    self_consumption_pct = results_with.get('self_consumption_rate', 0) * 100
    if self_consumption_pct > 70:
        insights.append({
            'type': 'success',
            'title': 'Excellent Self-Consumption',
            'message': f"You're achieving {self_consumption_pct:.0f}% self-consumption, which is excellent! Most of your solar energy is being used effectively."
        })
    elif self_consumption_pct > 50:
        insights.append({
            'type': 'info',
            'title': 'Good Self-Consumption',
            'message': f"You're achieving {self_consumption_pct:.0f}% self-consumption. There's still room for improvement with a larger battery."
        })
    
    # Effect tariff savings
    effect_savings = results_with.get('effect_tariff_savings_sek', 0)
    if effect_savings > 0:
        effect_pct = (effect_savings / roi['annual_savings_sek']) * 100 if roi['annual_savings_sek'] > 0 else 0
        insights.append({
            'type': 'info',
            'title': 'Effect Tariff Reduction',
            'message': f"Peak shaving saves you {effect_savings:,.0f} SEK/year ({effect_pct:.0f}% of total savings) by reducing your power peaks."
        })
    
    # Stödtjänster potential
    if params.get('stodtjanster_revenue_sek_year', 0) == 0 and params['battery_power_kw'] >= 5:
        insights.append({
            'type': 'tip',
            'title': 'Consider Stödtjänster',
            'message': f"With {params['battery_power_kw']} kW capacity, you could participate in grid services (FCR) and earn an additional 5,000-15,000 SEK/year. Enable this option to see the impact."
        })
    
    # Annual savings breakdown
    annual_savings = roi['annual_savings_sek']
    insights.append({
        'type': 'info',
        'title': 'Annual Savings Breakdown',
        'message': f"Total annual savings: {annual_savings:,.0f} SEK ({annual_savings/12:,.0f} SEK/month)"
    })
    
    return insights

@app.route('/api/stodtjanster/estimate', methods=['POST'])
def estimate_stodtjanster():
    """
    Estimate potential revenue from stödtjänster (FCR, aFRR)
    
    Expected JSON:
    {
        "battery_power_kw": 5,
        "battery_capacity_kwh": 10,
        "service_type": "fcr_n"  // fcr_n, fcr_d, afrr
    }
    """
    try:
        data = request.json
        power_kw = data.get('battery_power_kw', 0)
        capacity_kwh = data.get('battery_capacity_kwh', 0)
        service = data.get('service_type', 'fcr_n')
        
        # Minimum requirements
        if power_kw < 5:
            return jsonify({
                'eligible': False,
                'message': 'Minimum 5 kW power capacity required for most stödtjänster',
                'estimated_revenue_sek_year': 0
            })
        
        # Rough estimates based on Swedish market (2024-2025 averages)
        # These are conservative estimates
        revenue_estimates = {
            'fcr_n': {  # FCR-N (Frequency Containment Reserve - Normal)
                'sek_per_mw_hour': 2500,  # Average market price
                'availability_factor': 0.7  # 70% of time available (accounting for home use)
            },
            'fcr_d': {  # FCR-D (Frequency Containment Reserve - Disturbance)
                'sek_per_mw_hour': 2000,
                'availability_factor': 0.6
            },
            'afrr': {  # Automatic Frequency Restoration Reserve
                'sek_per_mw_hour': 1500,
                'availability_factor': 0.5
            }
        }
        
        if service not in revenue_estimates:
            return jsonify({'error': 'Invalid service type'}), 400
        
        estimate = revenue_estimates[service]
        
        # Calculate annual revenue
        # Revenue = (Power in MW) * (Price per MW-hour) * (Hours per year) * (Availability factor)
        power_mw = power_kw / 1000
        hours_per_year = 8760
        
        annual_revenue = (power_mw * estimate['sek_per_mw_hour'] * 
                         hours_per_year * estimate['availability_factor'])
        
        # Deduct aggregator fees (typically 20-30%)
        aggregator_fee = 0.25
        net_revenue = annual_revenue * (1 - aggregator_fee)
        
        return jsonify({
            'eligible': True,
            'service_type': service,
            'estimated_revenue_sek_year': round(net_revenue, 2),
            'gross_revenue_sek_year': round(annual_revenue, 2),
            'aggregator_fee_percentage': aggregator_fee * 100,
            'notes': [
                'This is a conservative estimate based on market averages',
                'Actual revenue varies with market conditions',
                'Requires partnership with an aggregator (e.g., Checkwatt, Flower)',
                f'Based on {estimate["availability_factor"]*100:.0f}% availability factor'
            ]
        })
    
    except Exception as e:
        return jsonify({'error': f'Estimation failed: {str(e)}'}), 500

@app.route('/api/battery/presets', methods=['GET'])
def get_battery_presets():
    """Get common battery system presets for Swedish market"""
    presets = [
        {
            'name': 'Small - Huawei Luna 2000 5kWh',
            'capacity_kwh': 5,
            'power_kw': 2.5,
            'cost_sek': 45000,
            'description': 'Good for small households (up to 5000 kWh/year)'
        },
        {
            'name': 'Medium - Tesla Powerwall 13.5kWh',
            'capacity_kwh': 13.5,
            'power_kw': 5,
            'cost_sek': 95000,
            'description': 'Popular choice for average households (10000-20000 kWh/year)'
        },
        {
            'name': 'Large - Sonnen Eco 10kWh',
            'capacity_kwh': 10,
            'power_kw': 4.6,
            'cost_sek': 85000,
            'description': 'Premium quality, good for medium-large households'
        },
        {
            'name': 'Large - LG RESU 16kWh',
            'capacity_kwh': 16,
            'power_kw': 7,
            'cost_sek': 120000,
            'description': 'Large capacity for high consumption or stödtjänster'
        },
        {
            'name': 'Custom',
            'capacity_kwh': 10,
            'power_kw': 5,
            'cost_sek': 80000,
            'description': 'Configure your own battery system'
        }
    ]
    
    return jsonify({'presets': presets})

@app.route('/api/network-operators', methods=['GET'])
def get_network_operators():
    """Get list of Swedish network operators with typical fees"""
    operators = [
        {
            'name': 'Vattenfall Eldistribution',
            'grid_fee_sek_kwh': 0.45,
            'effect_tariff_sek_kw_month': 55,
            'region': 'Nationwide'
        },
        {
            'name': 'E.ON Energidistribution',
            'grid_fee_sek_kwh': 0.42,
            'effect_tariff_sek_kw_month': 50,
            'region': 'South Sweden'
        },
        {
            'name': 'Ellevio',
            'grid_fee_sek_kwh': 0.48,
            'effect_tariff_sek_kw_month': 60,
            'region': 'Stockholm region'
        },
        {
            'name': 'Göteborg Energi Nät',
            'grid_fee_sek_kwh': 0.44,
            'effect_tariff_sek_kw_month': 52,
            'region': 'Gothenburg'
        },
        {
            'name': 'Skellefteå Kraft Elnät',
            'grid_fee_sek_kwh': 0.38,
            'effect_tariff_sek_kw_month': 45,
            'region': 'North Sweden'
        }
    ]
    
    return jsonify({'operators': operators})

@app.route('/')
def index():
    """Serve the main HTML file"""
    return send_file('index.html')

if __name__ == '__main__':
    print("Starting Battery ROI API Server...")
    print("API will be available at http://localhost:5001")
    print("\nEndpoints:")
    print("  GET  /api/health - Health check")
    print("  POST /api/upload - Upload Tibber CSV")
    print("  POST /api/simulate - Run battery simulation")
    print("  POST /api/stodtjanster/estimate - Estimate stödtjänster revenue")
    print("  GET  /api/battery/presets - Get battery presets")
    print("  GET  /api/network-operators - Get network operator info")
    
    app.run(debug=True, host='0.0.0.0', port=5001)
