#!/bin/bash

echo "🔋 Battery ROI Calculator - Starting..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python found: $(python3 --version)"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip is not installed. Please install pip."
    exit 1
fi

echo "✅ pip found"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "📥 Installing dependencies..."
pip install -r requirements.txt --quiet

echo ""
echo "✨ Setup complete!"
echo ""
echo "Starting Flask server on http://localhost:5000"
echo "Opening web interface in your browser..."
echo ""
echo "To use the application:"
echo "1. Upload your Tibber CSV file"
echo "2. Configure your battery system"
echo "3. Get your ROI analysis!"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the Flask server
python3 app.py
