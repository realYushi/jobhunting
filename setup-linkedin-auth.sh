#!/bin/bash
# Setup LinkedIn auth vault for agent-browser
# Run this script manually - it will prompt for your password securely

echo "=== LinkedIn Auth Vault Setup ==="
echo ""

read -p "Enter your LinkedIn email: " LINKEDIN_EMAIL
echo ""
echo "Enter your LinkedIn password (hidden): "

agent-browser auth save linkedin \
	--url https://www.linkedin.com/login \
	--username "$LINKEDIN_EMAIL" \
	--password-stdin

echo ""
echo "✅ Done! Testing login..."
agent-browser auth login linkedin
