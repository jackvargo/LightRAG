#!/bin/bash

# LightRAG Secrets Setup Script
# Generates secure secrets for production deployment

set -e

SECRETS_DIR="./secrets"

echo "🔐 Setting up LightRAG production secrets..."

# Create secrets directory if it doesn't exist
mkdir -p "$SECRETS_DIR"

# Generate JWT token secret (64 characters)
echo "📝 Generating JWT token secret..."
openssl rand -base64 64 > "$SECRETS_DIR/token_secret"
echo "✅ JWT token secret generated"

# Generate API key (48 hex characters = 192 bits)
echo "📝 Generating API key..."
openssl rand -hex 48 > "$SECRETS_DIR/api_key"
echo "✅ API key generated"

# Create auth users file with bcrypt hashed passwords
echo "📝 Setting up user authentication..."
echo "Please enter admin password (minimum 12 characters):"
read -s admin_password

# Validate password length
if [ ${#admin_password} -lt 12 ]; then
    echo "❌ Password must be at least 12 characters long"
    exit 1
fi

# Generate bcrypt hash for admin user
htpasswd -Bbn admin "$admin_password" > "$SECRETS_DIR/auth_users"

echo "Do you want to add additional team members? (y/n)"
read add_team

if [ "$add_team" = "y" ] || [ "$add_team" = "Y" ]; then
    echo "Enter team member username:"
    read team_username
    echo "Enter team member password (minimum 12 characters):"
    read -s team_password
    
    if [ ${#team_password} -lt 12 ]; then
        echo "❌ Password must be at least 12 characters long"
        exit 1
    fi
    
    htpasswd -Bbn "$team_username" "$team_password" >> "$SECRETS_DIR/auth_users"
    echo "✅ Team member added"
fi

echo "✅ User authentication configured"

# Set proper permissions
chmod 600 "$SECRETS_DIR"/*
echo "🔒 Secrets permissions set to 600"

# Display summary
echo ""
echo "🎉 Secrets setup complete!"
echo ""
echo "Generated files:"
echo "  - $SECRETS_DIR/token_secret (JWT secret)"
echo "  - $SECRETS_DIR/api_key (API access key)"
echo "  - $SECRETS_DIR/auth_users (bcrypt user hashes)"
echo ""
echo "⚠️  IMPORTANT: Keep these files secure and never commit them to version control!"
echo ""
echo "Next steps:"
echo "1. Update your .env file with CORS_ORIGINS and LIGHTRAG_DOMAIN"
echo "2. Run: docker compose --profile prod up -d"
echo ""

# Show API key for reference
echo "Your API key (save this securely):"
cat "$SECRETS_DIR/api_key"
echo "" 