# Voice-Controlled Claude Code from Android

Use Claude Code CLI from your Android phone with voice typing via Termius and AWS EC2.

## Architecture

```
┌─────────────────────┐                    ┌──────────────────────────┐
│   Android Phone     │       SSH          │      AWS EC2             │
│   Termius App       │ ◄────────────────► │  - Claude Code CLI       │
│   + Voice Typing    │    (Tailscale)     │  - tmux (persistence)    │
└─────────────────────┘                    │  - EBS (workspace)       │
                                           │  - S3 backup (optional)  │
                                           └──────────────────────────┘
```

## Quick Start

### Option 1: Automated Setup (Recommended)

1. **Launch EC2 Instance**
   - Go to AWS Console → EC2 → Launch Instance
   - Choose **Ubuntu 22.04 LTS** AMI
   - Select **t3.small** (or t3.micro for free tier)
   - Configure storage: 30GB gp3
   - In "Advanced details" → "User data", paste contents of `ec2-user-data.sh`
   - Launch and wait 5-10 minutes for setup to complete

2. **SSH to Instance and Configure**
   ```bash
   ssh -i your-key.pem ubuntu@<ec2-public-ip>

   # Start Tailscale
   sudo tailscale up
   # Follow the auth URL and approve the device

   # Set your API key
   echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.bashrc
   source ~/.bashrc

   # Test Claude Code
   ./start-session.sh
   ```

3. **Get Tailscale IP**
   ```bash
   tailscale ip -4
   # Example output: 100.x.x.x
   ```

### Option 2: Manual Setup

1. **Launch EC2 Instance** (Ubuntu 22.04 LTS)

2. **Copy and Run Setup Script**
   ```bash
   scp -i your-key.pem setup-server.sh start-session.sh ubuntu@<ec2-ip>:~/
   ssh -i your-key.pem ubuntu@<ec2-ip>
   chmod +x setup-server.sh start-session.sh
   ./setup-server.sh
   ```

3. **Configure Tailscale and API Key** (same as Option 1)

## Android Setup (Termius)

1. **Install Termius** from Google Play Store

2. **Add New Host**
   - Tap + → New Host
   - Hostname: Your Tailscale IP (100.x.x.x)
   - Username: ubuntu
   - Authentication: SSH Key (import your .pem file)

3. **Connect and Start Claude**
   - Tap the host to connect
   - Run: `./start-session.sh` (or just `cs`)
   - Use the microphone button on Termius keyboard for voice input

## Usage

### Starting a Session

```bash
# Start or resume Claude Code in tmux
./start-session.sh

# Or use the alias
cs
```

### tmux Controls

| Action | Keys |
|--------|------|
| Detach (leave session running) | `Ctrl+b` then `d` |
| Scroll up | `Ctrl+b` then `[`, use arrow keys |
| Exit scroll mode | `q` |
| Kill session | `Ctrl+d` or type `exit` |

### Backup to S3 (Optional)

```bash
# Configure bucket
export BACKUP_S3_BUCKET=my-claude-backups

# Run backup
./backup-to-s3.sh

# Create timestamped snapshot
CREATE_SNAPSHOT=true ./backup-to-s3.sh
```

**Cron job for daily backups:**
```bash
# Edit crontab
crontab -e

# Add this line (runs at 2 AM daily)
0 2 * * * BACKUP_S3_BUCKET=my-claude-backups /home/ubuntu/backup-to-s3.sh >> /var/log/backup.log 2>&1
```

## Cost Optimization

### Use Spot Instances (70% savings)

When launching EC2:
- Select "Spot Instances" under purchasing options
- Set maximum price (suggest: on-demand price)
- Note: Instance may be interrupted with 2-min warning

### Stop When Not in Use

```bash
# From your local machine
aws ec2 stop-instances --instance-ids i-xxxxx

# Start when needed
aws ec2 start-instances --instance-ids i-xxxxx
```

### Monthly Cost Estimate

| Component | On-Demand | With Optimization |
|-----------|-----------|-------------------|
| EC2 t3.small | ~$15 | ~$5 (spot) |
| EC2 t3.micro | Free (12mo) | Free |
| EBS 30GB gp3 | ~$2.40 | ~$2.40 |
| S3 10GB | ~$0.25 | ~$0.25 |
| Tailscale | Free | Free |
| **Total** | **~$18** | **~$3-8** |

## Troubleshooting

### Can't connect via Tailscale

```bash
# Check Tailscale status
sudo tailscale status

# Re-authenticate if needed
sudo tailscale up --reset
```

### Claude Code not found

```bash
# Reload nvm
source ~/.bashrc

# Verify node
node --version  # Should be 20.x

# Reinstall if needed
npm install -g @anthropic-ai/claude-code
```

### Session not persisting

```bash
# Check if tmux session exists
tmux ls

# If no session, start fresh
./start-session.sh
```

### API key not set

```bash
# Check if set
echo $ANTHROPIC_API_KEY

# If empty, set it
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.bashrc
source ~/.bashrc
```

## Plugins

Custom Claude Code plugins are included in the `plugins/` directory and automatically installed during setup.

### Custom Plugins (8)

| Plugin | Agent | Hook Event | Hook Type | Description |
|--------|:-----:|------------|-----------|-------------|
| `assumption-debugger` | Y | SubagentStop:Plan | prompt | Socratic debugging -- questions assumptions |
| `best-practices-validator` | Y | SubagentStop:Plan | prompt | Validates approach against official docs |
| `branch-guard` | - | PreToolUse:Edit/Write | command | Blocks edits on main/master |
| `commit-often` | - | Stop | command | Warns about uncommitted changes |
| `doc-cross-checker` | Y | SubagentStop:Plan | prompt | Cross-references library documentation |
| `pre-mortem` | Y | SubagentStop:Plan | prompt | Pre-mortem risk analysis for plans |
| `refactoring-radar` | Y | - | - | Suggests refactoring opportunities |
| `review-changes` | Y | PostToolUse:Bash | command | Automatic post-commit review |

4 plugins fire as parallel SubagentStop:Plan validators whenever a Plan agent completes.
See [`docs/hook-flow.md`](docs/hook-flow.md) for the full flow diagram.

### Marketplace Plugins

These are installed via `claude plugin install` during setup:

- **plugin-dev** -- Plugin development tools
- **code-simplifier** -- Simplifies and refines code
- **context7** -- Up-to-date library documentation lookup

### Updating Plugins

After editing plugins locally on your Mac:

```bash
# On Mac: push plugin changes
cd ~/pyg/claude-remote-setup
git add -A && git commit -m "update plugins" && git push

# On remote: one command
update-plugins
```

The `update-plugins` alias runs `cd ~/claude-remote-setup && git pull && ./setup-plugins.sh`.

### Manual Plugin Setup

To install plugins on a machine without running the full server setup:

```bash
git clone https://github.com/tbuckworth/claude-remote-setup.git
cd claude-remote-setup
./setup-plugins.sh
```

## Files

| File | Description |
|------|-------------|
| `setup-server.sh` | Main provisioning script (run manually) |
| `setup-plugins.sh` | Deploy plugins to `~/.claude/plugins/` |
| `start-session.sh` | Start/attach to Claude Code tmux session |
| `backup-to-s3.sh` | Sync workspace to S3 bucket |
| `ec2-user-data.sh` | Cloud-init script for EC2 auto-setup |
| `plugins/` | Custom Claude Code plugins (8 plugins) |
| `docs/hook-flow.md` | Plugin hook flow diagram |
| `config/settings.json` | Portable Claude settings (marketplace plugins) |

## Security Notes

- Keep your EC2 security group restricted (SSH only from your IPs)
- Use Tailscale for secure access (no public SSH exposure)
- Store API key securely (consider AWS Secrets Manager for production)
- Regularly update packages: `sudo apt update && sudo apt upgrade`

## References

- [Termius Android with voice typing](https://termius.com/changelog/android-changelog)
- [Claude Code CLI documentation](https://docs.anthropic.com/en/docs/claude-code)
- [Tailscale setup guide](https://tailscale.com/kb/1031/install-linux/)
- [tmux cheat sheet](https://tmuxcheatsheet.com/)
