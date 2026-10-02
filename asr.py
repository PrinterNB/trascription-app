import os

import config as config_mod

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


