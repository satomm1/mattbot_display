#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIPER_DIR="$SCRIPT_DIR/piper"
VOICE_DIR="$PIPER_DIR/voices"
PIPER_BIN="$PIPER_DIR/piper"
VOICE_NAME="en_US-amy-medium"
VOICE_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium"

arch="$(uname -m)"
case "$arch" in
    aarch64|arm64) PIPER_TAR="piper_linux_aarch64.tar.gz" ;;
    x86_64|amd64)  PIPER_TAR="piper_linux_x86_64.tar.gz" ;;
    *)
        echo "Unsupported architecture: $arch" >&2
        exit 1
        ;;
esac
PIPER_RELEASE="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/$PIPER_TAR"

mkdir -p "$VOICE_DIR"

download() {
    local url="$1" dest="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$url" -o "$dest"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$dest" "$url"
    else
        echo "Need curl or wget to download Piper assets" >&2
        exit 1
    fi
}

if [[ ! -x "$PIPER_BIN" ]]; then
    echo "Downloading Piper ($PIPER_TAR)..."
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    download "$PIPER_RELEASE" "$tmp/piper.tar.gz"
    tar -xzf "$tmp/piper.tar.gz" -C "$SCRIPT_DIR"
    chmod +x "$PIPER_BIN" "$PIPER_DIR/piper_phonemize" "$PIPER_DIR/espeak-ng" 2>/dev/null || true
    echo "Installed Piper into $PIPER_DIR"
else
    echo "Piper already present: $PIPER_BIN"
fi

for ext in onnx onnx.json; do
    dest="$VOICE_DIR/${VOICE_NAME}.${ext}"
    if [[ ! -f "$dest" ]]; then
        echo "Downloading ${VOICE_NAME}.${ext}..."
        download "$VOICE_BASE/${VOICE_NAME}.${ext}" "$dest"
    else
        echo "Voice file already present: $dest"
    fi
done

echo "Piper setup complete."
echo "Test: echo 'Hello' | $PIPER_BIN --model $VOICE_DIR/${VOICE_NAME}.onnx --output_raw | aplay -r 22050 -f S16_LE -c 1 -t raw -"
