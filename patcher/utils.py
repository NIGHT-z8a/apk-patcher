"""Shared utilities: logging, tool discovery, path helpers."""

import os
import shutil
import subprocess
import sys


def banner(title: str) -> None:
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def step(title: str) -> None:
    print(f"\n[STEP] {title}")


def info(msg: str) -> None:
    print(f"  {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def error(msg: str) -> None:
    print(f"\n[ERROR] {msg}")


def run(cmd: str, desc: str = "", cwd: str | None = None) -> subprocess.CompletedProcess:
    if desc:
        step(desc)
    info(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=False, text=True, cwd=cwd)
    if result.returncode != 0:
        error(f"Command failed: {cmd}")
        sys.exit(1)
    return result


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def find_apksigner(base_path: str = "", versions: list[str] | None = None) -> str | None:
    """Find apksigner via ANDROID_HOME, ANDROID_SDK_ROOT, or common paths."""
    if versions is None:
        versions = [
            "37.0.0", "36.1.0", "35.0.0", "34.0.0", "33.0.0",
            "32.0.0", "31.0.0", "30.0.0",
        ]

    # Check ANDROID_HOME / ANDROID_SDK_ROOT first
    for env_var in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
        sdk_path = os.environ.get(env_var)
        if sdk_path:
            for ver in versions:
                candidate = os.path.join(sdk_path, "build-tools", ver, "apksigner")
                if os.path.exists(candidate):
                    return candidate

    # Check provided base path
    if base_path:
        for ver in versions:
            candidate = os.path.join(base_path, "build-tools", ver, "apksigner")
            if os.path.exists(candidate):
                return candidate

    # Check common system-wide locations
    common_paths = [
        os.path.expanduser("~/Android/Sdk"),
        os.path.expanduser("~/Library/Android/sdk"),
        "/opt/android-sdk",
        "/usr/lib/android-sdk",
    ]
    for sdk_path in common_paths:
        for ver in versions:
            candidate = os.path.join(sdk_path, "build-tools", ver, "apksigner")
            if os.path.exists(candidate):
                return candidate

    return None


def find_tool(name: str) -> str | None:
    return shutil.which(name)


def require_tool(name: str) -> str:
    path = find_tool(name)
    if not path:
        error(f"{name} not found in PATH. Please install it.")
        sys.exit(1)
    return path


def clean_dir(path: str) -> None:
    if os.path.exists(path):
        shutil.rmtree(path)
