#!/usr/bin/env python3
"""
Monitor long-running task agents and handle timeouts.

Launches a command as a subprocess, polls every 30 seconds,
kills on timeout (SIGTERM → SIGKILL after 5s), retries up to N times.
Logs all activity to agent_monitor.log.

Usage:
  python3 agent_monitor.py --command "python3 generate.py" --timeout 480 --retry 2
  python3 agent_monitor.py --command "sleep 120" --timeout 30 --retry 1
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOG_FILE = Path.cwd() / "agent_monitor.log"
POLL_INTERVAL = 30
KILL_GRACE_SECONDS = 5


def setup_logging() -> None:
    """Configure file-only logging to agent_monitor.log."""
    handler = logging.FileHandler(str(LOG_FILE), mode="a")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger = logging.getLogger("agent_monitor")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)


def log_and_print(message: str, level: str = "INFO") -> None:
    """Log to file and print to stdout."""
    logger = logging.getLogger("agent_monitor")
    if level == "ERROR":
        logger.error(message)
    elif level == "WARNING":
        logger.warning(message)
    else:
        logger.info(message)
    print(message, flush=True)


def terminate_process(
    proc: subprocess.Popen[bytes], pid: int
) -> bool:
    """Send SIGTERM, wait KILL_GRACE_SECONDS, then SIGKILL if still alive."""
    log_and_print(f"Sending SIGTERM to PID {pid}...", "WARNING")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass

    for _ in range(KILL_GRACE_SECONDS * 2):
        if proc.poll() is not None:
            log_and_print(f"Process {pid} terminated via SIGTERM.")
            return True
        time.sleep(0.5)

    log_and_print(f"Sending SIGKILL to PID {pid}...", "WARNING")
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    time.sleep(1)
    if proc.poll() is None:
        log_and_print(f"Process {pid} still running after SIGKILL!", "ERROR")
        return False
    log_and_print(f"Process {pid} killed via SIGKILL.")
    return True


def run_command(
    command: str, timeout_seconds: int
) -> tuple[int, str, str]:
    """Launch command as subprocess, return (exit_code, stdout, stderr)."""
    log_and_print(f"Launching: {command}")
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )
    except Exception as exc:
        log_and_print(f"Failed to launch process: {exc}", "ERROR")
        return 1, "", str(exc)

    pid = proc.pid
    log_and_print(f"Agent started (PID: {pid})")
    start_time = time.time()

    while proc.poll() is None:
        elapsed = int(time.time() - start_time)
        if elapsed > 0 and elapsed % POLL_INTERVAL == 0:
            log_and_print(f"Agent running... ({elapsed}s elapsed)")
        if elapsed >= timeout_seconds:
            log_and_print(
                f"Agent timeout after {elapsed}s (limit: {timeout_seconds}s)",
                "WARNING",
            )
            terminated = terminate_process(proc, pid)
            if not terminated:
                log_and_print(
                    "Could not kill process; it may be hung.",
                    "ERROR",
                )
            stdout_data, stderr_data = proc.communicate(timeout=10)
            return -1, stdout_data.decode(
                "utf-8", errors="replace"
            ), stderr_data.decode("utf-8", errors="replace")
        time.sleep(1)

    total_time = int(time.time() - start_time)
    stdout_data, stderr_data = proc.communicate(timeout=10)
    exit_code = proc.returncode
    log_and_print(
        f"Agent completed in {total_time}s (exit code: {exit_code})"
    )
    return (
        exit_code,
        stdout_data.decode("utf-8", errors="replace"),
        stderr_data.decode("utf-8", errors="replace"),
    )


def monitor_agent(
    command: str, timeout_seconds: int, max_retries: int
) -> int:
    """
    Run command with timeout and retry logic.
    Returns 0 on success, 1 if all retries exhausted.
    """
    attempt = 0
    while attempt <= max_retries:
        if attempt > 0:
            log_and_print(
                f"Agent timeout - retrying ({attempt}/{max_retries})..."
            )
        exit_code, stdout, stderr = run_command(command, timeout_seconds)
        if exit_code == 0:
            log_and_print("Agent completed successfully.")
            return 0
        if exit_code == -1:
            attempt += 1
            continue
        attempt += 1
        if stderr:
            log_and_print(f"Agent stderr: {stderr[:500]}", "WARNING")
    log_and_print(
        f"All {max_retries} retries exhausted. Agent failed.",
        "ERROR",
    )
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor long-running task agents and handle timeouts."
    )
    parser.add_argument(
        "--command",
        required=True,
        help="The command to run as a subprocess.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        required=True,
        help="Timeout in seconds before killing the process.",
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=0,
        help="Maximum number of retries after timeout (default: 0).",
    )
    args = parser.parse_args()

    setup_logging()
    start_dt = datetime.now(timezone.utc).isoformat()
    log_and_print(
        f"=== Agent Monitor started at {start_dt} ==="
    )
    log_and_print(
        f"Command: {args.command} | Timeout: {args.timeout}s "
        f"| Max retries: {args.retry}"
    )

    exit_code = monitor_agent(args.command, args.timeout, args.retry)

    end_dt = datetime.now(timezone.utc).isoformat()
    log_and_print(
        f"=== Agent Monitor finished at {end_dt} "
        f"(exit: {exit_code}) ==="
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
