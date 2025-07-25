#!/bin/bash
# This script ensures the bot runs continuously in Termux and restarts on crash.

# Navigate to the bot's directory
cd "$(dirname "$0")"

while true; do
    echo "Starting Lunura Bot..."
    python main.py
    echo "Bot crashed. Restarting in 5 seconds..."
    sleep 5
done