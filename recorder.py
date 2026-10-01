import time

import numpy
import sounddevice

SAMPLERATE = 16000


def record_fixed(seconds, samplerate=SAMPLERATE):
    frames = []

    def collect(_ptr, size, buf):
        frames.append(buf[:size].copy())

    with sounddevice.RawInputStream(
        samplerate=samplerate, blocksize=1600, device=None, dtype="int16", channels=1, callback=collect
    ):
        time.sleep(seconds)
    return _to_float(frames)


def record_until_key_up(is_key_up, timeout=600):
    frames = []

    def collect(_ptr, size, buf):
        frames.append(buf[:size].copy())

    t0 = time.time()
    duration = 0.0
    with sounddevice.RawInputStream(
        samplerate=SAMPLERATE, blocksize=1600, device=None, dtype="int16", channels=1, callback=collect
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
