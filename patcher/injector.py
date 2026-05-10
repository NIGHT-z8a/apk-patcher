"""Inject mod menu files, smali hooks, and manifest modifications."""

import os
import re
import shutil

from patcher.utils import ensure_dir, info, warn, error


def copy_modmenu_smali(decompiled_base: str, decompiled_modmenu: str) -> str:
    """Copy mod menu smali files into the target APK's highest smali_classes dir."""
    smali_dirs = [d for d in os.listdir(decompiled_base) if d.startswith("smali_classes")]
    if smali_dirs:
        target_smali = sorted(smali_dirs)[-1]
    else:
        target_smali = "smali"
        ensure_dir(os.path.join(decompiled_base, target_smali))

    # Copy R files (smali/com/)
    src_r = os.path.join(decompiled_modmenu, "smali", "com")
    if os.path.exists(src_r):
        dest = os.path.join(decompiled_base, target_smali, "com")
        shutil.copytree(src_r, dest, dirs_exist_ok=True)
        info(f"Copied R files → {target_smali}/com/")

    # Copy main mod menu classes (smali_classes2/com/android/)
    src_main = os.path.join(decompiled_modmenu, "smali_classes2", "com", "android")
    if os.path.exists(src_main):
        dest_com = os.path.join(decompiled_base, target_smali, "com")
        os.makedirs(dest_com, exist_ok=True)
        shutil.copytree(src_main, os.path.join(dest_com, "android"), dirs_exist_ok=True)
        info(f"Copied mod menu classes → {target_smali}/com/android/")

    return target_smali


def copy_native_lib(decompiled_base: str, decompiled_modmenu: str, lib_name: str, arch: str) -> None:
    """Copy the mod menu .so library into the target APK."""
    lib_src = os.path.join(decompiled_modmenu, "lib", arch, lib_name)
    lib_dest_dir = os.path.join(decompiled_base, "lib", arch)
    ensure_dir(lib_dest_dir)

    if os.path.exists(lib_src):
        shutil.copy2(lib_src, lib_dest_dir)
        info(f"Copied {lib_name} → lib/{arch}/")
    else:
        warn(f"{lib_name} not found at {lib_src}")


def copy_game_libs(decompiled_base: str, split_apk: str | None, arch: str) -> list[str]:
    """Copy game native libs from split APK into the target."""
    if not split_apk or not os.path.exists(split_apk):
        warn("No split APK found, skipping game libs")
        return []

    lib_dest = os.path.join(decompiled_base, "lib", arch)
    ensure_dir(lib_dest)

    import zipfile
    copied = []
    prefix = f"lib/{arch}/"
    with zipfile.ZipFile(split_apk, 'r') as zf:
        for name in zf.namelist():
            if name.startswith(prefix) and name.endswith(".so"):
                dest_path = os.path.join(lib_dest, os.path.basename(name))
                with zf.open(name) as src, open(dest_path, 'wb') as dst:
                    dst.write(src.read())
                info(f"Copied {os.path.basename(name)}")
                copied.append(os.path.basename(name))

    return copied


def inject_smali_hook(decompiled_base: str, hook_code: str, detection_pattern: str) -> str:
    """Inject a smali hook into the main activity's onCreate method."""
    manifest = os.path.join(decompiled_base, "AndroidManifest.xml")
    with open(manifest, 'r') as f:
        manifest_content = f.read()

    # Find LAUNCHER activity
    match = re.search(
        r'<activity[^>]*android:name="([^"]+)"[^>]*>.*?'
        r'<category android:name="android.intent.category.LAUNCHER"',
        manifest_content, re.DOTALL
    )
    if not match:
        error("Could not find LAUNCHER activity in AndroidManifest.xml")
        raise SystemExit(1)

    activity_name = match.group(1)
    info(f"Main activity: {activity_name}")

    # Convert to smali path
    smali_path = activity_name.replace(".", "/") + ".smali"

    # Search across all smali dirs
    smali_file = None
    for d in sorted(os.listdir(decompiled_base)):
        if d.startswith("smali"):
            candidate = os.path.join(decompiled_base, d, smali_path)
            if os.path.exists(candidate):
                smali_file = candidate
                break

    if not smali_file:
        error(f"Could not find smali file for {activity_name}")
        raise SystemExit(1)

    info(f"Smali file: {smali_file}")

    with open(smali_file, 'r') as f:
        smali_content = f.read()

    # Check if already injected
    if re.search(detection_pattern, smali_content):
        info("Hook already present, skipping")
        return smali_file

    # Inject after super.onCreate
    pattern = r'(invoke-super \{p0, p1\}, L[^;]+;->onCreate\(Landroid/os/Bundle;\)V\s*\n)'
    replacement = r'\1\n' + hook_code.strip() + '\n'

    new_content = re.sub(pattern, replacement, smali_content, count=1)
    with open(smali_file, 'w') as f:
        f.write(new_content)

    info("Hook injected successfully")
    return smali_file


def modify_manifest(decompiled_base: str, config: dict) -> None:
    """Apply manifest modifications from config."""
    manifest = os.path.join(decompiled_base, "AndroidManifest.xml")
    with open(manifest, 'r') as f:
        content = f.read()

    # Remove specified attributes
    for attr in config.get("remove_attributes", []):
        pattern = rf'\s+{attr}="[^"]*"'
        new_content = re.sub(pattern, '', content)
        if new_content != content:
            info(f"Removed {attr}")
            content = new_content

    # Add permissions
    for perm in config.get("add_permissions", []):
        if perm not in content:
            content = content.replace(
                '<uses-permission android:name="android.permission.INTERNET"/>',
                f'<uses-permission android:name="{perm}"/>\n    '
                '<uses-permission android:name="android.permission.INTERNET"/>'
            )
            info(f"Added permission: {perm}")

    # Add service
    service = config.get("add_service")
    if service:
        service_name = service["name"]
        if service_name not in content:
            enabled = str(service.get("enabled", True)).lower()
            exported = str(service.get("exported", False)).lower()
            stop_with_task = str(service.get("stopWithTask", True)).lower()
            service_tag = (
                f'        <service android:name="{service_name}" '
                f'android:enabled="{enabled}" android:exported="{exported}" '
                f'android:stopWithTask="{stop_with_task}"/>\n    </application>'
            )
            content = content.replace('</application>', service_tag)
            info(f"Added service: {service_name}")

    with open(manifest, 'w') as f:
        f.write(content)
