import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULTS = {
    "trigger_key": "f9",
    "output_mode": "autotype",
    "engine": "whisper",
    "whisper_model": "base",
    "hf_model": "nvidia/canary-180m-flash",
    "language": None,
    "commands": [],
    # Microphone source: "" = auto-pick, "ds:<name>" = Windows/DirectShow source
    # (the real mic list), "sd:<idx>" = PortAudio input index.
    "input_device": "",
}


def load():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            stored = json.load(f)
        cfg.update(stored)
    return cfg


def save(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
