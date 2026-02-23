#!/bin/bash

BENJAMIN_DIR="/Users/mtnslwm/Desktop/עוזר אישי בנימין/benjamin"
cd "$BENJAMIN_DIR" || exit 1

echo "📦 Benjamin - Installing dependencies..."
pip3 install -r requirements.txt --upgrade -q

echo ""
echo "🤖 Benjamin - Starting bot..."
python3 bot.py
