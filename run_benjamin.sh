#!/bin/bash
# Benjamin Bot - סקריפט קבוע להרצה
# Usage: ./run_benjamin.sh

BENJAMIN_DIR="/Users/mtnslwm/Desktop/עוזר אישי בנימין/benjamin"
cd "$BENJAMIN_DIR" || { echo "Error: Benjamin directory not found"; exit 1; }

echo "📦 Installing dependencies..."
pip3 install -r requirements.txt --upgrade -q

echo ""
echo "🤖 Starting Benjamin bot..."
python3 bot.py
