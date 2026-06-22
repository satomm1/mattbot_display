# Piper TTS (repo-local)

The display app speaks socket messages using [Piper](https://github.com/rhasspy/piper) and `aplay`. Binary and voice files live here — not in git (see `.gitignore`).

## Setup

From the repo root:

```bash
./scripts/setup_piper.sh
```

This downloads:

- `piper/piper` — Piper CLI for your CPU arch
- `piper/voices/en_US-amy-medium.onnx` (+ `.onnx.json`)

## Manual test

```bash
echo "Hello, I am a mobile robot." | ./piper/piper \
  --model ./piper/voices/en_US-amy-medium.onnx --output_raw | \
  aplay -D plughw:2,3 -r 22050 -f S16_LE -c 1 -t raw -
```

Adjust `-D` for your HDMI ALSA device (`aplay -l`).

## Overrides

Optional env vars (defaults are repo-relative paths):

| Variable | Default |
|----------|---------|
| `MATTBOT_PIPER_BIN` | `./piper/piper` |
| `MATTBOT_PIPER_MODEL` | `./piper/voices/en_US-amy-medium.onnx` |
| `MATTBOT_PIPER_SAMPLE_RATE` | `22050` |
| `MATTBOT_PIPER_LENGTH_SCALE` | `1.0` (higher = slower) |
| `MATTBOT_PIPER_SPEAKER` | *(unset)* |
| `MATTBOT_ALSA_DEVICE` | auto-detect HDMI |
