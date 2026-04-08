#!/usr/bin/env python3
"""Omnivo CLI — manage the background daemon.

Usage:
    omnivo start              Start the daemon (auto-starts on login)
    omnivo stop               Stop the daemon
    omnivo restart            Restart the daemon
    omnivo status             Show daemon status (and current model/punctuation)
    omnivo log                Tail daemon logs (Ctrl+C to stop)
    omnivo model [whisper|transcribe]   Show or set the transcription model
    omnivo punctuation [on|off]         Show or set the punctuation prompt mode
    omnivo help               Show this help
"""

import argparse
import os
import subprocess
import sys
import time

from core.settings import load_settings, save_settings, VALID_MODELS
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
        time.sleep(1)  # launchd needs a moment between bootout and bootstrap

    snapshot_env()
    install()
    print("Omnivo daemon started.")


def cmd_status():
    settings = load_settings()
    model_label = settings["model"]
    punct_label = "on" if settings["punctuation"] else "off"

    status = get_status()
    if not status["loaded"]:
        print("Omnivo daemon: not running")
        print(f"  Model:       {model_label}")
        print(f"  Punctuation: {punct_label}")
        return

    print("Omnivo daemon: running")
    if status["pid"]:
        print(f"  PID:         {status['pid']}")
    if status["state"]:
        print(f"  State:       {status['state']}")
    print(f"  Model:       {model_label}")
    print(f"  Punctuation: {punct_label}")
    print(f"  Logs:        {STDOUT_LOG}")


def cmd_model(value):
    """Show or set the dictation transcription model."""
    if value is None:
        current = load_settings()["model"]
        print(f"Current model: {current}")
        return

    if value not in VALID_MODELS:
        print(
            f"Error: model must be one of {', '.join(VALID_MODELS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    save_settings(model=value)
    pretty = "gpt-4o-transcribe" if value == "transcribe" else "whisper-1"
    print(f"Model set to: {value} ({pretty})")

    # If the user is switching to whisper while punctuation is on, warn —
    # informational only, doesn't block.
    if value == "whisper" and load_settings()["punctuation"]:
        print("Note: punctuation mode is on, but won't have any effect with whisper.")


def cmd_punctuation(value):
    """Show or set the punctuation prompt mode."""
    if value is None:
        current = load_settings()["punctuation"]
        print(f"Punctuation: {'on' if current else 'off'}")
        return

    if value not in ("on", "off"):
        print("Error: punctuation must be 'on' or 'off'", file=sys.stderr)
        sys.exit(1)

    enable = value == "on"

    if enable:
        current_model = load_settings()["model"]
        if current_model == "whisper":
            print("Punctuation only takes effect with the gpt-4o-transcribe model.")
            # Non-interactive: just warn and set the flag.
            if not sys.stdin.isatty():
                print(
                    "stdin is not a tty — leaving model as whisper. "
                    "Run `omnivo model transcribe` to make punctuation effective."
                )
                save_settings(punctuation=True)
                print("Punctuation enabled.")
                return

            # Interactive prompt.
            try:
                answer = (
                    input(
                        "You're currently on whisper. "
                        "Switch to gpt-4o-transcribe now? [y/N]: "
                    )
                    .strip()
                    .lower()
                )
            except EOFError:
                answer = ""

            if answer == "y":
                save_settings(model="transcribe", punctuation=True)
                print("Model set to: transcribe")
                print("Punctuation enabled.")
                return

            # User declined — still respect the punctuation toggle.
            save_settings(punctuation=True)
            print("Punctuation enabled.")
            print(
                "Note: punctuation won't take effect until you run "
                "`omnivo model transcribe`."
            )
            return

        # Already on transcribe — just flip the flag.
        save_settings(punctuation=True)
        print("Punctuation enabled.")
        return

    # value == "off"
    save_settings(punctuation=False)
    print("Punctuation disabled.")


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
    p_model = sub.add_parser("model", help="Show or set the transcription model")
    p_model.add_argument(
        "value",
        nargs="?",
        choices=list(VALID_MODELS),
        help="whisper or transcribe (omit to show current)",
    )
    p_punct = sub.add_parser(
        "punctuation", help="Show or set the punctuation prompt mode"
    )
    p_punct.add_argument(
        "value",
        nargs="?",
        choices=["on", "off"],
        help="on or off (omit to show current)",
    )

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
        "model": lambda: cmd_model(args.value),
        "punctuation": lambda: cmd_punctuation(args.value),
    }
    commands[args.command]()


if __name__ == "__main__":
    main()
