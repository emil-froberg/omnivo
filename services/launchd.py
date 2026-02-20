"""macOS LaunchAgent lifecycle management for Omnivo daemon."""

import os
import sys
import plistlib
import subprocess

LABEL = "com.omnivo.daemon"
DATA_DIR = os.path.expanduser("~/.omnivo")
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
STDOUT_LOG = os.path.join(DATA_DIR, "daemon.stdout.log")
STDERR_LOG = os.path.join(DATA_DIR, "daemon.stderr.log")


def _project_dir():
    """Return the omnivo project root directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_from_dotenv(path):
    """Parse a .env file into a dict of key=value pairs."""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                env[key] = value
    return env


def generate_plist():
    """Build a launchd plist dict for the Omnivo daemon."""
    project_dir = _project_dir()
    env_file = os.path.join(DATA_DIR, ".env")

    # Read env vars from the snapshotted .env
    env_vars = _env_from_dotenv(env_file)
    # Ensure PATH includes common locations for ffmpeg etc.
    env_vars.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin")

    # Resolve symlinks — macOS Accessibility checks the real binary path
    python_bin = os.path.realpath(sys.executable)

    plist = {
        "Label": LABEL,
        "ProgramArguments": [python_bin, os.path.join(project_dir, "main.py")],
        "WorkingDirectory": project_dir,
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "StandardOutPath": STDOUT_LOG,
        "StandardErrorPath": STDERR_LOG,
        "EnvironmentVariables": env_vars,
    }
    return plist


def ensure_data_dir():
    """Create ~/.omnivo/ if it doesn't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)


def install():
    """Write plist and bootstrap the LaunchAgent."""
    ensure_data_dir()

    # Clear stale logs so we only see output from this launch
    for log in (STDOUT_LOG, STDERR_LOG):
        open(log, "w").close()

    plist = generate_plist()
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)

    uid = os.getuid()
    domain = f"gui/{uid}"

    # Bootout first in case it's already loaded (ignore errors)
    subprocess.run(
        ["launchctl", "bootout", f"{domain}/{LABEL}"],
        capture_output=True,
    )

    result = subprocess.run(
        ["launchctl", "bootstrap", domain, PLIST_PATH],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"launchctl bootstrap failed: {result.stderr.strip()}")


def uninstall():
    """Bootout the LaunchAgent and remove the plist."""
    uid = os.getuid()
    domain = f"gui/{uid}"

    subprocess.run(
        ["launchctl", "bootout", f"{domain}/{LABEL}"],
        capture_output=True,
    )

    if os.path.exists(PLIST_PATH):
        os.remove(PLIST_PATH)


def is_loaded():
    """Check if the LaunchAgent is currently loaded."""
    uid = os.getuid()
    result = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{LABEL}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def get_status():
    """Get daemon status info. Returns dict with 'loaded', 'pid', 'state'."""
    uid = os.getuid()
    result = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{LABEL}"],
        capture_output=True,
        text=True,
    )

    status = {"loaded": False, "pid": None, "state": None}

    if result.returncode != 0:
        return status

    status["loaded"] = True
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("pid ="):
            try:
                status["pid"] = int(line.split("=")[1].strip())
            except (ValueError, IndexError):
                pass
        elif line.startswith("state ="):
            status["state"] = line.split("=")[1].strip()

    return status
