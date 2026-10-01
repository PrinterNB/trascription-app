import base64
import ctypes
import os
import re
import subprocess
import sys
import threading
import time

import config as config_mod
import recorder
import asr
import trayicon
import webui

import tkinter
from tkinter import messagebox

import pystray
from pystray import Icon, Menu, MenuItem

# pythonw.exe (windowed, how the launcher starts us) has no sys.stderr; give
# anything that prints (tqdm, http logs) a sink so nothing raises.
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# Virtual key codes shared with the settings UI (single source of truth).
KEY_VK = webui.KEY_VK

CFG = config_mod.load()
STATUS = {"status": "idle", "paused": False}
ICON = None


def log_error(msg):
    path = os.path.join(os.path.dirname(config_mod.CONFIG_PATH), "errors.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def key_down(name):
    # A trigger may be a single key ("f9") or a combination ("ctrl+f9", "win+ctrl"):
    # all parts must be physically held at once.
    parts = [p for p in str(name).split("+") if p.strip()]
    if not parts:
        parts = ["f9"]
    for part in parts:
        vk = KEY_VK.get(part.strip())
        if vk is None:
            continue
        if not (ctypes.windll.user32.GetKeyState(vk) & 0x8000):
            return False
    return True


def mic_device():
    """Selected microphone token: '' = auto, 'ds:<name>' = DirectShow source,
    'sd:<idx>' = PortAudio input. The recorder resolves the token."""
    v = CFG.get("input_device", "")
    return v if isinstance(v, str) else ""


def set_status(status):
    STATUS["status"] = status
    webui.LIVE_STATUS["stage"] = status
    webui.LIVE_STATUS["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if ICON:
        try:
            ICON.icon = trayicon.image_for(status)
            ICON.title = _title()
        except Exception:
            pass


def note(detail):
    webui.LIVE_STATUS["detail"] = detail


def _title():
    return (
        "Voice Dictation - hold "
        + webui._key_label(CFG.get("trigger_key", "f9"))
        + " while you speak, release to dictate"
    )


def apply_commands(text, commands):
    out = text
    for cmd in commands:
        phrase = (cmd.get("say") or "").strip()
        if not phrase:
            continue
        insert = cmd.get("insert", "")
        out = re.sub(re.escape(phrase), lambda _m: insert, out, flags=re.IGNORECASE)
    return out


def _chunks(text, size):
    parts = []
    i = 0
    while i < len(text):
        j = min(i + size, len(text))
        if j < len(text):
            space = text.rfind(" ", i, j)
            if space > i:
                j = space
        parts.append(text[i:j])
        i = j
    return parts or [""]


def ps_run(script):
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    subprocess.run(["powershell.exe", "-EncodedCommand", encoded], check=False)


def set_clipboard(text):
    for chunk in _chunks(text, 3000):
        ps_run("Set-Clipboard -Value '" + chunk.replace("'", "''") + "'")


def send_keys(text):
    vbs = os.path.join(os.path.dirname(config_mod.CONFIG_PATH), "sendkeys.vbs")
    for chunk in _chunks(text, 3000):
        r = subprocess.run(
            ["cscript.exe", "//nologo", vbs, chunk], capture_output=True, text=True
        )
        if r.returncode != 0:
            raise OSError((r.stderr or r.stdout or "sendkeys failed").strip())


def hotkey_loop():
    while True:
        try:
            if STATUS["paused"]:
                time.sleep(0.3)
                continue
            key = CFG.get("trigger_key", "f9")
            while not key_down(key):
                time.sleep(0.03)
            set_status("recording")
            audio, duration = recorder.record_until_key_up(lambda: not key_down(key), device=mic_device())
            if len(audio) == 0:
                note("the selected microphone returned no audio - pick another source in the settings UI")
                set_status("idle")
                continue
            if duration < 0.5:
                note(f"released after {duration:.2f}s - too short to dictate")
                set_status("idle")
                continue
            if recorder.peak(audio) < 0.002:
                note(f"heard {duration:.1f}s of SILENCE - microphone not capturing")
                set_status("idle")
                continue
            set_status("processing")
            note(f"heard {duration:.1f}s of audio")
            try:
                text = asr.transcribe(audio, CFG)
            except Exception as e:
                log_error(f"transcription failed: {e}")
                note(f"engine error: {e}")
                set_status("idle")
                continue
            if text:
                text = apply_commands(text, CFG.get("commands", []))
                try:
                    if CFG.get("output_mode", "autotype") == "clipboard":
                        set_clipboard(text)
                    else:
                        send_keys(text)
                except Exception as e:
                    log_error(f"output failed: {e}")
                    note(f"output error: {e}")
                else:
                    note(f"typed into focused window ({len(text)} chars)")
            else:
                note("nothing recognized (empty text)")
            set_status("idle")
        except Exception as e:
            log_error(f"dictation cycle failed: {e}")


def on_settings(_icon, _item):
    webui.open_in_browser()


def on_models(_icon, _item):
    webui.open_models_in_browser()


def on_test(_icon, _item):
    audio = recorder.record_fixed(4)
    try:
        text = asr.transcribe(audio, CFG)
        messagebox.showinfo("Voice Dictation test", ("Heard: " + text) if text else "Nothing recognized.")
    except Exception as e:
        log_error(str(e))
        messagebox.showerror("Voice Dictation test", str(e))


def on_quit(_icon, _item):
    if ICON:
        ICON.stop()


def on_pause(_icon, _item):
    STATUS["paused"] = True


def on_resume(_icon, _item):
    STATUS["paused"] = False


MENU = Menu(
    MenuItem("Open settings", on_settings),
    MenuItem("Model manager", on_models),
    MenuItem("Pause listening", on_pause, checked=lambda _icon: STATUS["paused"]),
    MenuItem("Resume listening", on_resume, checked=lambda _icon: not STATUS["paused"]),
    MenuItem("Test microphone", on_test),
    MenuItem("Quit", on_quit),
)


def main():
    global ICON
    if "--settings" in sys.argv[1:]:
        webui.open_settings_standalone(CFG)
        return
    webui.LIVE_CFG = CFG
    webui.start_server()
    ICON = Icon("Voice Dictation", trayicon.image_for("idle"), _title(), MENU)
    threading.Thread(target=hotkey_loop, name="VoiceDictation", daemon=True).start()
    ICON.run()


if __name__ == "__main__":
    main()
