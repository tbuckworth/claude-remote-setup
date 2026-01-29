#!/bin/bash
# ec2-user-data.sh - Cloud-init script for automated EC2 setup
# Paste this into the "User data" field when launching an EC2 instance
# Works with Ubuntu 22.04 LTS AMI

set -e
exec > >(tee /var/log/claude-setup.log) 2>&1

echo "=== Claude Code EC2 User Data Script ==="
echo "Started at: $(date)"

# Wait for cloud-init to complete
cloud-init status --wait

# System updates
apt-get update
apt-get upgrade -y

# Install essential packages
apt-get install -y \
    curl \
    wget \
    git \
    tmux \
    htop \
    unzip \
    build-essential \
    ca-certificates \
    gnupg \
    awscli

# Create workspace directory
mkdir -p /workspace/projects
chown -R ubuntu:ubuntu /workspace

# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Switch to ubuntu user for remaining setup
sudo -u ubuntu bash << 'USERSCRIPT'
cd ~

# Install nvm
export NVM_DIR="$HOME/.nvm"
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

# Load nvm
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Install Node.js 20 LTS
nvm install 20
nvm use 20
nvm alias default 20

# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Configure tmux
cat > ~/.tmux.conf << 'EOF'
set -g mouse on
set -g history-limit 50000
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on
set -g default-terminal "screen-256color"
set -sg escape-time 10
set -g status-style 'bg=#333333 fg=#ffffff'
set -g status-left '[#S] '
set -g status-right '%Y-%m-%d %H:%M'
setw -g automatic-rename on
set -g set-titles on
setw -g monitor-activity on
set -g visual-activity off
EOF

# Create start-session script
cat > ~/start-session.sh << 'SCRIPT'
#!/bin/bash
SESSION_NAME="claude"
WORKSPACE_DIR="${WORKSPACE:-/workspace/projects}"
mkdir -p "$WORKSPACE_DIR"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Attaching to existing Claude session..."
    tmux attach-session -t "$SESSION_NAME"
else
    echo "Creating new Claude session..."
    tmux new-session -d -s "$SESSION_NAME" -c "$WORKSPACE_DIR"
    tmux rename-window -t "$SESSION_NAME" "claude-code"
    tmux send-keys -t "$SESSION_NAME" "cd $WORKSPACE_DIR && claude" Enter
    tmux attach-session -t "$SESSION_NAME"
fi
SCRIPT
chmod +x ~/start-session.sh

# Clone repo and install plugins
if [ ! -d ~/claude-remote-setup ]; then
    git clone https://github.com/tbuckworth/claude-remote-setup.git ~/claude-remote-setup 2>/dev/null || echo "WARN: Could not clone repo, plugins not installed"
fi

if [ -f ~/claude-remote-setup/setup-plugins.sh ]; then
    bash ~/claude-remote-setup/setup-plugins.sh
fi

# Configure bashrc
cat >> ~/.bashrc << 'EOF'

# Claude Code Remote Setup
export WORKSPACE="/workspace"
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
alias cs='~/start-session.sh'
alias ll='ls -alF'

# Update plugins from repo
alias update-plugins='cd ~/claude-remote-setup && git pull && ./setup-plugins.sh'
EOF

USERSCRIPT

# Create MOTD
cat > /etc/motd << 'MOTD'

  ╔═══════════════════════════════════════════════════════════╗
  ║           Claude Code Remote Server                       ║
  ╠═══════════════════════════════════════════════════════════╣
  ║  Quick Start:                                             ║
  ║    1. Set API key: export ANTHROPIC_API_KEY=your-key      ║
  ║    2. Start Tailscale: sudo tailscale up                  ║
  ║    3. Start Claude: ./start-session.sh  (or just: cs)     ║
  ║                                                           ║
  ║  Workspace: /workspace/projects                           ║
  ║  Logs: /var/log/claude-setup.log                          ║
  ╚═══════════════════════════════════════════════════════════╝

MOTD

echo ""
echo "=== Setup Complete ==="
echo "Finished at: $(date)"
echo ""
echo "Next steps:"
echo "1. SSH to the instance"
echo "2. Run: sudo tailscale up"
echo "3. Set ANTHROPIC_API_KEY"
echo "4. Run: ./start-session.sh"
