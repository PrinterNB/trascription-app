import tkinter as tk
from tkinter import ttk, messagebox

import config as config_mod
import recorder
import asr

ENGINE_LABELS = {
    "whisper": "OpenAI Whisper (faster-whisper) - fast on CPU",
    "canary": "NVIDIA Canary (multilingual)",
    "parakeet": "NVIDIA Parakeet (English, very accurate)",
    "custom": "Custom model (Hugging Face ID)",
}
ENGINE_BY_LABEL = {label: engine for engine, label in ENGINE_LABELS.items()}

WHISPER_SIZES = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]

PRESET_MODELS = {
    "nvidia/canary-180m-flash": "Canary 180M Flash (EN/ES, fastest)",
    "nvidia/canary-1b-v2": "Canary 1B v2 (25 languages)",
    "nvidia/canary-qwen-2.5b": "Canary Qwen 2.5B (best quality, heavy on CPU)",
    "nvidia/parakeet-tdt-0.6b-v3": "Parakeet TDT 0.6B v3 (26 languages)",
    "nvidia/parakeet-ctc-1.1b": "Parakeet CTC 1.1B (English)",
    "nvidia/parakeet-rnnt-1.1b": "Parakeet RNNT 1.1B (English)",
}

LANGUAGES = [
    ("", "(auto-detect)"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("ru", "Russian"),
    ("tr", "Turkish"),
    ("ar", "Arabic"),
    ("hi", "Hindi"),
    ("zh", "Chinese"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
]
LANG_BY_LABEL = {label: code for code, label in LANGUAGES}

OUTPUT_MODES = [("autotype", "Type into focused window"), ("clipboard", "Copy to clipboard")]
MODE_BY_LABEL = {label: mode for mode, label in OUTPUT_MODES}

TRIGGER_KEYS = [f"f{i}" for i in range(1, 13)] + ["ctrl", "alt", "shift"]
TRIGGER_KEYS += [chr(c) for c in range(ord("a"), ord("z") + 1)]
TRIGGER_KEYS += [str(d) for d in range(10)]


def _default_label(pairs, value):
    for v, label in pairs:
        if v == value:
            return label
    return pairs[0][1]


def open_settings(cfg):
    root = tk.Tk()
    root.title("Voice Dictation - settings")
    frm = ttk.Frame(root)
    frm.pack(fill="both", expand=True)

    field_list = []

    def add_field(title, values, default):
        sv = tk.StringVar(value=default)
        widget = tk.OptionMenu(sv, *values)
        col = len(field_list) * 2
        ttk.Label(frm, text=title).grid(row=0, column=col, sticky="nw")
        widget.grid(row=1, column=col, sticky="nw")
        field_list.append((title, sv))
        return sv

    key_sv = add_field("Hold-to-talk key:", TRIGGER_KEYS, cfg.get("trigger_key", "f9"))
    out_sv = add_field("Output mode:", [lbl for _, lbl in OUTPUT_MODES], _default_label(OUTPUT_MODES, cfg.get("output_mode", "autotype")))
    engine_sv = add_field("Transcription engine:", list(ENGINE_LABELS.values()), ENGINE_LABELS.get(cfg.get("engine", "whisper"), ENGINE_LABELS["whisper"]))
    size_sv = add_field("Whisper model size:", WHISPER_SIZES, cfg.get("whisper_model", "base"))
    model_sv = add_field("Canary/Parakeet preset:", list(PRESET_MODELS), cfg.get("hf_model", "nvidia/canary-180m-flash"))
    lang_sv = add_field("Language:", [lbl for _, lbl in LANGUAGES], _default_label(LANGUAGES, cfg.get("language") or ""))

    ttk.Label(frm, text="Custom model ID (optional, overrides the preset):").grid(row=2, column=0, sticky="nw")
    custom_e = ttk.Entry(frm)
    custom_e.grid(row=2, column=1, sticky="nw")

    ttk.Label(
        frm,
        text="Notes: prefer F-keys / Ctrl / Alt / Shift as the trigger key (holding a letter or digit key "
        "also types repeated characters). For the dictation output, first mouse-click into the text field "
        "you want to dictate into.",
        wraplength=620,
    ).grid(row=3, column=0, columnspan=13, sticky="nw")

    ttk.Label(frm, text="Voice shortcuts (say this, insert that):").grid(row=4, column=0, sticky="nw")
    rows = []

    def new_row():
        frame = ttk.Frame(frm)
        say = ttk.Entry(frame)
        ins = ttk.Entry(frame)
        col = (len(rows) + 1) * 2
        frame.grid(row=5, column=col, sticky="nw")
        say.grid(row=0, column=0, sticky="nw")
        ttk.Label(frame, text="->").grid(row=0, column=1, sticky="nw")
        ins.grid(row=0, column=2, sticky="nw")
        ttk.Button(frame, text="Remove", command=lambda: remove_row(frame)).grid(row=1, column=0)
        rows.append((frame, say, ins))

    def remove_row(frame):
        for i, entry in enumerate(rows):
            if entry[0] is frame:
                rows.pop(i)
                frame.destroy()
                return

    ttk.Button(frm, text="Add voice shortcut", command=new_row).grid(row=5, column=0, sticky="nw")

    for cmd in cfg.get("commands", []):
        new_row()
        rows[-1][1].insert("end", cmd.get("say", ""))
        rows[-1][2].insert("end", cmd.get("insert", ""))

    def gather():
        new = dict(config_mod.DEFAULTS)
        new["trigger_key"] = key_sv.get()
        new["output_mode"] = MODE_BY_LABEL[out_sv.get()]
        new["engine"] = ENGINE_BY_LABEL[engine_sv.get()]
        new["whisper_model"] = size_sv.get()
        new["hf_model"] = custom_e.get().strip() or model_sv.get()
        new["language"] = LANG_BY_LABEL[lang_sv.get()] or None
        new["commands"] = [
            {"say": say.get(), "insert": ins.get()} for _, say, ins in rows if say.get()
        ]
        cfg.clear()
        cfg.update(new)

    def do_save():
        gather()
        config_mod.save(cfg)
        messagebox.showinfo("Voice Dictation", "Settings saved. The running app picks them up immediately.")

    def do_test():
        gather()
        try:
            audio = recorder.record_fixed(4)
            text = asr.transcribe(audio, cfg)
            messagebox.showinfo("Voice Dictation test", ("Heard: " + text) if text else "Nothing recognized.")
        except Exception as e:
            messagebox.showerror("Voice Dictation test", str(e))

    ttk.Button(frm, text="Save settings", command=do_save).grid(row=6, column=0, sticky="nw")
    ttk.Button(frm, text="Test microphone (4s)", command=do_test).grid(row=6, column=1, sticky="nw")

    root.mainloop()


if __name__ == "__main__":
    open_settings(config_mod.load())
