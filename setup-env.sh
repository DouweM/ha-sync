#!/bin/bash
# Setup script for ha-sync .env file

echo "Home Assistant Sync - Environment Setup"
echo "========================================"
echo

# Prompt for HA URL
read -p "Enter your Home Assistant URL (e.g., http://homeassistant.local:8123): " HA_URL

# Prompt for token (hidden input)
echo "Enter your long-lived access token"
echo "(Create at: Settings > User > Long-lived access tokens)"
read -s -p "Token: " HA_TOKEN
echo

# Write the .env file
cat > .env << EOF
# Home Assistant URL
HA_URL=$HA_URL

# Long-lived access token from Home Assistant
HA_TOKEN=$HA_TOKEN
EOF

echo
echo ".env file created successfully!"
echo "You can now run: uv run ha-sync status"
