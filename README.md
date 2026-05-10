# APK Patcher

Automated pipeline to inject a mod menu into an Android APK (.apks bundle).

## Pipeline

```
extract → decompile → inject → build → zipalign → sign
```

## Quick Start

```bash
# 1. Install dependencies
bash setup.sh

# 2. Run (supports both .apk and .apks)
python3 main.py --input game.apk --modmenu app-debug.apk
python3 main.py --input game.apks --modmenu app-debug.apk
```

## Requirements

| Tool | Purpose |
|------|---------|
| Python 3.10+ | Runtime |
| apktool | Decompile / rebuild APKs |
| Java JDK | Required by apktool + signing |
| apksigner | Sign APKs (from Android SDK build-tools) |
| unzip | Extract .apks bundles |

## Installation

### Option 1: Automatic

```bash
bash setup.sh
```

### Option 2: Manual

```bash
# Ubuntu/Debian
sudo apt install -y default-jdk apktool unzip python3-pip
pip3 install pyyaml

# Arch
sudo pacman -S jdk-openjdk apktool unzip python-pip
pip install pyyaml

# macOS
brew install openjdk apktool unzip
pip3 install pyyaml
```

Then install [Android SDK command-line tools](https://developer.android.com/studio#command-line-tools-only) and set `ANDROID_HOME`:

```bash
export ANDROID_HOME=$HOME/Android/Sdk
```

## Usage

### Basic

```bash
python3 main.py --input game.apks --modmenu app-debug.apk
```

### With Options

```bash
python3 main.py \
  --input game.apks \
  --modmenu app-debug.apk \
  --output ./output \
  --output-name MyMod.apk \
  --arch armeabi-v7a \
  --lib libGameHack.so
```

### Arguments

| Flag | Short | Required | Default | Description |
|------|-------|----------|---------|-------------|
| `--input` | `-i` | Yes | — | Target .apk or .apks bundle |
| `--modmenu` | `-m` | Yes | — | Mod menu APK (built from source) |
| `--output` | `-o` | No | `./output` | Output directory |
| `--output-name` | — | No | `ModMenu.apk` | Output filename |
| `--arch` | `-a` | No | `arm64-v8a` | Target arch: `arm64-v8a`, `armeabi-v7a`, `x86`, `x86_64` |
| `--lib` | `-l` | No | `libMyLibName.so` | Mod menu .so filename |
| `--sdk-path` | — | No | auto | Android SDK path |
| `--config` | `-c` | No | `config.yaml` | Custom config file |
| `--keep-work` | — | No | false | Keep work directory after build |

## Project Structure

```
├── config.yaml              # All configurable settings
├── main.py                  # Entry point
├── requirements.txt         # Python dependencies
├── setup.sh                 # Dependency installer
├── patcher/
│   ├── extractor.py         # .apks bundle extraction
│   ├── decompiler.py        # apktool decompile / build
│   ├── injector.py          # smali injection, manifest edits
│   ├── packager.py          # zipalign + apksigner
│   └── utils.py             # helpers, tool discovery
├── templates/
│   └── hooks/
│       └── modmenu.smali    # Smali hook template
└── README.md
```

## How It Works

1. **Extract** — If `.apks`, extracts bundle to get `base.apk` + split APK. If `.apk`, uses it directly
2. **Decompile** — Uses apktool to decompile both base APK and mod menu APK
3. **Inject** — Copies mod menu smali files, .so library, and game native libs
4. **Hook** — Injects `Main.Start()` call into the game's main activity `onCreate`
5. **Manifest** — Adds `SYSTEM_ALERT_WINDOW` permission and `Launcher` service, removes split attributes
6. **Build** — Rebuilds the APK with apktool
7. **Zipalign** — Aligns uncompressed files (.arsc, .so) to 4-byte boundaries
8. **Sign** — Signs with apksigner (v2/v3 scheme, preserves alignment)

## Customization

### Change the Hook

Edit `templates/hooks/modmenu.smali`:

```smali
    invoke-static {p0}, Lcom/android/support/Main;->Start(Landroid/content/Context;)V
```

### Change Mod Menu Package

If your mod menu uses a different package name, update `config.yaml`:

```yaml
hook:
  template: "templates/hooks/modmenu.smali"
  detection_pattern: "com/yourpackage/Main.*->Start"
```

### Add More Permissions

Edit `config.yaml`:

```yaml
manifest:
  add_permissions:
    - "android.permission.SYSTEM_ALERT_WINDOW"
    - "android.permission.INTERNET"
```

## Troubleshooting

### "apksigner not found"

Set `ANDROID_HOME` or pass `--sdk-path`:

```bash
export ANDROID_HOME=$HOME/Android/Sdk
# or
python3 main.py --input game.apks --modmenu menu.apk --sdk-path /path/to/sdk
```

### "apktool not found"

Install it: https://apktool.org/docs/install

### "Unsigned short value out of range"

Too many methods in one dex. The script puts mod menu files in the highest `smali_classes` dir. If the game has many dexes, this should work automatically.

### Game crashes on launch

- Check that the .so architecture matches your device
- Verify the hook was injected into the correct activity
- Check `adb logcat` for crash logs

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
