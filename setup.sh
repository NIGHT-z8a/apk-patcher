#!/usr/bin/env bash
# APK Patcher — Dependency Setup Script
# Installs required tools and Python packages.
# Supports: Ubuntu/Debian, Arch, macOS (Homebrew)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[-]${NC} $1"; }

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    elif command -v brew &>/dev/null; then
        echo "macos"
    else
        echo "unknown"
    fi
}

check_tool() {
    if command -v "$1" &>/dev/null; then
        info "$1: found ($($1 --version 2>/dev/null | head -1 || echo 'installed'))"
        return 0
    else
        warn "$1: not found"
        return 1
    fi
}

install_apktool() {
    if check_tool apktool; then return; fi

    info "Installing apktool..."
    local OS=$(detect_os)

    case "$OS" in
        ubuntu|debian|linuxmint)
            sudo apt-get install -y apktool 2>/dev/null || {
                info "apktool not in apt, installing manually..."
                sudo curl -Lo /usr/local/bin/apktool https://raw.githubusercontent.com/iBotPeaches/Apktool/master/scripts/linux/apktool
                sudo curl -Lo /usr/local/bin/apktool.jar https://github.com/iBotPeaches/Apktool/releases/latest/download/apktool_2.9.3.jar
                sudo chmod +x /usr/local/bin/apktool
            }
            ;;
        arch|manjaro)
            sudo pacman -S --noconfirm apktool
            ;;
        macos)
            brew install apktool
            ;;
        *)
            warn "Unknown OS. Install apktool manually: https://apktool.org/docs/install"
            ;;
    esac
}

install_java() {
    if check_tool java; then return; fi

    info "Installing Java JDK..."
    local OS=$(detect_os)

    case "$OS" in
        ubuntu|debian|linuxmint)
            sudo apt-get install -y default-jdk
            ;;
        arch|manjaro)
            sudo pacman -S --noconfirm jdk-openjdk
            ;;
        macos)
            brew install openjdk
            ;;
        *)
            warn "Install Java JDK manually: https://adoptium.net"
            ;;
    esac
}

install_python_deps() {
    info "Installing Python dependencies..."
    if command -v pip3 &>/dev/null; then
        pip3 install --user -r requirements.txt 2>/dev/null || \
        pip3 install --user --break-system-packages -r requirements.txt 2>/dev/null || \
        python3 -m pip install --user -r requirements.txt
    else
        error "pip3 not found. Install python3-pip first."
        exit 1
    fi
}

check_android_sdk() {
    if [ -n "$ANDROID_HOME" ] && [ -d "$ANDROID_HOME" ]; then
        info "ANDROID_HOME: $ANDROID_HOME"
        return 0
    fi
    if [ -n "$ANDROID_SDK_ROOT" ] && [ -d "$ANDROID_SDK_ROOT" ]; then
        info "ANDROID_SDK_ROOT: $ANDROID_SDK_ROOT"
        return 0
    fi

    local common_paths=(
        "$HOME/Android/Sdk"
        "$HOME/Library/Android/sdk"
        "/opt/android-sdk"
    )
    for p in "${common_paths[@]}"; do
        if [ -d "$p" ]; then
            info "Found Android SDK at: $p"
            export ANDROID_HOME="$p"
            return 0
        fi
    done

    echo ""
    warn "Android SDK not found."
    echo "  Download from: https://developer.android.com/studio#command-line-tools-only"
    echo "  Or install Android Studio."
    echo ""
    echo "  After installing, set ANDROID_HOME:"
    echo "    export ANDROID_HOME=\$HOME/Android/Sdk"
    echo "    export PATH=\$PATH:\$ANDROID_HOME/build-tools/<version>"
    echo ""
}

main() {
    echo "============================================"
    echo "  APK Patcher — Setup"
    echo "============================================"
    echo ""

    install_java
    install_apktool
    install_python_deps
    check_android_sdk

    echo ""
    echo "============================================"
    echo "  Setup complete!"
    echo "============================================"
    echo ""
    echo "Usage:"
    echo "  python3 main.py --input game.apks --modmenu menu.apk"
    echo ""
}

main
