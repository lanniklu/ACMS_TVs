# ACMS MAWAQIT Stream Manager - Deployment Guide

## Architecture

```
Boot
  ↓
Crontab (@reboot)
  ↓
start_mawaqit_manager.sh (supervisor with while true)
  ↓
mawaqit_stream_manager.py (main application)
  ↓ (crash/exit)
Automatic restart by supervisor
```

## Quick Installation

### 1. Copy files to server
```bash
scp mawaqit_stream_manager.py acms_tech@10.1.5.10:/tmp/
scp mawaqit_box_setup.py acms_tech@10.1.5.10:/tmp/
scp start_mawaqit_manager.sh acms_tech@10.1.5.10:/tmp/
scp install.sh acms_tech@10.1.5.10:/tmp/
```

### 2. Run installation
```bash
ssh acms_tech@10.1.5.10
cd /tmp
sudo bash install.sh
```

### 3. Start manager (optional - will auto-start on reboot)
```bash
sudo -u acms_tech /home/acms_tech/scripts/start_mawaqit_manager.sh &
```

## Manual Installation

If you prefer manual setup:

### 1. Create directories
```bash
sudo mkdir -p /home/acms_tech/scripts
sudo mkdir -p /home/acms_tech/logs
```

### 2. Copy scripts
```bash
sudo cp mawaqit_stream_manager.py /home/acms_tech/scripts/
sudo cp mawaqit_box_setup.py /home/acms_tech/scripts/
sudo cp start_mawaqit_manager.sh /home/acms_tech/scripts/
```

### 3. Set permissions
```bash
sudo chmod +x /home/acms_tech/scripts/*.sh
sudo chmod +x /home/acms_tech/scripts/*.py
sudo chown -R acms_tech:acms_tech /home/acms_tech/scripts
sudo chown -R acms_tech:acms_tech /home/acms_tech/logs
```

### 4. Configure crontab
```bash
sudo crontab -u acms_tech -e
```

Add this line:
```
@reboot /home/acms_tech/scripts/start_mawaqit_manager.sh >> /home/acms_tech/logs/supervisor.log 2>&1 &
```

## Management Commands

### View logs
```bash
# Supervisor logs (restart events)
tail -f /home/acms_tech/logs/supervisor.log

# Application logs (detailed operation)
tail -f /home/acms_tech/logs/log_mawaqit_stream.log
```

### Stop manager
```bash
# Graceful stop (sends SIGTERM)
sudo pkill -TERM -f mawaqit_stream_manager.py

# Force stop (sends SIGKILL)
sudo pkill -9 -f mawaqit_stream_manager.py

# Stop supervisor too
sudo pkill -f start_mawaqit_manager.sh
```

### Start manager manually
```bash
sudo -u acms_tech /home/acms_tech/scripts/start_mawaqit_manager.sh &
```

### Check if running
```bash
ps aux | grep mawaqit_stream_manager.py
```

### View current status
```bash
# Last 50 lines of application log
tail -50 /home/acms_tech/logs/log_mawaqit_stream.log

# Check restart count
grep "restart #" /home/acms_tech/logs/supervisor.log | tail -5
```

## Exit Codes

The manager uses specific exit codes for supervisor control:

- **0**: Clean exit (will restart)
- **1**: Error exit with retry delay (will restart after 30s)
- **2**: Another instance already running (supervisor stops)

## Configuration

Edit parameters in `mawaqit_stream_manager.py`:

```python
# Network scanning
VLAN2_SCAN_START = 40
VLAN2_SCAN_END = 120

# Timeouts
TIMEOUT_SCAN = 2
TIMEOUT_DEVICE_CONNECT = 5
TIMEOUT_SOURCE_CHECK = 3

# Check interval
CHECK_INTERVAL = 5

# Anti-flap protection
ANTI_FLAP_TIME = 10

# Retry delay (prevents rapid restart loops)
RETRY_DELAY_ON_INIT_FAIL = 30
```

## Troubleshooting

### Manager doesn't start on boot
```bash
# Check crontab
sudo crontab -u acms_tech -l

# Check supervisor log
cat /home/acms_tech/logs/supervisor.log
```

### Rapid restart loop
The manager includes protection against rapid restarts:
- If initialization fails, waits 30s before exit
- Supervisor waits 5s between restarts
- Check logs to identify the root cause

### Multiple instances
The manager uses a PID file at `/var/run/mawaqit_stream_manager.pid` to prevent multiple instances.

If stuck, remove it:
```bash
sudo rm /var/run/mawaqit_stream_manager.pid
```

### No boxes discovered
```bash
# Check network connectivity
ping 10.1.2.101

# Check ADB server
adb devices

# Manually scan
nmap -p 5555 10.1.2.40-120
```

## Logs Rotation

To prevent logs from growing too large, setup logrotate:

```bash
sudo nano /etc/logrotate.d/mawaqit
```

Add:
```
/home/acms_tech/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 acms_tech acms_tech
}
```

## Monitoring

### Create a monitoring script
```bash
#!/bin/bash
# /home/acms_tech/scripts/check_mawaqit.sh

if ! pgrep -f mawaqit_stream_manager.py > /dev/null; then
    echo "ALERT: MAWAQIT manager not running!"
    # Send email/notification here
fi
```

Add to crontab:
```
*/5 * * * * /home/acms_tech/scripts/check_mawaqit.sh
```
