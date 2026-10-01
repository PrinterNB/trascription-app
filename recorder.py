import re
import shutil
import subprocess
import time

import numpy
import sounddevice

SAMPLERATE = 16000


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
    and repeated by _ffmpeg_until_key_up."""
    ff = _ffmpeg_path()
    if not ff:
        return numpy.zeros(0, dtype=numpy.int16)
    args = [ff, "-hide_banner", "-y", "-t", repr(float(seconds)),
            "-f", "dshow", "-i", f"audio={name}",
            "-vn", "-ac", "1", "-ar", str(SAMPLERATE),
            "-acodec", "pcm_s16le", "-f", "s16le", "pipe:1"]
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=max(10.0, seconds * 4))
    except Exception:
        return numpy.zeros(0, dtype=numpy.int16)
    return numpy.frombuffer(p.stdout, dtype=numpy.int16)


def _ffmpeg_until_key_up(name, is_key_up, timeout, chunk=0.5):
    """Accumulate capped DirectShow captures until `is_key_up()` says released.

    A single dshow stream EOFs after ~0.1s, so continuous capture is a loop of
    short ffmpeg runs; the key check between chunks is what honors
    'listen only while I'm holding the key' (release caught within ~0.5s)."""
    parts = []
    total = 0
    t0 = time.time()
    while True:
        if is_key_up():
            break
        left = timeout - (time.time() - t0)
        if left <= 0:
            break
        raw = _ffmpeg_chunk(name, min(chunk, left))
        if raw.size == 0:
            break
        parts.append(raw)
        total += raw.size
    if not parts:
        return numpy.zeros(0, dtype=numpy.float32), 0.0
    cat = numpy.concatenate(parts)
    return cat.astype(numpy.float32) / 32768.0, total / float(SAMPLERATE)


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


def _sd_until_key_up(is_key_up, timeout, dev):
    frames = []

    def collect(data, _frames, _t, _status):
        frames.append(numpy.frombuffer(data, dtype=numpy.int16))

    t0 = time.time()
    duration = 0.0
    with sounddevice.RawInputStream(
        samplerate=SAMPLERATE, blocksize=1600, device=dev,
        dtype="int16", channels=1, callback=collect,
    ):
        while not is_key_up():
            if time.time() - t0 > timeout:
                break
            duration = time.time() - t0
        deadline = time.time() + 0.25
        while time.time() < deadline:
            time.sleep(0.01)
    return _to_float(frames), duration


def record_fixed(seconds, samplerate=SAMPLERATE, device=None):
    mode, val = _resolve(device)
    if mode == "dshow":
        raw = _ffmpeg_chunk(val, seconds)
        return raw.astype(numpy.float32) / 32768.0
    return _sd_fixed(seconds, samplerate, val)


def record_until_key_up(is_key_up, timeout=600, device=None):
    mode, val = _resolve(device)
    if mode == "dshow":
        return _ffmpeg_until_key_up(val, is_key_up, timeout)
    return _sd_until_key_up(is_key_up, timeout, val)


def _to_float(frames):
    if not frames:
        return numpy.zeros(0, dtype=numpy.float32)
    raw = numpy.frombuffer(b"".join(frames), dtype=numpy.int16)
    return raw.astype(numpy.float32) / 32768.0


def peak(audio):
    if audio is None or len(audio) == 0:
        return 0.0
    return float(numpy.abs(audio).max())
