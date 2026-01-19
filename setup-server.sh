#!/bin/bash
# setup-server.sh - Main server provisioning script for Claude Code remote access
# Run this on a fresh Ubuntu 22.04+ EC2 instance

set -e

echo "=== Claude Code Remote Server Setup ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root or with sudo
if [ "$EUID" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# Update system packages
log_info "Updating system packages..."
$SUDO apt-get update
$SUDO apt-get upgrade -y

# Install essential packages
log_info "Installing essential packages..."
$SUDO apt-get install -y \
    curl \
    wget \
    git \
    tmux \
    htop \
    unzip \
    build-essential \
    ca-certificates \
    gnupg

# Install Node.js 20+ via nvm
log_info "Installing Node.js via nvm..."
export NVM_DIR="$HOME/.nvm"

if [ ! -d "$NVM_DIR" ]; then
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
fi

# Load nvm
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Install Node.js 20 LTS
nvm install 20
nvm use 20
nvm alias default 20

log_info "Node.js version: $(node --version)"
log_info "npm version: $(npm --version)"

# Install Claude Code CLI globally
log_info "Installing Claude Code CLI..."
npm install -g @anthropic-ai/claude-code

# Verify installation
if command -v claude &> /dev/null; then
    log_info "Claude Code installed successfully!"
else
    log_error "Claude Code installation failed"
    exit 1
fi

# Install Tailscale
log_info "Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sh

# Create workspace directory
WORKSPACE_DIR="/workspace"
log_info "Setting up workspace directory at $WORKSPACE_DIR..."

if [ ! -d "$WORKSPACE_DIR" ]; then
    $SUDO mkdir -p "$WORKSPACE_DIR"
    $SUDO chown -R "$USER:$USER" "$WORKSPACE_DIR"
fi

# Create projects subdirectory
mkdir -p "$WORKSPACE_DIR/projects"

# Configure tmux for better experience
log_info "Configuring tmux..."
cat > ~/.tmux.conf << 'EOF'
# Enable mouse support
set -g mouse on

# Increase scrollback buffer
set -g history-limit 50000

# Start windows and panes at 1, not 0
set -g base-index 1
setw -g pane-base-index 1

# Automatically renumber windows
set -g renumber-windows on

# Better terminal colors
set -g default-terminal "screen-256color"

# Reduce escape time for better vim experience
set -sg escape-time 10

# Status bar
set -g status-style 'bg=#333333 fg=#ffffff'
set -g status-left '[#S] '
set -g status-right '%Y-%m-%d %H:%M'

# Window titles
setw -g automatic-rename on
set -g set-titles on

# Activity monitoring
setw -g monitor-activity on
set -g visual-activity off
EOF

# Add environment variables to bashrc
log_info "Configuring shell environment..."
cat >> ~/.bashrc << 'EOF'

# Claude Code Remote Setup
export WORKSPACE="/workspace"
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Alias for quick Claude session start
alias cs='~/start-session.sh'

# Helpful aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
EOF

# Copy start-session.sh to home directory if it exists in current dir
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/start-session.sh" ]; then
    cp "$SCRIPT_DIR/start-session.sh" ~/start-session.sh
    chmod +x ~/start-session.sh
fi

# Print next steps
echo ""
echo "============================================"
log_info "Setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Start Tailscale and authenticate:"
echo "   ${YELLOW}sudo tailscale up${NC}"
echo ""
echo "2. Set your Anthropic API key:"
echo "   ${YELLOW}echo 'export ANTHROPIC_API_KEY=your-key-here' >> ~/.bashrc${NC}"
echo "   ${YELLOW}source ~/.bashrc${NC}"
echo ""
echo "3. Start a Claude Code session:"
echo "   ${YELLOW}./start-session.sh${NC}"
echo ""
echo "4. From your Android Termius app, SSH to this server's Tailscale IP"
echo ""
