# mattbot_display

Touch-screen display for the Mattbot mobile robot. Shows messages from the robot backend and sends user actions back over HTTP. Speech is synthesized locally with Piper TTS.

## Run locally

```bash
python3 display_app.py
```

Requires `python3-tk` and `alsa-utils` (`aplay`). `install.sh` installs these if missing; or manually:

```bash
sudo apt install python3-tk alsa-utils curl wget
```

### Piper TTS setup

Piper binary and voice live in `./piper/` (not committed to git). One-time setup:

```bash
./scripts/setup_piper.sh
```

Test audio on HDMI speakers:

```bash
echo "Hello, I am a mobile robot." | ./piper/piper \
  --model ./piper/voices/en_US-amy-medium.onnx --output_raw | \
  aplay -r 22050 -f S16_LE -c 1 -t raw -
```

See [piper/README.md](piper/README.md) for layout and overrides.

## Configuration

Environment variables (defaults shown):

| Variable | Default |
|----------|---------|
| `MATTBOT_BACKEND_URL` | `http://127.0.0.1:5000/gemini` |
| `MATTBOT_SOCKET_PORT` | `65432` |
| `MATTBOT_PIPER_BIN` | `{repo}/piper/piper` |
| `MATTBOT_PIPER_MODEL` | `{repo}/piper/voices/en_US-amy-medium.onnx` |
| `MATTBOT_PIPER_SAMPLE_RATE` | `22050` |
| `MATTBOT_PIPER_LENGTH_SCALE` | `1.0` (higher = slower) |
| `MATTBOT_PIPER_SPEAKER` | *(unset — optional multi-speaker id)* |
| `MATTBOT_ALSA_DEVICE` | auto-detect HDMI via `aplay -l` |
| `MATTBOT_HOST_SERVICE_URL` | `http://127.0.0.1:8081` |
| `MATTBOT_LAUNCHER_URL` | `http://127.0.0.1:8080` |
| `MATTBOT_ROS_START_PATH` | `/start?kaist=true` |
| `MATTBOT_ROBOT_POLL_MS` | `2000` |
| `MATTBOT_WRAP_MARGIN_PX` | auto (~2× 'M' width) | Extra right-edge buffer for text wrapping (pixels) |

Set `MATTBOT_ALSA_DEVICE` (e.g. `plughw:2,3`) to override auto-detection. By default the app picks the first HDMI output from `aplay -l`.

## Robot start/stop

The toolbar **Start Robot** / **Stop Robot** button controls ROS via existing host services:

| Service | Port | Role |
|---------|------|------|
| `robot-host-service` (`/opt/robot/host_service.py`) | 8081 | Starts Docker if needed |
| `startup_script.py` (inside container) | 8080 | Starts/stops `roslaunch mattbot_bringup kaist.launch` |

**Prerequisites:** `robot-host-service` running (`curl http://127.0.0.1:8081/status`), Docker image `ghcr.io/satomm1/ml_ros:latest`.

- **Start Docker** — starts the ROS Docker container (when Docker is not running)
- **Start Robot** — starts `kaist.launch` (when Docker is up, ROS is down)
- **Stop Robot** — stops ROS only; Docker keeps running

Change launch file later via `MATTBOT_ROS_START_PATH` (e.g. `/start?social=true`).

### Docker start failed (HTTP 500)

The display calls `GET http://127.0.0.1:8081/docker-start` on **`/opt/robot/host_service.py`** (not part of this repo). A 500 means that service tried to start containers and failed.

**Get the real error** (the response body explains what failed):

```bash
python3 -c "import urllib.request,urllib.error
try: print(urllib.request.urlopen('http://127.0.0.1:8081/docker-start',timeout=120).read().decode())
except urllib.error.HTTPError as e: print(e.read().decode())"

journalctl -u robot-host-service -n 30 --no-pager
```

**Common causes on a new machine:**

| Check | Fix |
|-------|-----|
| `robot-host-service` not running | `curl http://127.0.0.1:8081/status` — install with `sudo bash ~/jetson-host-install.sh` |
| Missing Gemini API key | Create `~/gemini_api/.env` with `API_KEY=your-key` (Gemini container starts first) |
| Missing repos | Clone/copy `~/workspaces/catkin_ws` and `~/gemini_api` |
| Wrong paths in `host_service.py` | Paths must match your home dir (e.g. `/home/ubuntu/...` not `/home/jetson/...`). Re-run `jetson-host-install.sh` as your desktop user |
| Docker images not pulled | `docker pull ghcr.io/satomm1/ml_ros:latest` and `ghcr.io/satomm1/gemini:latest` |
| Missing devices | `/dev/ttyUSB0`, `/dev/video0`, etc. — plug in hardware or edit `DOCKER_RUN_CMD` in `host_service.py` |
| Docker not running | `sudo systemctl start docker` |

After updating `display_app.py`, the display shows the host service error text instead of a generic “HTTP 500”.

## Socket protocol

Send UTF-8 text messages to `localhost:65432`, one message per line (newline-terminated). The display shows and **speaks** each non-status message:

```bash
echo "Hello robot" | nc localhost 65432
python3 send_message.py
```

Status messages (`Listening...`, `Processing...`, `No speech detected.`) are shown but not spoken.

## gemini_api migration (text-only TTS)

The display now handles speech from socket text. Update `~/gemini_api` separately:

1. **Remove gTTS** from `endpoint.py` (and `endpoint_openai.py` if used):

   ```python
   # Delete: from gtts import gTTS
   # Delete: tts = gTTS(...); tts.save("../audio/response.mp3")
   ```

2. **Keep** `send_message(text)` — the display speaks the same string it shows.

3. **Append newline** when sending (recommended):

   ```python
   s.sendall((message + '\n').encode('utf-8'))
   ```

4. **Docker run** — drop the audio volume if it was only for gTTS output:

   ```bash
   # Remove: -v ~/Desktop/audio:/audio
   ```

   Mount only the gemini code and expose port 5000. No MP3 files or `~/Desktop/audio/` needed.

## Systemd install

On a fixed Jetson image, install as a service (no PyInstaller needed):

```bash
chmod +x scripts/install.sh
sudo ./scripts/install.sh
```

This runs `setup_piper.sh`, installs systemd, sudoers, and desktop shortcuts. The service runs **directly from this repo** — edit code here, then restart from the desktop (no sync step).

Override the install path: `INSTALL_DIR=/opt/mattbot/display sudo ./scripts/install.sh`

After code changes, double-click **Start-Mattbot-Display.sh** on the desktop (or run `./scripts/restart_display.sh`).

Override env vars in `~/.config/systemd/user/mattbot-display.service` or `/etc/default/mattbot-display`.

The display runs as a **user systemd service** (not system-wide) so it can access the desktop X session. Status and logs:

```bash
systemctl --user status mattbot-display
journalctl --user -u mattbot-display -n 30
```

If you see `couldn't connect to display ":0"`, log in to the desktop first, then `systemctl --user restart mattbot-display`. Auto-login is recommended for kiosk use.

## Exit and desktop workflow

- **Exit button** — quits the display and returns you to the desktop (service stops; it does not auto-restart on a clean exit).
- **Shut down** — use the normal desktop power menu after pressing Exit.
- **Start display again** — double-click **Start-Mattbot-Display.sh** on the desktop (or use **Mattbot Display** in the application menu). Restarts the service using the latest code in the repo (no separate sync step).

The desktop shortcut starts the display via `systemctl --user` (no sudo required).

### Desktop shortcut opens a text editor?

On **LXDE / PCManFM** (common on Jetson), `gio metadata::trusted` is not supported — that message during install is normal. The install script enables PCManFM auto-launch instead (`quick_exec` + `exec_apps`).

1. **Double-click `Start-Mattbot-Display.sh`** (not the `.desktop` file) — or launch **Mattbot Display** from the application menu.
2. If prompted, choose **Execute** / **Run** (once).
3. If it still opens in an editor, log out and back in, then re-run:
   ```bash
   sudo ./scripts/setup_desktop_shortcut.sh
   ```
4. Manual PCManFM setting: **Edit → Preferences → General → “Don’t ask options on launch executable file”**.

## GPU tips

- `TK_ENABLE_PLATFORM_GL=0` is set in the app to avoid OpenGL in Tk.
- For lowest GPU use, run with a minimal X session (no compositor) and monitor with `tegrastats` or `jtop`.
