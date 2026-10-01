import time

import numpy
import sounddevice

SAMPLERATE = 16000


def _pick_device():
    """Return an index for a usable microphone input, or None for the default.

    sounddevice's default is usually right, but with several input devices
    present it can pick one that captures silence; prefer anything named like a
    microphone, else the first real input device."""
    try:
        devs = sounddevice.query_devices()
    except Exception:
        return None
    inputs = []
    for i, d in enumerate(devs):
        try:
            if str(d.get("type", "")).upper().startswith("INPUT") and d.get("channels", 0) > 0:
                inputs.append(i)
        except Exception:
            continue
    for i in inputs:
        name = str(devs[i].get("name", "")).lower()
        if "mic" in name or "audio in" in name or "microphone" in name:
            return i
    return inputs[0] if inputs else None


_DEVICE = _pick_device()


def record_fixed(seconds, samplerate=SAMPLERATE, device=None):
    dev = device if device is not None else _DEVICE
    frames = []

    def collect(_ptr, size, buf):
        frames.append(buf[:size].copy())

    with sounddevice.RawInputStream(
        samplerate=samplerate, blocksize=1600, device=dev, dtype="int16", channels=1, callback=collect
    ):
        time.sleep(seconds)
    return _to_float(frames)


def record_until_key_up(is_key_up, timeout=600, device=None):
    dev = device if device is not None else _DEVICE
    frames = []

    def collect(_ptr, size, buf):
        frames.append(buf[:size].copy())

    t0 = time.time()
    duration = 0.0
    with sounddevice.RawInputStream(
        samplerate=samplerate, blocksize=1600, device=dev, dtype="int16", channels=1, callback=collect
    ):
        while not is_key_up():
            if time.time() - t0 > timeout:
                break
            duration = time.time() - t0
        deadline = time.time() + 0.25
        while time.time() < deadline:
            time.sleep(0.01)
    return _to_float(frames), duration


def _to_float(frames):
    if not frames:
        return numpy.zeros(0, dtype=numpy.float32)
    raw = numpy.frombuffer(b"".join(frames), dtype=numpy.int16)
    return raw.astype(numpy.float32) / 32768.0


def peak(audio):
    """Loudest signal in a float32 buffer (0..1); ~0 means the mic heard nothing."""
    if audio is None or len(audio) == 0:
        return 0.0
    return float(numpy.abs(audio).max())
