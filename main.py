#!/usr/bin/env python3
"""
Android APK Patcher

Injects a mod menu into an Android APK (.apks bundle).

Pipeline: extract → decompile → inject → build → zipalign → sign

Usage:
    python3 main.py --input game.apks --modmenu menu.apk
    python3 main.py --input game.apks --modmenu menu.apk --output ./output
    python3 main.py --input game.apks --modmenu menu.apk --arch armeabi-v7a
"""

import argparse
import os
import sys
import shutil

import yaml

from patcher.utils import (
    banner, info, error, warn,
    find_apksigner, require_tool, clean_dir, ensure_dir,
)
from patcher.extractor import extract_apks, extract_split_libs
from patcher.decompiler import decompile, build
from patcher.injector import (
    copy_modmenu_smali,
    copy_native_lib,
    copy_game_libs,
    inject_smali_hook,
    modify_manifest,
)
from patcher.packager import zipalign, verify_alignment, generate_keystore, sign_apk


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inject a mod menu into an Android APK (.apks bundle)."
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to target .apk or .apks bundle"
    )
    parser.add_argument(
        "--modmenu", "-m", required=True,
        help="Path to mod menu APK (app-debug.apk)"
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output directory (default: ./output)"
    )
    parser.add_argument(
        "--output-name", default=None,
        help="Output APK filename (default: ModMenu.apk)"
    )
    parser.add_argument(
        "--arch", "-a", default=None,
        choices=["arm64-v8a", "armeabi-v7a", "x86", "x86_64"],
        help="Target architecture (default: arm64-v8a)"
    )
    parser.add_argument(
        "--lib", "-l", default=None,
        help="Mod menu .so filename (default: libMyLibName.so)"
    )
    parser.add_argument(
        "--config", "-c", default=None,
        help="Path to config.yaml (default: config.yaml in script dir)"
    )
    parser.add_argument(
        "--sdk-path", default=None,
        help="Android SDK path (auto-detected if not set)"
    )
    parser.add_argument(
        "--keep-work", action="store_true",
        help="Keep work directory after completion"
    )
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    if not os.path.exists(config_path):
        error(f"Config not found: {config_path}")
        sys.exit(1)
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def resolve_paths(args: argparse.Namespace, cfg: dict, script_dir: str) -> dict:
    """Merge CLI args with config, resolving all paths."""
    paths = {}

    # Input files
    paths["apks_path"] = args.input or cfg.get("apks_path", "")
    paths["modmenu_apk"] = args.modmenu or cfg.get("modmenu_apk", "")

    # Output
    paths["output_dir"] = os.path.abspath(
        args.output or cfg.get("output_dir", "./output")
    )
    paths["output_filename"] = args.output_name or cfg.get("output_filename", "ModMenu.apk")
    paths["final_apk"] = os.path.join(paths["output_dir"], paths["output_filename"])
    paths["work_dir"] = os.path.join(paths["output_dir"], "work")

    # Architecture
    paths["native_arch"] = args.arch or cfg.get("native_arch", "arm64-v8a")
    paths["native_lib"] = args.lib or cfg.get("native_lib", "libMyLibName.so")

    # Keystore
    keystore_cfg = cfg.get("keystore", {})
    paths["keystore_path"] = os.path.join(
        paths["output_dir"],
        keystore_cfg.get("path", "modmenu.keystore")
    )
    paths["keystore"] = keystore_cfg

    # Hook template
    hook_cfg = cfg.get("hook", {})
    template_rel = hook_cfg.get("template", "templates/hooks/modmenu.smali")
    paths["hook_template"] = os.path.join(script_dir, template_rel)
    paths["hook_detection"] = hook_cfg.get("detection_pattern", "com/android/support/Main.*->Start")

    # Manifest
    paths["manifest"] = cfg.get("manifest", {})

    # Zipalign
    paths["zipalign"] = cfg.get("zipalign", {
        "alignment": 4,
        "uncompressed_extensions": [".arsc", ".png", ".so", ".ogg", ".mp3", ".gif", ".wav", ".mid", ".amr", ".ttf", ".otf", ".db", ".dex"]
    })

    # Verify alignment
    paths["verify_alignment"] = cfg.get("verify_alignment", ["resources.arsc"])

    # Android SDK
    sdk_cfg = cfg.get("android_sdk", {})
    sdk_base = args.sdk_path or sdk_cfg.get("base_path", "")
    sdk_versions = sdk_cfg.get("build_tools_versions", [
        "37.0.0", "36.1.0", "35.0.0", "34.0.0", "33.0.0", "32.0.0", "31.0.0", "30.0.0"
    ])
    paths["apksigner"] = find_apksigner(sdk_base, sdk_versions)
    paths["keep_work"] = args.keep_work

    return paths


def check_tools(paths: dict) -> None:
    """Verify all required tools are available."""
    require_tool("apktool")
    require_tool("unzip")
    require_tool("keytool")

    if not paths["apksigner"]:
        error("apksigner not found.")
        error("Install Android SDK build-tools or set --sdk-path / ANDROID_HOME")
        sys.exit(1)
    info(f"Using apksigner: {paths['apksigner']}")


def validate_inputs(paths: dict) -> None:
    """Check that input files exist."""
    if not os.path.exists(paths["apks_path"]):
        error(f"Input file not found: {paths['apks_path']}")
        sys.exit(1)
    if not os.path.exists(paths["modmenu_apk"]):
        error(f"Mod menu APK not found: {paths['modmenu_apk']}")
        sys.exit(1)
    if not os.path.exists(paths["hook_template"]):
        error(f"Hook template not found: {paths['hook_template']}")
        sys.exit(1)


def main() -> None:
    print("\nDISCLAIMER: This tool is for educational purposes only.")
    print("Use responsibly and only on apps you own or have permission to modify.")

    banner("Android APK Patcher")

    args = parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Load config
    config_path = args.config or os.path.join(script_dir, "config.yaml")
    cfg = load_config(config_path)

    # Resolve all paths
    paths = resolve_paths(args, cfg, script_dir)

    # Validate
    check_tools(paths)
    validate_inputs(paths)

    # Show config summary
    info(f"Input: {paths['apks_path']}")
    info(f"Mod menu: {paths['modmenu_apk']}")
    info(f"Output: {paths['final_apk']}")
    info(f"Arch: {paths['native_arch']}")
    info(f"Lib: {paths['native_lib']}")

    # Clean work directory
    clean_dir(paths["work_dir"])
    ensure_dir(paths["output_dir"])
    ensure_dir(paths["work_dir"])

    # Load hook template
    with open(paths["hook_template"], 'r') as f:
        hook_code = f.read()

    # ─── Pipeline ────────────────────────────────────────────────────────

    # Step 1: Extract
    base_apk, split_apk = extract_apks(paths["apks_path"], paths["work_dir"])

    # Step 2: Decompile
    decompiled_base = decompile(base_apk, os.path.join(paths["work_dir"], "decompiled_base"))
    decompiled_modmenu = decompile(paths["modmenu_apk"], os.path.join(paths["work_dir"], "decompiled_modmenu"))

    # Step 3: Copy mod menu files
    copy_modmenu_smali(decompiled_base, decompiled_modmenu)
    copy_native_lib(decompiled_base, decompiled_modmenu, paths["native_lib"], paths["native_arch"])

    # Step 4: Copy game native libs from split APK
    lib_dest = os.path.join(decompiled_base, "lib", paths["native_arch"])
    copy_game_libs(decompiled_base, split_apk, paths["native_arch"])

    # Step 5: Inject smali hook
    inject_smali_hook(decompiled_base, hook_code, paths["hook_detection"])

    # Step 6: Modify manifest
    modify_manifest(decompiled_base, paths["manifest"])

    # Step 7: Build
    unsigned_apk = os.path.join(paths["output_dir"], "unsigned.apk")
    build(decompiled_base, unsigned_apk)

    # Step 8: Zipalign
    aligned_apk = os.path.join(paths["output_dir"], "aligned.apk")
    zipalign(
        unsigned_apk, aligned_apk,
        alignment=paths["zipalign"]["alignment"],
        uncompressed_ext=set(paths["zipalign"]["uncompressed_extensions"])
    )

    # Verify alignment
    info("Verifying alignment...")
    if verify_alignment(
        aligned_apk,
        paths["verify_alignment"],
        uncompressed_ext=set(paths["zipalign"]["uncompressed_extensions"])
    ):
        info("All critical files 4-byte aligned ✓")
    else:
        error("Some files are misaligned!")
        sys.exit(1)

    # Step 9: Sign
    ks = paths["keystore"]
    generate_keystore(
        paths["keystore_path"],
        password=ks.get("password", "modmenu123"),
        alias=ks.get("alias", "modmenu"),
        validity=ks.get("validity_days", 10000),
        dn=ks.get("dn", "CN=ModMenu, OU=ModMenu, O=ModMenu, L=Unknown, S=Unknown, C=US")
    )

    signed_apk = sign_apk(
        aligned_apk, paths["keystore_path"],
        password=ks.get("password", "modmenu123"),
        alias=ks.get("alias", "modmenu"),
        apksigner_path=paths["apksigner"]
    )

    # Final output
    shutil.copy2(signed_apk, paths["final_apk"])

    # Cleanup intermediates
    for f in [unsigned_apk, aligned_apk, signed_apk]:
        if os.path.exists(f):
            os.remove(f)

    # Cleanup work dir
    if not paths["keep_work"]:
        clean_dir(paths["work_dir"])

    # Done
    size_mb = os.path.getsize(paths["final_apk"]) / (1024 * 1024)
    banner(f"DONE — {size_mb:.1f} MB")
    info(f"Output: {paths['final_apk']}")
    info(f'Install: adb install "{paths["final_apk"]}"')


if __name__ == "__main__":
    main()
