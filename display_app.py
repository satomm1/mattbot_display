#!/usr/bin/python3
import os
os.environ['TK_ENABLE_PLATFORM_GL'] = '0'

import json
import logging
import re
import socket
import subprocess
import threading
import tkinter as tk
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

from helvetica import helvetica_widths

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

BACKEND_URL = os.environ.get('MATTBOT_BACKEND_URL', 'http://127.0.0.1:5000/gemini')
SOCKET_PORT = int(os.environ.get('MATTBOT_SOCKET_PORT', '65432'))
AUDIO_DIR = Path(os.environ.get('MATTBOT_AUDIO_DIR', Path.home() / 'Desktop' / 'audio'))


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

DEFAULT_MESSAGE = 'Hello! I am a mobile robot.\nSay "Hey Robot" to talk to me.'
CHARACTER_WIDTH = 19
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
        self._audio_proc = None
        self._picture_step = None
        self._picture_after_id = None
        self._running = True
        self._socket = None
        self._msg_queue = deque(maxlen=100)
        self._msg_drain_scheduled = False
        self._touch_targets = []

        root.title('Message Display')
        root.attributes('-fullscreen', True)
        root.configure(bg='black')
        root.bind('<Escape>', lambda e: root.attributes('-fullscreen', False))
        root.protocol('WM_DELETE_WINDOW', self.exit_application)
        root.grid_rowconfigure(1, weight=1)
        toolbar_cols = 5 if SHOW_PICTURE_BUTTON else 4
        self._toolbar_cols = toolbar_cols
        for i in range(toolbar_cols):
            root.grid_columnconfigure(i, weight=1)

        btn_kw = dict(bg='white', fg='black', font=('Helvetica', 16))
        self.toolbar = tk.Frame(root, bg='black')
        self.toolbar.grid(row=0, column=0, columnspan=toolbar_cols, sticky='ew')
        for i in range(toolbar_cols):
            self.toolbar.grid_columnconfigure(i, weight=1)

        self.clear_button = self._make_button('Clear', self.clear_text, 0, **btn_kw)
        self.chat_button = self._make_button('Chat', self.chat_action, 1, **btn_kw)
        self.goal_button = self._make_button('Set Goal', self.goal_action, 2, **btn_kw)
        if SHOW_PICTURE_BUTTON:
            self.picture_button = self._make_button('Take Picture', self.picture_action, 3, **btn_kw)
            self.exit_button = self._make_button('Exit', self.exit_application, 4, **btn_kw)
        else:
            self.picture_button = None
            self.exit_button = self._make_button('Exit', self.exit_application, 3, **btn_kw)

        self.text_widget = tk.Text(root, bg='black', fg='white', insertbackground='white',
                                   font=('Helvetica', 40), state='disabled', cursor='arrow',
                                   takefocus=0)
        self.text_widget.grid(row=1, column=0, columnspan=toolbar_cols, sticky='nsew', padx=10, pady=10)
        self.toolbar.lift()

        for seq in ('<Button-1>', '<ButtonRelease-1>', '<1>'):
            root.bind_all(seq, self._global_touch, add='+')

        threading.Thread(target=self._socket_server, daemon=True).start()

        self._style_mode_btn(self.chat_button, active=True)
        self._post_json({'query_type': 'set_mode', 'query': 'chat'})
        self.root.after_idle(lambda: self._enqueue_message(DEFAULT_MESSAGE))

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

    def exit_application(self):
        log.info('Exit to desktop')
        self._running = False
        self._abort_picture()
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
        if self._audio_proc and self._audio_proc.poll() is None:
            self._audio_proc.terminate()
        try:
            self.root.attributes('-fullscreen', False)
            self.root.update_idletasks()
        except tk.TclError:
            pass
        self.root.destroy()

    def _play_sound(self, path):
        if self._audio_proc and self._audio_proc.poll() is None:
            self._audio_proc.terminate()
        path = Path(path)
        if not path.is_file():
            log.warning('Audio file not found: %s', path)
            return
        if path.suffix.lower() == '.wav':
            cmd = ['aplay', '-D', ALSA_DEVICE, str(path)] if ALSA_DEVICE else ['aplay', str(path)]
        else:
            cmd = ['mpg123', '-q', str(path)]
            if ALSA_DEVICE:
                cmd = ['mpg123', '-a', ALSA_DEVICE, '-q', str(path)]
        try:
            self._audio_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            threading.Thread(target=self._watch_audio, args=(path.name,), daemon=True).start()
        except OSError as e:
            log.warning('Audio playback failed: %s', e)

    def _watch_audio(self, name):
        if not self._audio_proc:
            return
        err = self._audio_proc.communicate()[1]
        rc = self._audio_proc.returncode
        if rc not in (0, -15):  # 0=ok, -15=terminated for next sound
            msg = err.decode(errors='replace').strip() if err else f'exit {rc}'
            log.warning('Audio %s failed: %s', name, msg)

    def _word_length(self, word):
        return sum(helvetica_widths.get(c, 0.5) for c in word)

    def _wrap_message(self, message):
        parts, line_len = [], 0
        for word in message.split():
            wlen = self._word_length(word)
            if line_len + wlen > CHARACTER_WIDTH:
                parts.append('\n')
                line_len = 0
            line_len += wlen + 0.5
            parts.append(word + ' ')
        return ''.join(parts).strip()

    def _append_text(self, text):
        self.text_widget.config(state='normal')
        self.text_widget.insert(tk.END, text)
        if len(self.text_widget.get('1.0', tk.END)) > MAX_TEXT_CHARS:
            self.text_widget.delete('1.0', 'end-4000c')
        self.text_widget.see(tk.END)
        self.text_widget.config(state='disabled')

    def _append_message(self, message):
        log.info(message)
        if message == DEFAULT_MESSAGE:
            self._play_sound(AUDIO_DIR / 'default.mp3')
        elif message not in STATUS_MESSAGES:
            self._play_sound(AUDIO_DIR / 'response.mp3')
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
