#!/bin/bash
# backup-to-s3.sh - Sync workspace to S3 bucket
# Optional backup script that can be run manually or as a cron job

set -e

# Configuration - modify these or set as environment variables
S3_BUCKET="${BACKUP_S3_BUCKET:-}"
WORKSPACE_DIR="${WORKSPACE:-/workspace}"
BACKUP_PREFIX="${BACKUP_PREFIX:-claude-workspace}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if S3 bucket is configured
if [ -z "$S3_BUCKET" ]; then
    log_error "S3 bucket not configured!"
    echo ""
    echo "Set the BACKUP_S3_BUCKET environment variable:"
    echo "  export BACKUP_S3_BUCKET=your-bucket-name"
    echo ""
    echo "Or add to ~/.bashrc:"
    echo "  echo 'export BACKUP_S3_BUCKET=your-bucket-name' >> ~/.bashrc"
    exit 1
fi

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI not installed!"
    echo ""
    echo "Install with:"
    echo "  curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o 'awscliv2.zip'"
    echo "  unzip awscliv2.zip"
    echo "  sudo ./aws/install"
    exit 1
fi

# Check if workspace exists
if [ ! -d "$WORKSPACE_DIR" ]; then
    log_error "Workspace directory not found: $WORKSPACE_DIR"
    exit 1
fi

# Get current timestamp
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
S3_PATH="s3://${S3_BUCKET}/${BACKUP_PREFIX}"

log_info "Starting backup of $WORKSPACE_DIR"
log_info "Destination: $S3_PATH"
echo ""

# Sync to S3 with exclusions
aws s3 sync "$WORKSPACE_DIR" "$S3_PATH" \
    --exclude "node_modules/*" \
    --exclude ".git/objects/*" \
    --exclude "*.pyc" \
    --exclude "__pycache__/*" \
    --exclude ".venv/*" \
    --exclude "venv/*" \
    --exclude ".cache/*" \
    --exclude "*.log" \
    --exclude ".DS_Store" \
    --exclude "*.tmp" \
    --exclude "dist/*" \
    --exclude "build/*" \
    --exclude "target/*" \
    --delete

log_info "Backup completed successfully!"
echo ""

# Optional: Create a timestamped snapshot
if [ "${CREATE_SNAPSHOT:-false}" = "true" ]; then
    SNAPSHOT_PATH="s3://${S3_BUCKET}/${BACKUP_PREFIX}-snapshots/${TIMESTAMP}"
    log_info "Creating snapshot at $SNAPSHOT_PATH"
    aws s3 sync "$WORKSPACE_DIR" "$SNAPSHOT_PATH" \
        --exclude "node_modules/*" \
        --exclude ".git/objects/*" \
        --exclude "*.pyc" \
        --exclude "__pycache__/*" \
        --exclude ".venv/*" \
        --exclude "venv/*"
    log_info "Snapshot created!"
fi

# Print summary
echo ""
echo "============================================"
echo "Backup Summary"
echo "============================================"
echo "Source:      $WORKSPACE_DIR"
echo "Destination: $S3_PATH"
echo "Timestamp:   $TIMESTAMP"
echo ""
echo "To restore from backup:"
echo "  aws s3 sync $S3_PATH $WORKSPACE_DIR"
echo ""
