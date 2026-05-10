"""Extract .apks bundles and individual APKs."""

import os
import sys

from patcher.utils import run, ensure_dir, info, error


def extract_apks(apks_path: str, work_dir: str) -> tuple[str, str | None]:
    """Extract an .apks bundle and return (base_apk, split_apk)."""
    extracted = os.path.join(work_dir, "extracted")
    ensure_dir(extracted)

    run(f'unzip -o "{apks_path}" -d "{extracted}"', "Extract .apks bundle")

    base = os.path.join(extracted, "base.apk")
    if not os.path.exists(base):
        error("base.apk not found in bundle")
        sys.exit(1)

    split = None
    for f in os.listdir(extracted):
        if f.startswith("split_config.") and f.endswith(".apk"):
            split = os.path.join(extracted, f)
            info(f"Found split APK: {f}")
            break

    return base, split


def extract_split_libs(split_apk: str | None, dest_dir: str) -> list[str]:
    """Extract .so files from a split APK into dest_dir. Returns list of copied filenames."""
    if not split_apk or not os.path.exists(split_apk):
        return []

    ensure_dir(dest_dir)
    copied = []

    import zipfile
    with zipfile.ZipFile(split_apk, 'r') as zf:
        for name in zf.namelist():
            if name.startswith("lib/") and name.endswith(".so"):
                dest_path = os.path.join(dest_dir, os.path.basename(name))
                with zf.open(name) as src, open(dest_path, 'wb') as dst:
                    dst.write(src.read())
                copied.append(os.path.basename(name))

    return copied
