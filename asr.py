import os

import config as config_mod

import numpy

_CACHE = {}


def _threads():
    """Use every core: ctranslate2 defaults to 2 threads, which crawls on a 16-core CPU."""
    return max(1, os.cpu_count() or 1)


def transcribe(audio, cfg):
    """Transcribe float32 audio (16 kHz). Dispatches on cfg["engine"]."""
    gpu = bool(cfg.get("gpu", False))
    if cfg.get("engine", "whisper") == "whisper":
        return _whisper(audio, cfg.get("whisper_model", "base"), cfg.get("language"), gpu)
    model_id = cfg.get("hf_model") or config_mod.DEFAULTS["hf_model"]
    return _hf_transformers(audio, model_id, gpu)


def _whisper(audio, size, language, gpu=False):
    key = ("fw", size, gpu)
    model = _CACHE.get(key)
    if model is None:
        from faster_whisper import WhisperModel

        if gpu:
            try:
                model = WhisperModel(size, device="cuda", compute_type="int8_float16")
            except Exception:
                model = WhisperModel(size, device="cpu", compute_type="int8",
                                     cpu_threads=_threads())
                _CACHE[("fw", size, False)] = model
                _CACHE.pop(key, None)
                key = ("fw", size, False)
        else:
            model = WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=_threads())
        _CACHE[key] = model
    segments, _info = model.transcribe(
        audio,
        language=language or None,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


def _hf_transformers(audio, model_id, gpu=False):
    """Canary / Parakeet / custom HF models through the transformers ASR
    pipeline. The model must have an HF-native config (model_type); repos that
    ship only a NeMo checkpoint (.nemo) cannot be loaded this way - the preset
    list avoids those, and this raises a clear message for anything else."""
    key = ("hf", model_id, gpu)
    pipe = _CACHE.get(key)
    if pipe is None:
        from transformers import pipeline
        import torch

        torch.set_num_threads(_threads())
        dev = 0 if gpu and torch.cuda.is_available() else -1
        try:
            pipe = pipeline("automatic-speech-recognition", model=model_id, device=dev)
        except Exception as e:
            raise OSError(
                "%s cannot be loaded as a transformers ASR model: %s "
                "(models that only ship a .nemo checkpoint are not supported here)" % (model_id, e)
            )
        _CACHE[("hf", model_id, dev == 0)] = pipe
    return _run_hf(pipe, audio)


def _run_hf(pipe, audio):
    out = pipe({"raw": audio, "sampling_rate": 16000})
    return (out["text"] if isinstance(out, dict) else out).strip()


class LiveSession:
    """Progressive live typing for engines without a native streaming API (none
    of the ones here have one). While the user speaks, feed() re-transcribes
    the growing audio every STEP seconds; the FIRST hypothesis commits
    immediately (minus the one word in flight), so typing starts within about
    a second of speech, and later growth only extends text at least two
    consecutive hypotheses read the same way - nothing typed is ever
    retracted. Works with every engine: fast models (Whisper) keep pace with
    speech, big ones lag behind and catch up when finish() runs at release.
    If a hypothesis rewrites already-committed text, growth stalls and the
    final flush types the remainder (and says so).

    feed(chunk) returns text newly safe to type ("" most calls);
    finish() flushes the rest."""

    SR = 16000
    STEP = 1.0            # seconds of new speech between hypothesis passes
    WINDOW_MAX = 45.0     # re-transcribe at most this many seconds (cap cost)
    SAFETY_WORDS = 1      # only the word in flight is held back

    def __init__(self, cfg):
        self.cfg = cfg
        self.chunks = []
        self.head = 0      # frames dropped from the front of the window
        self.total = 0     # frames fed so far
        self.pend = 0.0    # frames fed since the last pass
        self.prev = ""     # last hypothesis
        self.committed = ""
        self.last_error = None

    def feed(self, audio):
        if audio is None or len(audio) == 0:
            return ""
        self.chunks.append(numpy.asarray(audio, dtype=numpy.float32))
        self.total += len(audio)
        self.pend += len(audio)
        if self.pend < self.STEP * self.SR:
            return ""
        return self._pass()

    def finish(self):
        return self._pass(final=True)

    def _pass(self, final=False):
        self.pend = 0.0
        window = self._window()
        if window.size == 0:
            return ""
        try:
            h = transcribe(window, self.cfg).strip()
        except Exception as e:
            self.last_error = str(e)  # the FIRST pass is where a bad engine
            return ""                # config fails here, not at startup: keep
                                     # it for the caller so the user gets told
        if final:
            if h.startswith(self.committed):
                new = h[len(self.committed):]
                self.committed = h
                return new
            # trimmed window or rewritten hypothesis: type what h adds past
            # the words it shares with what is already committed
            tail = self._tail_after_overlap(h)
            if tail:
                self.committed = (self.committed + " " + tail).strip()
            return tail
        # the first pass commits its own head right away (minus the word in
        # flight) so typing starts the moment speech starts; later growth still
        # needs agreement with the previous hypothesis, so nothing typed is
        # ever retracted - only words at least two consecutive passes read the
        # same way extend the committed text
        cand = self._safe_prefix(self.prev or h, h)
        self.prev = h
        if len(cand) <= len(self.committed) or not cand.startswith(self.committed):
            return ""  # cannot untype: hold off until passes agree again
        new = cand[len(self.committed):]
        self.committed = cand
        return new

    def _window(self):
        if not self.chunks:
            return numpy.zeros(0, dtype=numpy.float32)
        cat = numpy.concatenate(self.chunks)
        cap = int(self.WINDOW_MAX * self.SR)
        skip = max(self.head, cat.size - cap)
        if skip:
            cat = cat[skip:]
        self.head = skip
        # storage follows the window: drop chunks fully before it, or a long
        # dictation keeps every frame and every pass costs the whole session
        while len(self.chunks) > 1 and len(self.chunks[0]) <= self.head:
            self.head -= len(self.chunks.pop(0))
        return cat

    def _safe_prefix(self, prev, h):
        """Longest word-aligned prefix prev and h agree on, minus SAFETY_WORDS."""
        n = min(len(prev), len(h))
        i = 0
        while i < n and prev[i] == h[i]:
            i += 1
        lcp = h[:i]
        sp = lcp.rfind(" ")
        if sp < 0:
            return ""
        words = lcp[:sp].split()
        if len(words) <= self.SAFETY_WORDS:
            return ""
        return " ".join(words[:-self.SAFETY_WORDS])

    def _tail_after_overlap(self, h):
        """Words of h past whatever h and the committed text end/start sharing
        (a trimmed window repeats a few of the last words as context)."""
        cw = self.committed.split()
        hw = h.split()
        for t in range(min(len(cw), len(hw)), -1, -1):
            if cw[len(cw) - t:] == hw[:t]:
                return " ".join(hw[t:]).strip()
        return ""


