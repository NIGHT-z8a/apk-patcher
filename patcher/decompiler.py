"""Decompile and build APKs using apktool."""

import os

from patcher.utils import run, require_tool, info


def decompile(apk_path: str, output_dir: str) -> str:
    """Decompile an APK with apktool. Returns the output directory."""
    require_tool("apktool")
    run(f'apktool d "{apk_path}" -o "{output_dir}" -f',
        f"Decompile {os.path.basename(apk_path)}")
    return output_dir


def build(decompiled_dir: str, output_apk: str) -> str:
    """Build a decompiled directory back into an APK. Returns the APK path."""
    run(f'apktool b "{decompiled_dir}" -o "{output_apk}"', "Build APK with apktool")
    return output_apk
