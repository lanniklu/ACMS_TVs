#!/bin/bash

################################################################################
# START_MAWAQIT_MANAGER.SH - Supervisor script for AUTO_StreamACMS
# 
# Purpose:
#   Automatically manages the mawaqit_stream_manager.py process
#   Restarts on failure, handles dependencies, manages logs
#
# Usage (crontab):
#   @reboot /home/acms_tech/AUTO_StreamACMS/start_mawaqit_manager.sh
#
# Exit codes:
#   0: Clean exit (process was running, stopped by signal)
#   1: Initialization error (fatal)
#   2: Process already running (another instance active)
#   3: Missing dependencies
#   4: Permission error
################################################################################

set -u  # Exit on undefined variables
IFS=$'\n\t'  # Secure IFS

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_DIR="/home/acms_tech/AUTO_StreamACMS"
PYTHON_SCRIPT="${BASE_DIR}/MANAGER/mawaqit_stream_manager.py"
LOG_DIR="${BASE_DIR}/logs"
LOG_FILE="${LOG_DIR}/supervisor.log"
PID_FILE="${LOG_DIR}/mawaqit_stream_manager.pid"

PYTHON_EXECUTABLE="python3"
INITIAL_WAIT=5          # Wait before first restart attempt
RESTART_DELAY=5         # Delay between restart attempts
MAX_CONSECUTIVE_FAILURES=5  # Max failures before giving up
WATCHDOG_TIMEOUT=600    # Restart if process silent for 10 min

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

log_msg() {
    local level="$1"
    local msg="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${msg}" | tee -a "${LOG_FILE}"
}

log_info() {
    log_msg "INFO " "$1"
}

log_warn() {
    log_msg "WARN " "$1"
}

log_error() {
    log_msg "ERROR" "$1"
}

# ============================================================================
# DEPENDENCY CHECKS
# ============================================================================

check_dependencies() {
    log_info "Checking dependencies..."
    
    # Check Python
    if ! command -v "${PYTHON_EXECUTABLE}" &> /dev/null; then
        log_error "Python3 not found: ${PYTHON_EXECUTABLE}"
        log_error "Install with: sudo apt-get install python3"
        return 3
    fi
    
    # Check Python version (3.7+)
    local python_version=$("${PYTHON_EXECUTABLE}" --version 2>&1 | awk '{print $2}')
    log_info "Python version: ${python_version}"
    
    # Check ADB
    if ! command -v adb &> /dev/null; then
        log_warn "ADB not found - Android device management unavailable"
        log_warn "Install with: sudo apt-get install adb"
        # Don't return error - ADB might be optional or will be set up later
    else
        log_info "ADB found: $(adb version 2>/dev/null | head -1)"
    fi
    
    # Check required Python packages
    if ! "${PYTHON_EXECUTABLE}" -c "import requests" 2>/dev/null; then
        log_info "Installing required Python packages..."
        "${PYTHON_EXECUTABLE}" -m pip install -q requests
    fi
    
    # Check directories
    if [[ ! -d "${BASE_DIR}" ]]; then
        log_error "Base directory not found: ${BASE_DIR}"
        return 3
    fi
    
    if [[ ! -f "${PYTHON_SCRIPT}" ]]; then
        log_error "Python script not found: ${PYTHON_SCRIPT}"
        return 3
    fi
    
    # Create log directory if needed
    mkdir -p "${LOG_DIR}" || {
        log_error "Cannot create log directory: ${LOG_DIR}"
        return 4
    }
    
    log_info "All dependencies OK"
    return 0
}

# ============================================================================
# PID FILE MANAGEMENT
# ============================================================================

check_existing_process() {
    # Check if another instance is already running
    if [[ -f "${PID_FILE}" ]]; then
        local old_pid=$(cat "${PID_FILE}" 2>/dev/null)
        
        if [[ -z "${old_pid}" ]]; then
            log_warn "PID file exists but is empty, removing..."
            rm -f "${PID_FILE}"
            return 0
        fi
        
        # Check if process is alive
        if kill -0 "${old_pid}" 2>/dev/null; then
            log_error "Another instance already running (PID: ${old_pid})"
            return 2
        else
            log_warn "PID file exists but process dead (PID: ${old_pid}), cleaning up..."
            rm -f "${PID_FILE}"
            return 0
        fi
    fi
    return 0
}

# ============================================================================
# PROCESS MONITORING
# ============================================================================

wait_for_process() {
    # Wait for process to finish or timeout (0 = no hard timeout)
    local pid=$1
    local timeout=${2:-0}  # 0 disables hard timeout
    local start_time=$(date +%s)
    
    while true; do
        # Check if process is still running
        if ! kill -0 "${pid}" 2>/dev/null; then
            # Process terminated
            wait "${pid}" 2>/dev/null
            local exit_code=$?
            return "${exit_code}"
        fi
        
        # Check timeout
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        if [[ ${timeout} -gt 0 && ${elapsed} -gt ${timeout} ]]; then
            log_error "Process timeout (${elapsed}s > ${timeout}s), killing..."
            kill -TERM "${pid}" 2>/dev/null
            sleep 2
            kill -KILL "${pid}" 2>/dev/null || true
            return 124  # Timeout exit code
        fi
        
        # Check watchdog file (if created by script)
        if [[ -f "${LOG_DIR}/mawaqit_heartbeat.txt" ]]; then
            local heartbeat_time=$(cat "${LOG_DIR}/mawaqit_heartbeat.txt" 2>/dev/null | head -1)
            local current_time_unix=$(date +%s)
            
            if [[ -n "${heartbeat_time}" ]]; then
                # Heartbeat may include fractional seconds; strip decimals
                local heartbeat_time_int="${heartbeat_time%%.*}"
                if [[ "${heartbeat_time_int}" =~ ^[0-9]+$ ]]; then
                    local heartbeat_age=$((current_time_unix - heartbeat_time_int))
                    if [[ ${heartbeat_age} -gt ${WATCHDOG_TIMEOUT} ]]; then
                        log_warn "Watchdog timeout: heartbeat stale for ${heartbeat_age}s"
                        log_warn "Killing unresponsive process ${pid}..."
                        kill -KILL "${pid}" 2>/dev/null || true
                        sleep 1
                        return 1
                    fi
                fi
            fi
        fi
        
        sleep 5  # Check every 5 seconds
    done
}

# ============================================================================
# MAIN SUPERVISOR LOOP
# ============================================================================

main_loop() {
    local consecutive_failures=0
    local restart_count=0
    
    log_info "Starting main supervisor loop"
    
    while true; do
        # Check for system signals
        if [[ ! -d /proc/$$ ]]; then
            log_info "Parent process died, exiting"
            return 0
        fi
        
        # Log restart attempt
        restart_count=$((restart_count + 1))
        log_info "Restart attempt #${restart_count} (consecutive failures: ${consecutive_failures}/${MAX_CONSECUTIVE_FAILURES})"
        
        # Start Python script
        log_info "Starting: ${PYTHON_EXECUTABLE} ${PYTHON_SCRIPT}"
        
        # Run in background and capture PID
        cd "${BASE_DIR}" || {
            log_error "Cannot change to ${BASE_DIR}"
            sleep "${RESTART_DELAY}"
            continue
        }
        
        "${PYTHON_EXECUTABLE}" "${PYTHON_SCRIPT}" &
        local python_pid=$!
        
        log_info "Process started with PID ${python_pid}"
        
        # Wait for process to finish
        wait_for_process "${python_pid}"
        local exit_code=$?
        
        # Process finished
        if [[ ${exit_code} -eq 0 ]]; then
            log_info "Process exited cleanly (exit code 0)"
            return 0
        elif [[ ${exit_code} -eq 2 ]]; then
            log_warn "Another instance detected (exit code 2)"
            return 2
        elif [[ ${exit_code} -eq 124 ]]; then
            log_error "Process timeout/killed (exit code 124)"
            consecutive_failures=$((consecutive_failures + 1))
        else
            log_warn "Process exited with code ${exit_code}"
            consecutive_failures=$((consecutive_failures + 1))
        fi
        
        # Check for too many consecutive failures
        if [[ ${consecutive_failures} -ge ${MAX_CONSECUTIVE_FAILURES} ]]; then
            log_error "Too many consecutive failures (${consecutive_failures}/${MAX_CONSECUTIVE_FAILURES})"
            log_error "Giving up - please check logs: ${LOG_FILE}"
            return 1
        fi
        
        # Wait before restart
        log_info "Waiting ${RESTART_DELAY}s before restart..."
        sleep "${RESTART_DELAY}"
    done
}

# ============================================================================
# SIGNAL HANDLING
# ============================================================================

trap_handler() {
    local sig=$1
    log_info "Received signal ${sig}, initiating graceful shutdown"
    
    # Kill Python process if running
    if [[ -f "${PID_FILE}" ]]; then
        local python_pid=$(cat "${PID_FILE}" 2>/dev/null)
        if [[ -n "${python_pid}" ]] && kill -0 "${python_pid}" 2>/dev/null; then
            log_info "Sending SIGTERM to Python process ${python_pid}"
            kill -TERM "${python_pid}" 2>/dev/null || true
            
            # Wait for graceful exit (5 seconds)
            sleep 5
            
            # Force kill if still running
            if kill -0 "${python_pid}" 2>/dev/null; then
                log_warn "Process still running, force killing..."
                kill -KILL "${python_pid}" 2>/dev/null || true
            fi
        fi
    fi
    
    exit 0
}

# Register signal handlers
trap 'trap_handler SIGTERM' SIGTERM
trap 'trap_handler SIGINT' SIGINT

# ============================================================================
# ENTRY POINT
# ============================================================================

main() {
    # Initialize logging
    mkdir -p "$(dirname "${LOG_FILE}")" || {
        echo "ERROR: Cannot create log directory: $(dirname "${LOG_FILE}")"
        exit 4
    }
    
    log_info "========================================================================"
    log_info "MAWAQIT STREAM MANAGER - SUPERVISOR SCRIPT"
    log_info "========================================================================"
    log_info "Base directory: ${BASE_DIR}"
    log_info "Python script: ${PYTHON_SCRIPT}"
    log_info "Log file: ${LOG_FILE}"
    log_info "PID file: ${PID_FILE}"
    log_info "========================================================================"
    
    # Check dependencies
    check_dependencies
    local dep_result=$?
    if [[ ${dep_result} -ne 0 ]]; then
        exit "${dep_result}"
    fi
    
    # Wait for system to stabilize on first boot
    log_info "Waiting ${INITIAL_WAIT}s for system stabilization..."
    sleep "${INITIAL_WAIT}"
    
    # Check if another instance is running
    check_existing_process
    local check_result=$?
    if [[ ${check_result} -ne 0 ]]; then
        exit "${check_result}"
    fi
    
    # Enter main loop
    main_loop
    local main_result=$?
    
    log_info "========================================================================"
    log_info "Supervisor exiting with code ${main_result}"
    log_info "========================================================================"
    
    exit "${main_result}"
}

# Run main function
main "$@"
