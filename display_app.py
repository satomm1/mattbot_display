#!/usr/bin/python3
import os
os.environ['TK_ENABLE_PLATFORM_GL'] = '0'

import json
import logging
import re
import socket
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

REPO_DIR = Path(__file__).resolve().parent
BACKEND_URL = os.environ.get('MATTBOT_BACKEND_URL', 'http://127.0.0.1:5000/gemini')
SOCKET_PORT = int(os.environ.get('MATTBOT_SOCKET_PORT', '65432'))
PIPER_BIN = Path(os.environ.get('MATTBOT_PIPER_BIN', REPO_DIR / 'piper' / 'piper'))
PIPER_MODEL = Path(os.environ.get(
    'MATTBOT_PIPER_MODEL', REPO_DIR / 'piper' / 'voices' / 'en_US-amy-medium.onnx'))
PIPER_SAMPLE_RATE = int(os.environ.get('MATTBOT_PIPER_SAMPLE_RATE', '22050'))
PIPER_LENGTH_SCALE = float(os.environ.get('MATTBOT_PIPER_LENGTH_SCALE', '1.0'))
PIPER_SPEAKER = os.environ.get('MATTBOT_PIPER_SPEAKER', '')
HOST_SERVICE_URL = os.environ.get('MATTBOT_HOST_SERVICE_URL', 'http://127.0.0.1:8081')
LAUNCHER_URL = os.environ.get('MATTBOT_LAUNCHER_URL', 'http://127.0.0.1:8080')
ROS_START_PATH = os.environ.get('MATTBOT_ROS_START_PATH', '/start?kaist=true')
ROBOT_POLL_MS = int(os.environ.get('MATTBOT_ROBOT_POLL_MS', '2000'))


def _detect_hdmi_alsa_device():
    """Pick first HDMI output from aplay -l, skipping USB camera mics."""
    try:
        out = subprocess.check_output(['aplay', '-l'], stderr=subprocess.DEVNULL, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return ''
    devices = []
    for line in out.splitlines():
        # Compact: "card 2: HDA [...], device 3: HDMI 0 [HDMI 0]"
        if m := re.search(r'card (\d+):.+device (\d+): (.+)', line):
            card, dev, name = int(m.group(1)), int(m.group(2)), m.group(3)
            if 'HDMI' in name:
                hdmi_n = int(hm.group(1)) if (hm := re.search(r'HDMI (\d+)', name)) else dev
                devices.append((hdmi_n, card, dev))
    if not devices:
        return ''
    devices.sort()
    c, d = devices[0][1], devices[0][2]
    return f'plughw:{c},{d}'


def _resolve_alsa_device():
    if os.environ.get('MATTBOT_ALSA_DEVICE'):
        return os.environ['MATTBOT_ALSA_DEVICE']
    detected = _detect_hdmi_alsa_device()
    if detected:
        log.info('Auto-detected ALSA device: %s', detected)
        return detected
    log.warning('No HDMI ALSA device found; using system default')
    return ''


ALSA_DEVICE = _resolve_alsa_device()
MAX_TEXT_CHARS = 8000
MAX_SPEAK_CHARS = 500

if not PIPER_BIN.is_file():
    log.warning('Piper binary not found at %s — run scripts/setup_piper.sh', PIPER_BIN)
if not PIPER_MODEL.is_file():
    log.warning('Piper model not found at %s — run scripts/setup_piper.sh', PIPER_MODEL)

DEFAULT_MESSAGE = 'Hello! I am a mobile robot.\nSay "Hey Robot" to talk to me.'
STATUS_MESSAGES = frozenset(('Listening...', 'No speech detected.', 'Processing...'))
SHOW_PICTURE_BUTTON = os.environ.get('MATTBOT_SHOW_PICTURE', '0').lower() in ('1', 'true', 'yes')


def _touch_button(parent, text, action, bind=True, **kwargs):
    bg = kwargs.get('bg', 'white')
    fg = kwargs.get('fg', 'black')
    font = kwargs.get('font', ('Helvetica', 16))
    frame = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground='grey', cursor='hand2')
    label = tk.Label(frame, text=text, bg=bg, fg=fg, font=font, cursor='hand2')
    label.pack(padx=16, pady=12, fill='both', expand=True)
    frame._label = label
    frame._touch_action = action
    if bind:
        for w in (frame, label):
            for seq in ('<Button-1>', '<ButtonRelease-1>', '<1>'):
                w.bind(seq, lambda e, a=action: (a(), 'break')[1])
    return frame


class MessageDisplayApp:
    def __init__(self, root):
        self.root = root
        self.name = ''
        self._speak_procs = []
        self._speak_lock = threading.Lock()
        self._picture_step = None
        self._picture_after_id = None
        self._running = True
        self._socket = None
        self._msg_queue = deque(maxlen=100)
        self._msg_drain_scheduled = False
        self._touch_targets = []
        self._robot_docker_running = False
        self._robot_ros_running = False
        self._robot_busy = False
        self._robot_busy_action = None

        root.title('Message Display')
        root.attributes('-fullscreen', True)
        root.configure(bg='black')
        root.bind('<Escape>', lambda e: root.attributes('-fullscreen', False))
        root.protocol('WM_DELETE_WINDOW', self.exit_application)
        root.grid_rowconfigure(1, weight=1)
        self._toolbar_cols = 6 if SHOW_PICTURE_BUTTON else 5
        for i in range(self._toolbar_cols):
            root.grid_columnconfigure(i, weight=1)

        btn_kw = dict(bg='white', fg='black', font=('Helvetica', 16))
        self.toolbar = tk.Frame(root, bg='black')
        self.toolbar.grid(row=0, column=0, columnspan=self._toolbar_cols, sticky='ew')
        for i in range(self._toolbar_cols):
            self.toolbar.grid_columnconfigure(i, weight=1)

        col = 0
        self.clear_button = self._make_button('Clear', self.clear_text, col, **btn_kw)
        col += 1
        self.chat_button = self._make_button('Chat', self.chat_action, col, **btn_kw)
        col += 1
        self.goal_button = self._make_button('Set Goal', self.goal_action, col, **btn_kw)
        col += 1
        if SHOW_PICTURE_BUTTON:
            self.picture_button = self._make_button('Take Picture', self.picture_action, col, **btn_kw)
            col += 1
        else:
            self.picture_button = None
        self.robot_button = self._make_button('Start Docker', self.robot_toggle_action, col, **btn_kw)
        col += 1
        self.exit_button = self._make_button('Exit', self.exit_application, col, **btn_kw)

        self.text_widget = tk.Text(root, bg='black', fg='white', insertbackground='white',
                                   font=('Helvetica', 40), state='disabled', cursor='arrow',
                                   takefocus=0)
        self.text_widget.grid(row=1, column=0, columnspan=self._toolbar_cols, sticky='nsew', padx=10, pady=10)
        self._msg_font = tkfont.Font(font=self.text_widget['font'])
        self._wrap_pixels = 0
        self.text_widget.bind('<Configure>', lambda e: self._update_wrap_width())
        self.toolbar.lift()

        for seq in ('<Button-1>', '<ButtonRelease-1>', '<1>'):
            root.bind_all(seq, self._global_touch, add='+')

        threading.Thread(target=self._socket_server, daemon=True).start()

        self._style_mode_btn(self.chat_button, active=True)
        self._post_json({'query_type': 'set_mode', 'query': 'chat'})
        self.root.after_idle(self._show_welcome)
        self.root.after(ROBOT_POLL_MS, self._poll_robot_status)

    def _show_welcome(self):
        self._update_wrap_width()
        self._enqueue_message(DEFAULT_MESSAGE)

    def _update_wrap_width(self):
        self.root.update_idletasks()
        w = self.text_widget.winfo_width()
        if w <= 1:
            return
        margin_px = int(os.environ.get('MATTBOT_WRAP_MARGIN_PX', '0'))
        if margin_px <= 0:
            margin_px = self._msg_font.measure('MM')
        pad = 20
        self._wrap_pixels = max(100, w - pad - margin_px)

    def _make_button(self, text, action, column, **kwargs):
        btn = _touch_button(self.toolbar, text, action, bind=False, **kwargs)
        btn.grid(row=0, column=column, padx=20, pady=10, sticky='nsew')
        self._touch_targets.append(btn)
        return btn

    def _global_touch(self, event):
        self.root.update_idletasks()
        x, y = event.x_root, event.y_root
        for btn in self._touch_targets:
            if not btn.winfo_exists():
                continue
            bx, by = btn.winfo_rootx(), btn.winfo_rooty()
            if bx <= x <= bx + btn.winfo_width() and by <= y <= by + btn.winfo_height():
                log.info('Touch: %s', btn._label.cget('text'))
                btn._touch_action()
                return 'break'

    def _style_mode_btn(self, btn, active=False):
        bg = 'darkgrey' if active else 'white'
        font = ('Helvetica', 20 if active else 16)
        btn.config(bg=bg)
        btn._label.config(bg=bg, font=font)

    def _post_json(self, data):
        def do_post():
            req = urllib.request.Request(
                BACKEND_URL, data=json.dumps(data).encode(),
                method='POST', headers={'Content-Type': 'application/json'})
            try:
                urllib.request.urlopen(req, timeout=2)
            except (urllib.error.URLError, OSError) as e:
                log.warning('Backend request failed: %s', e)
        threading.Thread(target=do_post, daemon=True).start()

    @staticmethod
    def _robot_get_json(base_url, path, timeout=5, quiet=False):
        url = base_url.rstrip('/') + path
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as e:
            if not quiet:
                log.warning('Robot GET %s failed: %s', url, e)
            return None

    @staticmethod
    def _robot_get_text(base_url, path, timeout=5):
        url = base_url.rstrip('/') + path
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return True, resp.read().decode().strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors='replace').strip()
            log.warning('Robot GET %s failed: %s %s', url, e, body)
            return False, body or str(e)
        except (urllib.error.URLError, OSError) as e:
            log.warning('Robot GET %s failed: %s', url, e)
            return False, str(e)

    def _robot_update_button_label(self):
        if self._robot_busy:
            labels = {'docker': 'Starting Docker...', 'start': 'Starting...', 'stop': 'Stopping...'}
            label = labels.get(self._robot_busy_action, '...')
        elif not self._robot_docker_running:
            label = 'Start Docker'
        elif self._robot_ros_running:
            label = 'Stop Robot'
        else:
            label = 'Start Robot'
        self.robot_button._label.config(text=label)

    def _poll_robot_status(self):
        if self._running and not self._robot_busy:
            threading.Thread(target=self._robot_poll_worker, daemon=True).start()
        if self._running:
            try:
                self.root.after(ROBOT_POLL_MS, self._poll_robot_status)
            except tk.TclError:
                pass

    def _robot_poll_worker(self):
        host = self._robot_get_json(HOST_SERVICE_URL, '/status', quiet=True)
        docker = bool(host and host.get('docker_running'))
        launcher = self._robot_get_json(LAUNCHER_URL, '/status', quiet=True)
        ros = bool(launcher and launcher.get('ros_running'))
        self._schedule_ui(self._robot_set_status, docker, ros)

    def _robot_set_status(self, docker, ros):
        self._robot_docker_running = docker
        self._robot_ros_running = ros
        self._robot_update_button_label()

    def robot_toggle_action(self):
        if self._robot_busy:
            return
        if not self._robot_docker_running:
            self._robot_busy = True
            self._robot_busy_action = 'docker'
            self._robot_update_button_label()
            threading.Thread(target=self._robot_docker_start_worker, daemon=True).start()
        elif self._robot_ros_running:
            self._robot_busy = True
            self._robot_busy_action = 'stop'
            self._robot_update_button_label()
            threading.Thread(target=self._robot_stop_worker, daemon=True).start()
        else:
            self._robot_busy = True
            self._robot_busy_action = 'start'
            self._robot_update_button_label()
            threading.Thread(target=self._robot_ros_start_worker, daemon=True).start()

    def _robot_docker_start_worker(self):
        status = self._robot_get_json(HOST_SERVICE_URL, '/status')
        if status is None:
            self._robot_finish('Robot host service unavailable (port 8081).', None)
            return
        if status.get('docker_running'):
            self._robot_finish('Docker is already running.', None)
            return
        ok, msg = self._robot_get_text(HOST_SERVICE_URL, '/docker-start', timeout=120)
        if not ok:
            self._robot_finish(f'Docker start failed: {msg}', None)
            return
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._robot_get_json(LAUNCHER_URL, '/status', quiet=True):
                break
            time.sleep(0.5)
        self._robot_finish(msg or 'Docker started.', None)

    def _robot_ros_start_worker(self):
        if self._robot_get_json(LAUNCHER_URL, '/status', quiet=True) is None:
            self._robot_finish('Launcher unavailable. Start Docker first.', None)
            return
        ok, msg = self._robot_get_text(LAUNCHER_URL, ROS_START_PATH, timeout=120)
        if not ok:
            self._robot_finish(f'ROS start failed: {msg}', None)
            return
        self._robot_finish(msg or 'Robot started.', True)

    def _robot_stop_worker(self):
        ok, msg = self._robot_get_text(LAUNCHER_URL, '/stop', timeout=30)
        if ok:
            self._robot_finish(msg or 'Robot stopped.', False)
        else:
            self._robot_finish(f'Stop failed: {msg}', None)

    def _robot_finish(self, message, ros_running):
        def done():
            self._robot_busy = False
            self._robot_busy_action = None
            host = self._robot_get_json(HOST_SERVICE_URL, '/status', quiet=True)
            self._robot_docker_running = bool(host and host.get('docker_running'))
            if ros_running is not None:
                self._robot_ros_running = ros_running
            else:
                data = self._robot_get_json(LAUNCHER_URL, '/status', quiet=True)
                self._robot_ros_running = bool(data and data.get('ros_running'))
            if message:
                log.info('Robot: %s', message)
                self._append_text(f'\n{message}\n\n')
            self._robot_update_button_label()
        self._schedule_ui(done)

    def exit_application(self):
        log.info('Exit to desktop')
        self._running = False
        self._abort_picture()
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
        self._stop_speech()
        try:
            self.root.attributes('-fullscreen', False)
            self.root.update_idletasks()
        except tk.TclError:
            pass
        self.root.destroy()

    def _stop_speech(self):
        with self._speak_lock:
            for proc in self._speak_procs:
                if proc.poll() is None:
                    proc.terminate()
            self._speak_procs = []

    def _speak_text(self, text):
        text = text.strip().replace('\n', ' ')
        if not text:
            return
        if len(text) > MAX_SPEAK_CHARS:
            text = text[:MAX_SPEAK_CHARS]
        if not PIPER_BIN.is_file() or not PIPER_MODEL.is_file():
            return
        self._stop_speech()
        threading.Thread(target=self._speak_worker, args=(text,), daemon=True).start()

    def _speak_worker(self, text):
        piper_cmd = [str(PIPER_BIN), '--model', str(PIPER_MODEL), '--output_raw',
                     '--length_scale', str(PIPER_LENGTH_SCALE)]
        if PIPER_SPEAKER:
            piper_cmd.extend(['--speaker', PIPER_SPEAKER])
        aplay_cmd = ['aplay', '-r', str(PIPER_SAMPLE_RATE), '-f', 'S16_LE', '-c', '1', '-t', 'raw']
        if ALSA_DEVICE:
            aplay_cmd.extend(['-D', ALSA_DEVICE])
        aplay_cmd.append('-')
        piper = aplay = None
        try:
            piper = subprocess.Popen(
                piper_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL)
            aplay = subprocess.Popen(
                aplay_cmd, stdin=piper.stdout, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE)
            piper.stdout.close()
            with self._speak_lock:
                self._speak_procs = [piper, aplay]
            piper.communicate(input=text.encode('utf-8'), timeout=60)
            aplay.wait(timeout=30)
            if aplay.returncode not in (0, -15):
                err = aplay.stderr.read().decode(errors='replace').strip() if aplay.stderr else ''
                log.warning('Speech playback failed: %s', err or aplay.returncode)
        except subprocess.TimeoutExpired:
            log.warning('Speech timed out')
            self._stop_speech()
        except OSError as e:
            log.warning('Speech failed: %s', e)
        finally:
            with self._speak_lock:
                if piper in self._speak_procs or aplay in self._speak_procs:
                    self._speak_procs = []

    def _wrap_paragraph(self, paragraph, max_px):
        parts, line = [], ''
        for word in paragraph.split():
            candidate = (line + ' ' + word).strip()
            if line and self._msg_font.measure(candidate) > max_px:
                parts.append(line)
                line = word
            else:
                line = candidate
        if line:
            parts.append(line)
        return '\n'.join(parts)

    def _wrap_message(self, message):
        if self._wrap_pixels <= 0:
            self._update_wrap_width()
        max_px = self._wrap_pixels or 800
        paragraphs = [p.strip() for p in message.split('\n') if p.strip()]
        if not paragraphs:
            return ''
        return '\n'.join(self._wrap_paragraph(p, max_px) for p in paragraphs)

    def _append_text(self, text):
        self.text_widget.config(state='normal')
        self.text_widget.insert(tk.END, text)
        if len(self.text_widget.get('1.0', tk.END)) > MAX_TEXT_CHARS:
            self.text_widget.delete('1.0', 'end-4000c')
        self.text_widget.see(tk.END)
        self.text_widget.config(state='disabled')

    def _append_message(self, message):
        log.info(message)
        if message not in STATUS_MESSAGES:
            self._speak_text(message)
        self._append_text(self._wrap_message(message))
        self._append_text('\n\n\n' if message != 'Listening...' else ' ')

    def _enqueue_message(self, message):
        self._msg_queue.append(message)
        if not self._msg_drain_scheduled:
            self._msg_drain_scheduled = True
            self._schedule_ui(self._drain_messages)

    def _drain_messages(self):
        self._msg_drain_scheduled = False
        if not self._msg_queue:
            return
        msg = self._msg_queue.popleft()
        try:
            self._append_message(msg)
        except tk.TclError:
            return
        if self._msg_queue:
            self._msg_drain_scheduled = True
            self.root.after(50, self._drain_messages)

    def _set_active(self, button):
        mode_buttons = [self.chat_button, self.goal_button]
        if self.picture_button:
            mode_buttons.append(self.picture_button)
        for b in mode_buttons:
            self._style_mode_btn(b, active=(b is button))

    def _abort_picture(self):
        if self._picture_after_id:
            self.root.after_cancel(self._picture_after_id)
            self._picture_after_id = None
        self._picture_step = None
        if self.picture_button:
            self._style_mode_btn(self.picture_button, active=False)

    def clear_text(self):
        log.info('Clear')
        self._abort_picture()
        self._remove_input_frame()
        self.text_widget.config(state='normal')
        self.text_widget.delete(1.0, tk.END)
        self.text_widget.config(state='disabled')
        self._enqueue_message(DEFAULT_MESSAGE)

    def chat_action(self):
        log.info('Chat')
        self._set_active(self.chat_button)
        self._post_json({'query_type': 'set_mode', 'query': 'chat'})

    def goal_action(self):
        log.info('Goal')
        self._set_active(self.goal_button)
        self._post_json({'query_type': 'set_mode', 'query': 'set_goal'})

    def picture_action(self):
        log.info('Picture')
        if self.picture_button:
            self._style_mode_btn(self.picture_button, active=True)
            self._style_mode_btn(self.chat_button, active=False)
        self.text_widget.config(state='normal')
        self.text_widget.delete(1.0, tk.END)
        self.text_widget.config(state='disabled')
        self._picture_step = 0
        self._post_json({'query_type': 'take_picture', 'query': 'take_picture'})
        self._picture_tick()

    def _schedule_picture(self, delay_ms, next_step):
        self._picture_after_id = self.root.after(delay_ms, self._picture_advance, next_step)

    def _picture_advance(self, next_step):
        self._picture_after_id = None
        self._picture_step = next_step
        self._picture_tick()

    def _picture_tick(self):
        if self._picture_step is None:
            return
        step = self._picture_step
        if step == 0:
            self._append_text('Please look at the camera!\n\n')
            self._schedule_picture(1000, 1)
        elif step <= 5:
            self._append_text(f'{6 - step} ... ')
            self._schedule_picture(1000, step + 1)
        elif step == 6:
            self._append_text(' Cheese!\n\n')
            self._schedule_picture(2000, 7)
        elif step == 7:
            self._append_text('Your picture has been taken!\n\n')
            self._schedule_picture(1000, 8)
        elif step == 8:
            self._abort_picture()
            self.text_widget.config(state='normal')
            self.text_widget.delete(1.0, tk.END)
            self.text_widget.config(state='disabled')
            self._append_text('\n\nPlease Type Your First and\nLast Name Below and Press Enter\n\n')
            self._show_name_entry()

    def _show_name_entry(self):
        frame = tk.Frame(self.root, bg='black')
        frame.grid(row=2, column=0, columnspan=self._toolbar_cols, sticky='ew', padx=10, pady=10)
        frame.grid_columnconfigure(0, weight=3)
        frame.grid_columnconfigure(1, weight=1)
        self._input_frame = frame
        self.user_input = tk.Entry(frame, font=('Helvetica', 32), bg='white', fg='black')
        self.user_input.grid(row=0, column=0, padx=(0, 10), sticky='ew')
        self.cancel_button = _touch_button(frame, 'Cancel', self.cancel_button_action,
                                           bg='white', fg='black', font=('Helvetica', 16))
        self.cancel_button.grid(row=0, column=1, padx=(10, 0), sticky='ew')
        self.user_input.focus_set()
        self.user_input.bind('<Return>', lambda e: self.process_first_name())

    def _remove_input_frame(self):
        if hasattr(self, '_input_frame') and self._input_frame.winfo_exists():
            self._input_frame.destroy()
            self.root.grid_rowconfigure(2, weight=0)

    def process_first_name(self):
        self.name = self.user_input.get()
        self._remove_input_frame()
        self.text_widget.config(state='normal')
        self.text_widget.delete(1.0, tk.END)
        self.text_widget.config(state='disabled')
        self._append_text('\n\nYour name and picture have been saved!\n\n')
        self._post_json({'query_type': 'set_name', 'query': self.name})
        self.root.after(2000, self.clear_text)

    def cancel_button_action(self):
        self._abort_picture()
        self._remove_input_frame()
        self._post_json({'query_type': 'cancel_picture', 'query': 'cancel_picture'})
        self.clear_text()

    def _socket_server(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(('0.0.0.0', SOCKET_PORT))
        self._socket.listen()
        while self._running:
            try:
                conn, _ = self._socket.accept()
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn):
        buf = ''
        with conn:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data.decode('utf-8', errors='replace')
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    if line:
                        self._schedule_ui(self._enqueue_message, line)
        if buf.strip():
            self._schedule_ui(self._enqueue_message, buf.strip())

    def _schedule_ui(self, fn, *args):
        if not self._running:
            return
        try:
            self.root.after(0, fn, *args)
        except tk.TclError:
            pass


if __name__ == '__main__':
    root = tk.Tk()
    MessageDisplayApp(root)
    root.mainloop()
