"""Zipalign and sign APKs. Order: zipalign → apksigner (preserves alignment)."""

import os
import shutil
import struct
import tempfile
import zipfile
import zlib

from patcher.utils import run, info, warn, error, require_tool


def zipalign(unsigned_apk: str, aligned_apk: str, alignment: int = 4,
             uncompressed_ext: set | None = None) -> str:
    """Rebuild APK with proper 4-byte alignment for uncompressed files."""
    if uncompressed_ext is None:
        uncompressed_ext = {'.arsc', '.png', '.so', '.ogg', '.mp3', '.gif',
                            '.wav', '.mid', '.amr', '.ttf', '.otf', '.db', '.dex'}

    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract
        with zipfile.ZipFile(unsigned_apk, 'r') as zf:
            zf.extractall(tmpdir)

        # Build sorted entry list
        entries = []
        with zipfile.ZipFile(unsigned_apk, 'r') as zf:
            for info_entry in sorted(zf.infolist(), key=lambda x: x.filename):
                if info_entry.filename.endswith('/'):
                    continue
                ext = os.path.splitext(info_entry.filename)[1].lower()
                is_uncompressed = ext in uncompressed_ext
                entries.append((info_entry.filename,
                                os.path.join(tmpdir, info_entry.filename),
                                is_uncompressed))

        # Write aligned APK
        with open(aligned_apk, 'wb') as out_f:
            local_headers = []

            for fname, fpath, is_uncompressed in entries:
                with open(fpath, 'rb') as data_f:
                    data = data_f.read()

                filename_bytes = fname.encode('utf-8')

                if is_uncompressed:
                    compress_type = 0
                    crc = zipfile.crc32(data) & 0xFFFFFFFF
                    compress_size = len(data)
                    file_size = len(data)
                else:
                    compress_type = 8
                    compressed = zlib.compress(data, 6)[2:-4]
                    compress_size = len(compressed)
                    file_size = len(data)
                    crc = zipfile.crc32(data) & 0xFFFFFFFF
                    data = compressed

                header_size = 30 + len(filename_bytes)

                # Add padding for alignment
                if is_uncompressed:
                    padding = (alignment - (out_f.tell() + header_size) % alignment) % alignment
                else:
                    padding = 0

                if padding > 0:
                    out_f.write(b'\x00' * padding)

                local_offset = out_f.tell()

                # Local file header
                out_f.write(struct.pack('<I', 0x04034b50))
                out_f.write(struct.pack('<H', 20))
                out_f.write(struct.pack('<H', 0))
                out_f.write(struct.pack('<H', compress_type))
                out_f.write(struct.pack('<H', 0))
                out_f.write(struct.pack('<H', 0))
                out_f.write(struct.pack('<I', crc))
                out_f.write(struct.pack('<I', compress_size))
                out_f.write(struct.pack('<I', file_size))
                out_f.write(struct.pack('<H', len(filename_bytes)))
                out_f.write(struct.pack('<H', 0))
                out_f.write(filename_bytes)
                out_f.write(data)

                local_headers.append((fname, local_offset, compress_type,
                                      crc, compress_size, file_size))

            # Central directory
            central_dir_offset = out_f.tell()
            for fname, local_offset, compress_type, crc, compress_size, file_size in local_headers:
                filename_bytes = fname.encode('utf-8')
                out_f.write(struct.pack('<I', 0x02014b50))
                out_f.write(struct.pack('<H', 20))
                out_f.write(struct.pack('<H', 20))
                out_f.write(struct.pack('<H', 0))
                out_f.write(struct.pack('<H', compress_type))
                out_f.write(struct.pack('<H', 0))
                out_f.write(struct.pack('<H', 0))
                out_f.write(struct.pack('<I', crc))
                out_f.write(struct.pack('<I', compress_size))
                out_f.write(struct.pack('<I', file_size))
                out_f.write(struct.pack('<H', len(filename_bytes)))
                out_f.write(struct.pack('<H', 0))
                out_f.write(struct.pack('<H', 0))
                out_f.write(struct.pack('<H', 0))
                out_f.write(struct.pack('<H', 0))
                out_f.write(struct.pack('<I', 0))
                out_f.write(struct.pack('<I', local_offset))
                out_f.write(filename_bytes)

            central_dir_size = out_f.tell() - central_dir_offset
            num_entries = len(local_headers)

            # End of central directory
            out_f.write(struct.pack('<I', 0x06054b50))
            out_f.write(struct.pack('<H', 0))
            out_f.write(struct.pack('<H', 0))
            out_f.write(struct.pack('<H', num_entries))
            out_f.write(struct.pack('<H', num_entries))
            out_f.write(struct.pack('<I', central_dir_size))
            out_f.write(struct.pack('<I', central_dir_offset))
            out_f.write(struct.pack('<H', 0))

    return aligned_apk


def verify_alignment(apk_path: str, critical_files: list[str],
                     uncompressed_ext: set | None = None) -> bool:
    """Verify that critical files are properly aligned."""
    if uncompressed_ext is None:
        uncompressed_ext = {'.arsc', '.png', '.so', '.ogg', '.mp3', '.gif',
                            '.wav', '.mid', '.amr', '.ttf', '.otf', '.db', '.dex'}

    all_ok = True
    with open(apk_path, 'rb') as f:
        with zipfile.ZipFile(apk_path, 'r') as zf:
            for info_entry in zf.infolist():
                ext = os.path.splitext(info_entry.filename)[1].lower()
                if ext not in uncompressed_ext:
                    continue

                f.seek(info_entry.header_offset + 26)
                fname_len = struct.unpack('<H', f.read(2))[0]
                extra_len = struct.unpack('<H', f.read(2))[0]
                data_offset = info_entry.header_offset + 30 + fname_len + extra_len

                is_aligned = data_offset % 4 == 0
                if info_entry.filename in critical_files:
                    status = "OK" if is_aligned else "FAIL"
                    info(f"{status}: {info_entry.filename} offset={data_offset}")

                if not is_aligned:
                    all_ok = False

    return all_ok


def generate_keystore(keystore_path: str, password: str, alias: str,
                      validity: int, dn: str) -> None:
    """Generate a new signing keystore if it doesn't exist."""
    if os.path.exists(keystore_path):
        return

    run(
        f'keytool -genkeypair -keystore "{keystore_path}" '
        f'-storepass {password} -keypass {password} '
        f'-alias {alias} -keyalg RSA -keysize 2048 -validity {validity} '
        f'-dname "{dn}"',
        "Generate keystore"
    )


def sign_apk(apk_path: str, keystore_path: str, password: str,
             alias: str, apksigner_path: str) -> str:
    """Sign an APK using apksigner (v2/v3 scheme, preserves alignment)."""
    signed_apk = apk_path + ".signed"
    shutil.copy2(apk_path, signed_apk)

    run(
        f'{apksigner_path} sign --ks "{keystore_path}" '
        f'--ks-key-alias {alias} '
        f'--ks-pass pass:{password} '
        f'--key-pass pass:{password} '
        f'"{signed_apk}"',
        "Sign APK with apksigner (v2/v3)"
    )

    run(f'{apksigner_path} verify --print-certs "{signed_apk}"',
        "Verify signature")

    return signed_apk
