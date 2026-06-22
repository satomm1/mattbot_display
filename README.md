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
| `MATTBOT_HOST_SERVICE_URL` | `http://127.0.0.1:8081` |
| `MATTBOT_LAUNCHER_URL` | `http://127.0.0.1:8080` |
| `MATTBOT_ROS_START_PATH` | `/start?kaist=true` |
| `MATTBOT_ROBOT_POLL_MS` | `2000` |

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

This installs systemd, sudoers, and desktop shortcuts. The service runs **directly from this repo** — edit code here, then restart from the desktop (no sync step).

Override the install path: `INSTALL_DIR=/opt/mattbot/display sudo ./scripts/install.sh`

After code changes, double-click **Start-Mattbot-Display.sh** on the desktop (or run `./scripts/restart_display.sh`).

Override env vars in `/etc/systemd/system/mattbot-display.service` or add an `EnvironmentFile=/etc/default/mattbot-display`.

## Exit and desktop workflow

- **Exit button** — quits the display and returns you to the desktop (service stops; it does not auto-restart on a clean exit).
- **Shut down** — use the normal desktop power menu after pressing Exit.
- **Start display again** — double-click **Start-Mattbot-Display.sh** on the desktop. Restarts the service using the latest code in the repo (no separate sync step).

The desktop shortcut uses passwordless sudo for `systemctl start/restart mattbot-display` only (see `deploy/mattbot-display-sudoers`).

## GPU tips

- `TK_ENABLE_PLATFORM_GL=0` is set in the app to avoid OpenGL in Tk.
- For lowest GPU use, run with a minimal X session (no compositor) and monitor with `tegrastats` or `jtop`.
