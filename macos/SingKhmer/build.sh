#!/bin/bash
# Build the Sing Khmer input method for macOS.
#
#   ./build.sh            export the dictionary, compile, assemble build/SingKhmer.app
#   ./build.sh install    the above, then copy it into ~/Library/Input Methods
#   ./build.sh test       check the Swift port against the Python engine
#   ./build.sh uninstall  remove it from ~/Library/Input Methods
#
# Full walkthrough: docs/MAC_KEYBOARD.md

set -euo pipefail
cd "$(dirname "$0")"

REPO_ROOT="$(cd ../.. && pwd)"
APP_NAME="SingKhmer"                 # also the executable name in Info.plist
APP="build/$APP_NAME.app"
INSTALL_DIR="$HOME/Library/Input Methods"
PYTHON="${PYTHON:-python3}"

die() { echo "error: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }

require_tools() {
    [[ "$(uname)" == "Darwin" ]] || die "the input method can only be built on a Mac"
    command -v swift >/dev/null || die "Swift not found. Install it with: xcode-select --install"
    command -v "$PYTHON" >/dev/null || die "$PYTHON not found. Install it with: xcode-select --install"
}

build_app() {
    step "Exporting the dictionary from data/vocabulary.csv"
    "$PYTHON" "$REPO_ROOT/scripts/export_mac_data.py" --data-only

    step "Compiling (the first build takes a minute or two)"
    swift build -c release --product SingKhmerIME
    local bin
    bin="$(swift build -c release --show-bin-path)/SingKhmerIME"
    [[ -x "$bin" ]] || die "expected the compiled program at $bin"

    step "Assembling $APP"
    rm -rf "$APP"
    mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
    cp "$bin" "$APP/Contents/MacOS/$APP_NAME"
    cp Resources/Info.plist "$APP/Contents/Info.plist"
    cp Resources/engine_data.json Resources/icon.tiff "$APP/Contents/Resources/"
    # An ad-hoc signature: enough to run on this Mac, no Apple Developer account needed.
    codesign --force --sign - "$APP"
    echo "built $(pwd)/$APP"
}

install_app() {
    step "Installing into $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    local first_install=true
    [[ -d "$INSTALL_DIR/$APP_NAME.app" ]] && first_install=false
    pkill -x "$APP_NAME" 2>/dev/null || true      # stop the old copy; macOS restarts it on demand
    rm -rf "$INSTALL_DIR/$APP_NAME.app"
    cp -R "$APP" "$INSTALL_DIR/"
    echo "installed $INSTALL_DIR/$APP_NAME.app"
    echo
    if $first_install; then
        cat <<'NEXT'
First install. To finish:
  1. Log out of your Mac and log back in (so macOS notices the new input method).
  2. System Settings > Keyboard > Input Sources > Edit... > "+"
     choose Khmer in the list, select "Sing Khmer", click Add.
  3. Switch to it from the menu bar (or Ctrl+Space / the Globe key) and type: nh srolanh bong
NEXT
    else
        echo "Updated. Switch to another input source and back to Sing Khmer to load the new version."
    fi
}

case "${1:-build}" in
    build)
        require_tools
        build_app
        ;;
    install)
        require_tools
        build_app
        install_app
        ;;
    test)
        command -v swift >/dev/null || die "Swift not found. Install it with: xcode-select --install"
        step "Exporting the dictionary and the Python engine's answers (about 20 seconds)"
        "$PYTHON" "$REPO_ROOT/scripts/export_mac_data.py"
        step "Running the tests"
        swift test
        ;;
    uninstall)
        pkill -x "$APP_NAME" 2>/dev/null || true
        rm -rf "$INSTALL_DIR/$APP_NAME.app"
        echo "Removed. If Sing Khmer is still listed in System Settings > Keyboard > Input Sources, remove it there too."
        ;;
    *)
        die "unknown command '$1' (use: build, install, test, uninstall)"
        ;;
esac
