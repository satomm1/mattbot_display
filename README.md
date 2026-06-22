# mattbot_display

Touch-screen display for the Mattbot mobile robot. Shows messages from the robot backend and sends user actions back over HTTP.

## Run locally

```bash
python3 display_app.py
```

Requires `python3-tk`. Audio uses system `mpg123` (MP3) or `aplay` (WAV):

```bash
sudo apt install mpg123
```

Place audio files in `~/Desktop/audio/` (or set `MATTBOT_AUDIO_DIR`):

- `default.mp3` — played on the welcome message
- `response.mp3` — played on robot responses

## Configuration

Environment variables (defaults shown):

| Variable | Default |
|----------|---------|
| `MATTBOT_BACKEND_URL` | `http://127.0.0.1:5000/gemini` |
| `MATTBOT_SOCKET_PORT` | `65432` |
| `MATTBOT_AUDIO_DIR` | `~/Desktop/audio` |
| `MATTBOT_ALSA_DEVICE` | auto-detect HDMI via `aplay -l` |

Set `MATTBOT_ALSA_DEVICE` (e.g. `plughw:2,3`) to override auto-detection. By default the app picks the first HDMI output from `aplay -l`.

## Socket protocol

Send UTF-8 text messages to `localhost:65432`, one message per line (newline-terminated):

```bash
echo "Hello robot" | nc localhost 65432
python3 send_message.py
```

## Systemd install

On a fixed Jetson image, install as a service (no PyInstaller needed):

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

This copies the app to `/opt/mattbot/display`, creates a venv, and enables `mattbot-display.service`.

Override env vars in `/etc/systemd/system/mattbot-display.service` or add an `EnvironmentFile=/etc/default/mattbot-display`.

## GPU tips

- `TK_ENABLE_PLATFORM_GL=0` is set in the app to avoid OpenGL in Tk.
- For lowest GPU use, run with a minimal X session (no compositor) and monitor with `tegrastats` or `jtop`.
