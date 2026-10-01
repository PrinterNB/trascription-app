# Voice Dictation — hold-to-talk speech-to-text for Windows

100% local speech-to-text. No cloud, no GPU — everything runs on your CPU and RAM.

You mouse-click into a text field, hold a key while you talk, release it, and the
transcription is typed into that window. Say a configured shortcut phrase like
"insert email" and your email (or credit card number, address…) is inserted instead.

## How it works

| Part | Implementation |
| --- | --- |
| Speech recognition | [faster-whisper](https://github.com/DeepInsider/faster-whisper) (OpenAI Whisper, CTranslate2, CPU int8) — plus NVIDIA Canary and NVIDIA Parakeet as alternative engines |
| Tray icon | `pystray` — the app lives in your system tray, no terminal window |
| Hold-to-talk | any F-key / Ctrl / Alt / Shift / letter / digit, configurable in the UI (default `F9`) |
| Microphone | `sounddevice` (16 kHz) |
| Output | types into the focused window (Windows Script Host `SendKeys` via `cscript.exe`) or copies to the clipboard — configurable |
| Settings | Tk settings window saved to `config.json` |

## Setup

Double-click **`install.bat`** — it creates the virtual environment, installs the
core and optional (Canary/Parakeet) dependencies, and generates the tray icon.

Or step by step:

```bat
:: run from this repository's folder
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
:: optional, only if you want the Canary/Parakeet engines:
pip install -r requirements-optional.txt
```

## Run

Double-click **`VoiceDictation.bat`** — the installer creates it next to
`install.bat` and it launches the app windowless: the icon appears in your system
tray. Copy `VoiceDictation.bat` to your Desktop, a folder, or a USB stick — it
stores absolute paths, so a copy works from anywhere.

- **Right-click the tray icon** → menu: Open settings / Pause listening / Resume
  listening / Test microphone / Quit.
- To open just the settings window: `python app.py --settings`
- Status colors: gray = idle, **red = listening to you**, amber = transcribing,
  back to gray when the text was inserted.
- Debugging: run `.venv\Scripts\python.exe app.py` in a terminal to see errors.

## Using it

1. Mouse-click into the textbox you want to dictate into (Word, an email draft,
   any app) so it has keyboard focus.
2. Press and **hold** your trigger key (default F9) and talk.
3. **Release** it. The text — with your voice shortcuts already replaced — is
   typed into that window.

Speak the shortcut phrases you configured, e.g. "insert email" or "insert card
number" — they are matched in the transcript (case-insensitive) and replaced with
whatever you set.

## Settings (in the Tk settings window)

- **Trigger key** — F1–F12, Ctrl, Alt, Shift, or a letter/digit. Prefer F-keys:
  holding a letter key also types repeated characters into your document.
- **Engine** —
  - `OpenAI Whisper (faster-whisper)` — fast on CPU. Model size is a separate
    dropdown: `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo`
    (accuracy vs speed/RAM; `base` is a good start, `small` is noticeably
    better).
  - `NVIDIA Canary` — multilingual; presets: Canary 180M Flash (EN/ES, fastest),
    Canary 1B v2 (25 languages), **Canary Qwen 2.5B** (best quality, but heavy
    on CPU — several GB of RAM, slow).
  - `NVIDIA Parakeet` — very accurate English ASR (TDT 0.6B v3 also covers
    26 languages). CPU-friendly.
  - `Custom model` — any Hugging Face ASR model ID.
- **Language** — auto-detect by default; pick explicitly for better accuracy.
- **Output mode** — type into the focused window, or copy to clipboard.
- **Voice shortcuts** — "say this → insert that" rows (e.g. `insert email` →
  your email).
- **Test microphone** — records 4 s and shows what was recognized (useful for
  debugging mic/engine setup).

Models are downloaded once from Hugging Face/CT2 on first use and cached
(`~/.cache`). After that, inference is fully offline.

## Troubleshooting

- **Tray icon missing after a few seconds** — Windows 11 hides third-party tray
  icons by default; use TopBar/Barrel/ExplorerCoreFix, or just run the app as a
  window (`python app.py`).
- **Nothing typed into your app** — output mode "type into focused window" needs
  the target window to have keyboard focus: click into it first, right next to
  where you want the text. Alternatively set output mode to clipboard and paste
  with Ctrl+Ctrl+C.
- **Text arrives but is wrong/garbled** — switch engine/size in the settings UI.
- Errors are appended to `errors.log` next to this README.
- `config.json` is plain text — it stores your email/card number; keep the folder
  private.
- Canary Qwen 2.5B and `large-v3` need a lot of RAM; stay on `base`/`small` or
  the smaller models if your machine is modest.
- Parakeet CTC/RNNT presets are English-only; use TDT 0.6B v3 or Whisper for
  other languages.
