_CACHE = {}


def transcribe(audio, cfg):
    """Transcribe float32 audio (16 kHz). Dispatches on cfg["engine"]."""
    if cfg.get("engine", "whisper") == "whisper":
        return _whisper(audio, cfg.get("whisper_model", "base"), cfg.get("language"))
    model_id = cfg.get("hf_model") or "nvidia/canary-180m-flash"
    return _hf_transformers(audio, model_id)


def _whisper(audio, size, language):
    key = ("fw", size)
    if key not in _CACHE:
        from faster_whisper import WhisperModel

        _CACHE[key] = WhisperModel(size, device="cpu", compute_type="int8")
    model = _CACHE[key]
    segments, _info = model.transcribe(
        audio,
        language=language or None,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


def _hf_transformers(audio, model_id):
    key = ("hf", model_id)
    pipe = _CACHE.get(key)
    if pipe is None:
        from transformers import pipeline

        try:
            pipe = pipeline(
                "automatic-speech-recognition",
                model=model_id,
                trust_remote_code=True,
                device=-1,
            )
        except Exception:
            # Some model families are not registered for the ASR pipeline; use their
            # custom transformers classes directly.
            pipe = _manual_hf(model_id)
        _CACHE[key] = pipe
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
