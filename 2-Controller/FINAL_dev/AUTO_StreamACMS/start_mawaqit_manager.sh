#!/bin/bash
###############################################################################
# MAWAQIT Stream Manager Supervisor Script
# Purpose: Ensures mawaqit_stream_manager.py runs continuously with auto-restart
# Launched by: crontab @reboot
###############################################################################

# Configuration
SCRIPT_DIR="/home/acms_tech/AUTO_StreamACMS"
LOG_DIR="/home/acms_tech/AUTO_StreamACMS/logs"
SCRIPT_NAME="mawaqit_stream_manager.py"
SUPERVISOR_LOG="$LOG_DIR/supervisor.log"
RESTART_DELAY=5  # Seconds to wait between restarts

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Function to log with timestamp
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$SUPERVISOR_LOG"
}

# Function to check if Python3 is available
check_dependencies() {
    if ! command -v python3 &> /dev/null; then
        log_message "ERROR: python3 not found. Please install Python 3."
        exit 1
    fi
    
    if ! command -v adb &> /dev/null; then
        log_message "ERROR: adb not found. Please install Android Debug Bridge."
        exit 1
    fi
    
    if [ ! -f "$SCRIPT_DIR/$SCRIPT_NAME" ]; then
        log_message "ERROR: Script not found at $SCRIPT_DIR/$SCRIPT_NAME"
        exit 1
    fi
}

# Main supervisor loop
log_message "=========================================="
log_message "MAWAQIT Manager Supervisor Starting"
log_message "=========================================="
log_message "Script: $SCRIPT_DIR/$SCRIPT_NAME"
log_message "Logs: $LOG_DIR"
log_message "Restart delay: ${RESTART_DELAY}s"
log_message "=========================================="

# Check dependencies once at startup
check_dependencies

# Infinite supervision loop
RESTART_COUNT=0

while true; do
    RESTART_COUNT=$((RESTART_COUNT + 1))
    
    log_message "Starting mawaqit_stream_manager.py (restart #$RESTART_COUNT)..."
    
    # Run the Python script
    cd "$SCRIPT_DIR" || exit 1
    python3 "$SCRIPT_DIR/$SCRIPT_NAME"
    
    # Capture exit code
    EXIT_CODE=$?
    
    # Log exit reason
    case $EXIT_CODE in
        0)
            log_message "Process exited cleanly (code 0). Restarting in ${RESTART_DELAY}s..."
            ;;
        1)
            log_message "Process exited with error (code 1). Restarting in ${RESTART_DELAY}s..."
            ;;
        2)
            log_message "Process exited: another instance already running (code 2). Stopping supervisor."
            exit 2
            ;;
        *)
            log_message "Process exited with unknown code $EXIT_CODE. Restarting in ${RESTART_DELAY}s..."
            ;;
    esac
    
    # Wait before restart to prevent rapid crash loops
    sleep "$RESTART_DELAY"
done
