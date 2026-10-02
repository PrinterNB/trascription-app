import os

_CACHE = {}


def _threads():
    """Use every core: ctranslate2 defaults to 2 threads, which crawls on a 16-core CPU."""
    return max(1, os.cpu_count() or 1)


def transcribe(audio, cfg):
    """Transcribe float32 audio (16 kHz). Dispatches on cfg["engine"]."""
    gpu = bool(cfg.get("gpu", False))
    if cfg.get("engine", "whisper") == "whisper":
        return _whisper(audio, cfg.get("whisper_model", "base"), cfg.get("language"), gpu)
    model_id = cfg.get("hf_model") or "nvidia/canary-180m-flash"
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
    key = ("hf", model_id, gpu)
    pipe = _CACHE.get(key)
    if pipe is None:
        from transformers import pipeline
        import torch

        torch.set_num_threads(_threads())
        try:
            pipe = pipeline(
                "automatic-speech-recognition",
                model=model_id,
                trust_remote_code=True,
                device=0 if gpu else -1,
            )
        except Exception:
            # Some model families are not registered for the ASR pipeline; use their
            # custom transformers classes directly.
            if gpu:
                import torch as _t

                if not _t.cuda.is_available():
                    pipe = _manual_hf(model_id)
                    _CACHE[("hf", model_id, False)] = pipe
                    return _run_hf(pipe, audio)
            pipe = _manual_hf(model_id)
        _CACHE[key] = pipe
    return _run_hf(pipe, audio)


def _run_hf(pipe, audio):
    out = pipe({"raw": audio, "sampling_rate": 16000})
    return (out["text"] if isinstance(out, dict) else out).strip()


def _manual_hf(model_id):
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

    def _call(audio):
        model = AutoModelForSpeechSeq2Seq.from_pretrained(model_id, trust_remote_code=True)
        processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

        def run(audio):
            inputs = processor({"raw": audio, "sampling_rate": 16000}, return_tensors="pt")
            generated = model.generate(**inputs)
            try:
                return processor.batch_decode(generated, skip_special_tokens=True)[0]
            except Exception:
                return processor.batch_decode(
                    generated,
                    target_len=generated.shape[-1],
                    skip_special_tokens=True,
                )[0]

        return run

    return _call
