#!/usr/bin/env bash
# ==============================================================================
# Project: Telecom Tower Failure Prediction Service
# Group: Group 3 (Nishant & Bitu)
# Course: Elective II: Machine Learning Operations (MLOps)
# Faculty: Dr. Santosh Kumar
#
# Script: healthcheck_watchdog.sh
# Purpose: Task 7 - Automated Health Inspection, Loop Prevention & Self-Healing
#
# Requirements Satisfied:
# 1. Checks service /health at regular intervals with timestamped logging.
# 2. Restarts the container service if degraded or unresponsive.
# 3. Loops Prevention: Enforces max consecutive restart attempts before backoff cooldown.
# 4. Triggers logrotate / internal log rotation to prevent disk bloat.
# ==============================================================================

set -euo pipefail

# Configuration
SERVICE_URL="http://127.0.0.1:8000/health"
SERVICE_NAME="telecom_tower_service"
LOG_FILE="/var/log/telecom_watchdog.log"
STATE_FILE="/tmp/telecom_watchdog_fail_count"
MAX_CONSECUTIVE_RESTARTS=3
TIMEOUT_SECONDS=4
MAX_LOG_SIZE_KB=1024 # 1MB log threshold for self-rotation

# Ensure log directory & files exist if run in user space
if [[ ! -w "/var/log" ]]; then
    LOG_FILE="$(dirname "$0")/telecom_watchdog.log"
    STATE_FILE="/tmp/telecom_watchdog_user_fail_count"
fi

log_msg() {
    local level="$1"
    local msg="$2"
    local timestamp
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo "[$timestamp] [$level] $msg" | tee -a "$LOG_FILE"
}

# --- Step 1: Log Rotation Protection ---
rotate_logs_if_needed() {
    if [[ -f "$LOG_FILE" ]]; then
        local file_size_kb
        file_size_kb=$(du -k "$LOG_FILE" | cut -f1)
        if (( file_size_kb >= MAX_LOG_SIZE_KB )); then
            log_msg "INFO" "Log file size (${file_size_kb}KB) exceeded threshold. Rotating logs..."
            mv "$LOG_FILE" "${LOG_FILE}.1"
            touch "$LOG_FILE"
            chmod 644 "$LOG_FILE"
            log_msg "INFO" "Log rotation complete. Old log saved as ${LOG_FILE}.1."
        fi
    fi
}

# Read current consecutive failure count
get_fail_count() {
    if [[ -f "$STATE_FILE" ]]; then
        cat "$STATE_FILE"
    else
        echo "0"
    fi
}

set_fail_count() {
    echo "$1" > "$STATE_FILE"
}

# --- Main Execution ---
rotate_logs_if_needed

FAIL_COUNT=$(get_fail_count)

# Check HTTP Health
HTTP_CODE=$(curl -s -o /tmp/health_response.json -w "%{http_code}" --max-time "$TIMEOUT_SECONDS" "$SERVICE_URL" || echo "000")

if [[ "$HTTP_CODE" == "200" ]]; then
    log_msg "HEALTHY" "Endpoint $SERVICE_URL responded with HTTP 200. Service operational."
    # Reset failure counter upon healthy probe
    set_fail_count 0
    exit 0
else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    set_fail_count "$FAIL_COUNT"
    log_msg "CRITICAL" "Health probe failed! HTTP status: $HTTP_CODE (Consecutive failures: $FAIL_COUNT)"

    # Loop prevention check
    if (( FAIL_COUNT > MAX_CONSECUTIVE_RESTARTS )); then
        log_msg "FATAL" "Restart loop prevented! Service failed $FAIL_COUNT consecutive times. Threshold is $MAX_CONSECUTIVE_RESTARTS. Manual NOC intervention required. Aborting auto-restart."
        exit 2
    fi

    log_msg "WARN" "Initiating automated container recovery for service '$SERVICE_NAME'..."
    RESTART_START=$(date +%s)

    # Attempt recovery: Docker restart or systemd/process restart
    if command -v docker &> /dev/null && docker ps -a --format '{{.Names}}' | grep -q "^${SERVICE_NAME}$"; then
        docker restart "$SERVICE_NAME"
    elif command -v systemctl &> /dev/null; then
        sudo systemctl restart "$SERVICE_NAME" || true
    fi

    # Wait 3 seconds and re-probe to verify recovery
    sleep 3
    RECOVER_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT_SECONDS" "$SERVICE_URL" || echo "000")
    RESTART_END=$(date +%s)
    RECOVERY_TIME=$((RESTART_END - RESTART_START))

    if [[ "$RECOVER_HTTP" == "200" ]]; then
        log_msg "RECOVERED" "Service successfully recovered and healthy in ${RECOVERY_TIME}s. Auto-healing complete."
        set_fail_count 0
        exit 0
    else
        log_msg "ERROR" "Recovery probe returned HTTP $RECOVER_HTTP after restart attempt. Service still unhealthy."
        exit 1
    fi
fi
