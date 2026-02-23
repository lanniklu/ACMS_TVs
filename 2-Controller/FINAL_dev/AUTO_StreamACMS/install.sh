#!/bin/bash
###############################################################################
# ACMS Deployment Script
# Installs and configures MAWAQIT stream manager for automatic startup
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/home/acms_tech/AUTO_StreamACMS"
LOG_DIR="/home/acms_tech/AUTO_StreamACMS/logs"
USER="acms_tech"

echo -e "${GREEN}=========================================="
echo "ACMS MAWAQIT Manager Deployment"
echo -e "==========================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Create directories
echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$LOG_DIR"

# Scripts are already in place (copied via SCP)
echo -e "${YELLOW}Scripts already in $INSTALL_DIR${NC}"

# Set permissions
echo -e "${YELLOW}Setting permissions...${NC}"
chmod +x "$INSTALL_DIR/start_mawaqit_manager.sh"
chmod +x "$INSTALL_DIR/mawaqit_stream_manager.py"
chmod +x "$INSTALL_DIR/mawaqit_box_setup.py"
chown -R "$USER:$USER" "$INSTALL_DIR"

# Check dependencies
echo -e "${YELLOW}Checking dependencies...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python3 not found. Installing...${NC}"
    apt-get update
    apt-get install -y python3 python3-pip
fi

if ! command -v adb &> /dev/null; then
    echo -e "${RED}ADB not found. Installing...${NC}"
    apt-get install -y adb
fi

# Python dependencies check (all standard library modules - no pip needed)
echo -e "${YELLOW}Checking Python dependencies...${NC}"
echo -e "${GREEN}All required modules are in Python standard library${NC}"

# Setup crontab for user
echo -e "${YELLOW}Configuring crontab...${NC}"

# Create temporary crontab file
TEMP_CRON=$(mktemp)

# Get existing crontab (if any)
crontab -u "$USER" -l > "$TEMP_CRON" 2>/dev/null || true

# Remove old MAWAQIT entries if they exist
sed -i '/start_mawaqit_manager.sh/d' "$TEMP_CRON"

# Add new entry
echo "@reboot $INSTALL_DIR/start_mawaqit_manager.sh >> $LOG_DIR/supervisor.log 2>&1 &" >> "$TEMP_CRON"

# Install new crontab
crontab -u "$USER" "$TEMP_CRON"
rm "$TEMP_CRON"

echo -e "${GREEN}=========================================="
echo "Installation Complete!"
echo -e "==========================================${NC}"
echo ""
echo "Configuration:"
echo "  - Scripts: $INSTALL_DIR"
echo "  - Logs: $LOG_DIR"
echo "  - User: $USER"
echo ""
echo "The manager will start automatically on next reboot."
echo ""
echo "To start manually now:"
echo -e "  ${YELLOW}sudo -u $USER $INSTALL_DIR/start_mawaqit_manager.sh &${NC}"
echo ""
echo "To view logs:"
echo -e "  ${YELLOW}tail -f $LOG_DIR/supervisor.log${NC}"
echo -e "  ${YELLOW}tail -f $LOG_DIR/log_mawaqit_stream.log${NC}"
echo ""
echo "To stop:"
echo -e "  ${YELLOW}pkill -f mawaqit_stream_manager.py${NC}"
echo ""
