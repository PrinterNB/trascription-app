import re
import shutil
import subprocess
import time

import numpy
import sounddevice

SAMPLERATE = 16000
# Spawned helpers (ffmpeg per capture chunk) must NOT open a console window: on
# Windows each spawn would grab a conhost window and steal keyboard focus.
NO_CONSOLE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _list_dshow():
    """List the Windows microphone inputs ffmpeg's DirectShow can capture.

    This is what the settings UI shows: unlike PortAudio/sounddevice, DirectShow
    enumerates real microphones (headset mics included)."""
    ff = _ffmpeg_path()
    if not ff:
        return []
    try:
        p = subprocess.run(
            [ff, "-hide_banner", "-f", "dshow", "-list_devices", "true", "-i", "video=none"],
            capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL, creationflags=NO_CONSOLE,
        )
    except Exception:
        return []
    out = []
    for line in (p.stdout + p.stderr).splitlines():
        m = re.search(r'"(.+?)"\s+\(audio\)', line)
        if m:
            out.append(m.group(1))
    return out


def _ffmpeg_path():
    return shutil.which("ffmpeg")


def _list_sd():
    """List input-device indices visible to sounddevice/PortAudio."""
    try:
        devs = sounddevice.query_devices()
    except Exception:
        return []
    out = []
    for i, d in enumerate(devs):
        try:
            if str(d.get("type", "")).upper().startswith("INPUT") and d.get("channels", 0) > 0:
                out.append((i, str(d.get("name", "input"))))
        except Exception:
            continue
    return out


def _pick_sd():
    """Return a sounddevice index preferring anything named like a microphone."""
    for i, name in _list_sd():
        low = name.lower()
        if "mic" in low or "audio in" in low or "microphone" in low:
            return i
    xs = _list_sd()
    return xs[0][0] if xs else None


def _resolve(device):
    """Map a user token to a concrete (backend, value) pair.

    '' / '-1' / None -> auto: use DirectShow on Windows (sees real mics), else
    PortAudio. 'ds:<name>' -> DirectShow. 'sd:<idx>' -> PortAudio index.
    """
    if isinstance(device, str):
        s = device.strip()
        if s and s != "-1":
            if s.startswith("ds:"):
                return ("dshow", s[3:])
            if s.startswith("sd:"):
                try:
                    return ("sd", int(s[3:]))
                except ValueError:
                    pass
            try:
                return ("sd", int(s))
            except ValueError:
                pass
    # auto
    for name in _list_dshow():
        low = name.lower()
        if "mic" in low or "headset" in low or "microphone" in low:
            return ("dshow", name)
    ds = _list_dshow()
    if ds:
        return ("dshow", ds[0])
    return ("sd", _pick_sd())


def _ffmpeg_chunk(name, seconds):
    """Capture `seconds` seconds of raw PCM from a DirectShow source.

    `-t` is an INPUT option (before -i): with no cap the DirectShow source
    closes after ~0.1s on Windows capture filters, so every capture is capped
    and repeated by _dshow_key_held."""
    ff = _ffmpeg_path()
    if not ff:
        return numpy.zeros(0, dtype=numpy.int16)
    args = [ff, "-hide_banner", "-y", "-t", repr(float(seconds)),
            "-f", "dshow", "-i", f"audio={name}",
            "-vn", "-ac", "1", "-ar", str(SAMPLERATE),
            "-acodec", "pcm_s16le", "-f", "s16le", "pipe:1"]
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=max(10.0, seconds * 4),
                          stdin=subprocess.DEVNULL, creationflags=NO_CONSOLE)
    except Exception:
        return numpy.zeros(0, dtype=numpy.int16)
    return numpy.frombuffer(p.stdout, dtype=numpy.int16)


def _dshow_key_held(name, is_key_held, timeout, chunk=0.5, on_start=None, idle_wait=5.0):
    """Capture continuously and keep only the audio while the key is held.

    Chunks are captured whether or not the key is down, so the stream is
    already rolling when the key goes down: the chunk that contains the press
    is kept, which means listening starts the instant the key is pressed.

    A single dshow stream EOFs after ~0.1s, so continuous capture is a loop of
    short ffmpeg runs; the key check between chunks is what honors
    'listen only while I'm holding the key' (release caught within ~chunk).

    `timeout` caps one dictation once the key registers; `idle_wait` caps the
    wait for a press - after that we return held=False so the caller can
    re-read the config (a trigger key changed on the settings page takes
    effect within idle_wait, no app restart). Returns
    (audio, duration_seconds, key_was_held)."""
    parts = []
    total = 0
    started = False
    t0 = time.time()
    t_press = t0
    while True:
        now = time.time()
        if not started and now - t0 > idle_wait:
            break
        if started and now - t_press > timeout:
            break
        limit = (idle_wait if not started else timeout) - (now - (t0 if not started else t_press))
        if limit <= 0:
            break
        raw = _ffmpeg_chunk(name, min(chunk, limit))
        if is_key_held():
            if raw.size == 0:
                # key held but the source yielded nothing: dead mic
                return numpy.zeros(0, dtype=numpy.float32), 0.0, True
            if not started:
                started = True
                t_press = now
                if on_start:
                    on_start()
            parts.append(raw)
            total += raw.size
        elif started:
            break
    if not parts:
        return numpy.zeros(0, dtype=numpy.float32), 0.0, started
    cat = numpy.concatenate(parts)
    return cat.astype(numpy.float32) / 32768.0, total / float(SAMPLERATE), started


def _sd_fixed(seconds, samplerate, dev):
    frames = []

    def collect(data, _frames, _t, _status):
        frames.append(numpy.frombuffer(data, dtype=numpy.int16))

    with sounddevice.RawInputStream(
        samplerate=samplerate, blocksize=1600, device=dev,
        dtype="int16", channels=1, callback=collect,
    ):
        time.sleep(seconds)
    return _to_float(frames)


def _sd_key_held(is_key_held, timeout, dev, on_start=None, idle_wait=5.0):
    """PortAudio twin of _dshow_key_held (same idle_wait/timeout split)."""
    frames = []

    def collect(data, _frames, _t, _status):
        frames.append(numpy.frombuffer(data, dtype=numpy.int16))

    started = False
    t0 = time.time()
    t_press = t0
    duration = 0.0
    with sounddevice.RawInputStream(
        samplerate=SAMPLERATE, blocksize=1600, device=dev,
        dtype="int16", channels=1, callback=collect,
    ):
        while True:
            now = time.time()
            if not started and now - t0 > idle_wait:
                break
            if started and now - t_press > timeout:
                break
            if is_key_held():
                if not started:
                    started = True
                    t_press = now
                    if on_start:
                        on_start()
                duration = time.time() - t_press
            elif started:
                break
            else:
                del frames[:]  # idle: drop anything heard before the press
            time.sleep(0.05)
        deadline = time.time() + 0.25
        while time.time() < deadline:
            time.sleep(0.01)
    if not started:
        return numpy.zeros(0, dtype=numpy.float32), 0.0, False
    return _to_float(frames), duration, started


def record_fixed(seconds, samplerate=SAMPLERATE, device=None):
    mode, val = _resolve(device)
    if mode == "dshow":
        raw = _ffmpeg_chunk(val, seconds)
        return raw.astype(numpy.float32) / 32768.0
    return _sd_fixed(seconds, samplerate, val)


def record_key_held(is_key_held, timeout=600, device=None, on_start=None, idle_wait=5.0):
    """Capture continuously; keep audio only while `is_key_held()` is true.

    Capture runs ahead of the press, so listening begins the moment the key
    goes down. `idle_wait` bounds the wait for a press: when nothing was ever
    held we return quickly so callers can re-read their config (a trigger key
    changed on the settings page applies within idle_wait). `on_start` is
    called once when the key first registers. Returns
    (audio, duration_seconds, key_was_held)."""
    mode, val = _resolve(device)
    if mode == "dshow":
        return _dshow_key_held(val, is_key_held, timeout, on_start=on_start, idle_wait=idle_wait)
    return _sd_key_held(is_key_held, timeout, val, on_start, idle_wait)


def _to_float(frames):
    if not frames:
        return numpy.zeros(0, dtype=numpy.float32)
    raw = numpy.frombuffer(b"".join(frames), dtype=numpy.int16)
    return raw.astype(numpy.float32) / 32768.0


def peak(audio):
    if audio is None or len(audio) == 0:
        return 0.0
    return float(numpy.abs(audio).max())
