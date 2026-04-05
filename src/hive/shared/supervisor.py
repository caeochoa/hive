from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DEFAULT_CONF_DIR = Path.home() / ".config" / "hive" / "supervisord" / "conf.d"
SUPERVISORD_CONF = Path.home() / ".config" / "hive" / "supervisord" / "supervisord.conf"
LAUNCHAGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.hive.supervisord.plist"

SUPERVISORD_CONF_TEMPLATE = """\
[supervisord]
nodaemon=false
logfile={home}/.config/hive/supervisord/supervisord.log
pidfile={home}/.config/hive/supervisord/supervisord.pid

[unix_http_server]
file={home}/.config/hive/supervisord/supervisor.sock

[supervisorctl]
serverurl=unix://{home}/.config/hive/supervisord/supervisor.sock

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[include]
files = {conf_dir}/*.conf
"""

WORKER_BLOCK_TEMPLATE = """\
[program:worker-{name}]
command=hive run {path}
directory={path}
autostart=true
autorestart=true
stdout_logfile={path}/logs/out.log
stderr_logfile={path}/logs/err.log
"""

COMB_BLOCK_TEMPLATE = """\
[program:hive-comb]
command=hive comb serve --host 0.0.0.0
autostart=true
autorestart=true
stdout_logfile={home}/.config/hive/comb.log
stderr_logfile={home}/.config/hive/comb.err.log
"""

LAUNCHAGENT_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.hive.supervisord</string>
  <key>ProgramArguments</key>
  <array>
    <string>{supervisord}</string>
    <string>-c</string>
    <string>{conf}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
"""


def get_worker_conf_path(name: str, conf_dir: Path = DEFAULT_CONF_DIR) -> Path:
    return conf_dir / f"worker-{name}.conf"


def write_worker_block(name: str, worker_path: Path, conf_dir: Path = DEFAULT_CONF_DIR) -> None:
    conf_dir.mkdir(parents=True, exist_ok=True)
    conf_file = get_worker_conf_path(name, conf_dir)
    conf_file.write_text(
        WORKER_BLOCK_TEMPLATE.format(name=name, path=str(worker_path))
    )


def remove_worker_block(name: str, conf_dir: Path = DEFAULT_CONF_DIR) -> None:
    conf_file = get_worker_conf_path(name, conf_dir)
    if conf_file.exists():
        conf_file.unlink()


def ensure_supervisord_conf(conf_dir: Path = DEFAULT_CONF_DIR) -> None:
    """Create the main supervisord.conf if it doesn't exist."""
    SUPERVISORD_CONF.parent.mkdir(parents=True, exist_ok=True)
    if not SUPERVISORD_CONF.exists():
        home = Path.home()
        SUPERVISORD_CONF.write_text(
            SUPERVISORD_CONF_TEMPLATE.format(home=home, conf_dir=conf_dir)
        )


def write_comb_block(conf_dir: Path = DEFAULT_CONF_DIR) -> None:
    conf_dir.mkdir(parents=True, exist_ok=True)
    comb_conf = conf_dir / "hive-comb.conf"
    comb_conf.write_text(COMB_BLOCK_TEMPLATE.format(home=Path.home()))


def install_launchagent() -> bool:
    """Install macOS LaunchAgent for supervisord. Returns True if newly installed."""
    newly_written = False
    if not LAUNCHAGENT_PLIST.exists():
        supervisord_bin = shutil.which("supervisord")
        if not supervisord_bin:
            raise RuntimeError("supervisord not found in PATH")
        LAUNCHAGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
        LAUNCHAGENT_PLIST.write_text(
            LAUNCHAGENT_TEMPLATE.format(
                supervisord=supervisord_bin,
                conf=str(SUPERVISORD_CONF),
            )
        )
        newly_written = True

    # -w ensures the service is marked enabled so it auto-loads after reboots
    result = subprocess.run(["launchctl", "load", "-w", str(LAUNCHAGENT_PLIST)])
    if result.returncode != 0:
        raise RuntimeError(f"launchctl load -w failed (exit {result.returncode})")
    return newly_written


def supervisorctl(*args: str) -> subprocess.CompletedProcess:
    """Run supervisorctl with the Hive config."""
    cmd = ["supervisorctl", "-c", str(SUPERVISORD_CONF), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def is_launchagent_installed() -> bool:
    """Check if the macOS LaunchAgent plist exists and is bootstrapped."""
    if not LAUNCHAGENT_PLIST.exists():
        return False
    result = subprocess.run(
        ["launchctl", "list", "com.hive.supervisord"],
        capture_output=True,
    )
    return result.returncode == 0


def reload_supervisord() -> None:
    """Signal supervisord to reread and update config."""
    supervisorctl("reread")
    supervisorctl("update")
