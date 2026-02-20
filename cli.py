#!/usr/bin/env python3
"""Omnivo CLI — manage the background daemon.

Usage:
    omnivo start     Start the daemon (auto-starts on login)
    omnivo stop      Stop the daemon
    omnivo restart   Restart the daemon
    omnivo status    Show daemon status
    omnivo log       Tail daemon logs (Ctrl+C to stop)
    omnivo help      Show this help
"""

import argparse
import os
import subprocess
import sys

from services.launchd import (
    DATA_DIR,
    STDOUT_LOG,
    install,
    uninstall,
    is_loaded,
    get_status,
)


def snapshot_env():
    """Copy OPENAI_API_KEY to ~/.omnivo/.env so the daemon can access it."""
    os.makedirs(DATA_DIR, exist_ok=True)
    dest = os.path.join(DATA_DIR, ".env")

    # Try from current environment first
    api_key = os.getenv("OPENAI_API_KEY")

    # Fall back to project .env file
    if not api_key:
        project_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(project_env):
            with open(project_env) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENAI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip("'\"")
                        break

    if not api_key:
        print("Error: OPENAI_API_KEY not found in environment or .env file.")
        print("Set it in your .env file or export it before running 'start'.")
        sys.exit(1)

    with open(dest, "w") as f:
        f.write(f"OPENAI_API_KEY={api_key}\n")

    # Restrict permissions — contains API key
    os.chmod(dest, 0o600)
    print(f"API key snapshotted to {dest}")


def cmd_start():
    if is_loaded():
        print("Omnivo daemon is already running.")
        status = get_status()
        if status["pid"]:
            print(f"  PID: {status['pid']}")
        return

    snapshot_env()
    install()
    print("Omnivo daemon started.")
    print("  Logs:    omnivo log")
    print("  Stop:    omnivo stop")


def cmd_stop():
    if not is_loaded():
        print("Omnivo daemon is not running.")
        return

    uninstall()
    print("Omnivo daemon stopped.")


def cmd_restart():
    if is_loaded():
        uninstall()
        print("Omnivo daemon stopped.")

    snapshot_env()
    install()
    print("Omnivo daemon started.")


def cmd_status():
    status = get_status()
    if not status["loaded"]:
        print("Omnivo daemon: not running")
        return

    print("Omnivo daemon: running")
    if status["pid"]:
        print(f"  PID:   {status['pid']}")
    if status["state"]:
        print(f"  State: {status['state']}")
    print(f"  Logs:  {STDOUT_LOG}")


def cmd_log():
    if not os.path.exists(STDOUT_LOG):
        print(f"No log file yet at {STDOUT_LOG}")
        print("Start the daemon first: omnivo start")
        return

    try:
        subprocess.run(["tail", "-f", STDOUT_LOG])
    except KeyboardInterrupt:
        pass


def cmd_help():
    print(__doc__.strip())


def main():
    parser = argparse.ArgumentParser(
        prog="omnivo",
        description="Omnivo — manage the background daemon",
        add_help=False,
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("start", help="Start the daemon (auto-starts on login)")
    sub.add_parser("stop", help="Stop the daemon")
    sub.add_parser("restart", help="Restart the daemon")
    sub.add_parser("status", help="Show daemon status")
    sub.add_parser("log", help="Tail daemon logs (Ctrl+C to stop)")
    sub.add_parser("help", help="Show help")

    args = parser.parse_args()
    if not args.command:
        cmd_help()
        sys.exit(1)

    commands = {
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
        "log": cmd_log,
        "help": cmd_help,
    }
    commands[args.command]()


if __name__ == "__main__":
    main()
