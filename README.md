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
| Hold-to-talk | any F-key / Ctrl / Alt / Shift / letter / digit, configurable in the settings UI — or click "Detect my key" and physically press the shortcut you want (default `F9`) |
| Microphone | `sounddevice` (16 kHz) |
| Output | types into the focused window (Windows Script Host `SendKeys` via `cscript.exe`) or copies to the clipboard — configurable |
| Settings | web page served on `http://127.0.0.1:47111` — reachable **only from this machine** (no other LAN user can open it, so no password is needed), saved to `config.json` |

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

- **Right-click the tray icon** → menu: Open settings / **Model manager** / Pause
  listening / Resume listening / Test microphone / Quit. "Open settings" and
  "Model manager" just open the relevant page in your browser and return
  immediately — the tray menu keeps working while the page is open, and closing
  the browser tab is all it takes to be done.
- While the app is running, you can also open the settings page directly in your
  browser at `http://127.0.0.1:47111` (typing `127.0.0.1` **without** that port
  hits port 80, not the app — that shows "didn't send any data").
- To run just the settings page (debugging): `python app.py --settings` — it
  prints the URL; press Ctrl+Q in the terminal to quit.
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

## Settings (web page)

The settings page is opened from the tray menu (or `python app.py --settings`),
or — while the app is running — by typing `http://127.0.0.1:47111` in your
browser. It is served on `127.0.0.1`, so only this machine can view it
— no username/password needed. Press **Save settings** to write `config.json`
(a running app picks the changes up immediately); when you are done, just close
the tab — the page stays available for the whole time the app runs.

- **Trigger key** — pick from the dropdown (F1–F12, Ctrl, Alt, Shift, Win, letter/digit),
  or press **Detect my key** and then physically hold **any number of keys together**
  for a moment (a single key, a combination like `Ctrl + F9`, or as many keys as you
  like): the exact keys you are holding are captured and used as your trigger
  combination. Prefer F-keys: holding a letter or digit also types repeated characters
  into your document.
  You can also choose a **combination** (e.g. `Ctrl + F9` or `Win + Ctrl`) — pick one
  from the dropdown, or **type your own combination of any number of keys** in the
  "Or type your own combination" box (keys joined with `+`): the listener starts
  recording only when *all* parts are physically held at once, and stops when any
  one is released.
- **Microphone** — choose which input the recorder uses. The "(default / auto-detect)"
  entry lets `sounddevice` pick; if you have several inputs (or the auto pick records
  silence), select a specific one from the dropdown. If the list shows only "(default /
  auto-detect)", this machine exposes no microphone input through the app's audio
  backend - use an actual microphone (Windows permission allowed) or a headset mic.
- **Engine** — model options shown change automatically to match the engine you
  select:
  - `OpenAI Whisper (faster-whisper)` — fast on CPU; shows a model-size dropdown:
    `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo`
    (accuracy vs speed/RAM; `base` is a good start, `small` is noticeably
    better).
  - `NVIDIA Canary` — multilingual; shows Canary presets: 180M Flash (EN/ES,
    fastest), 1B v2 (25 languages), **Canary Qwen 2.5B** (best quality, but
    heavy on CPU — several GB of RAM, slow).
  - `NVIDIA Parakeet` — very accurate English ASR (TDT 0.6B v3 also covers
    26 languages); shows Parakeet presets. CPU-friendly.
  - `Custom model` — shows a free-text field for any Hugging Face ASR model ID.
- **Language** — auto-detect by default; pick explicitly for better accuracy.
- **Output mode** — type into the focused window, or copy to clipboard.
- **Voice shortcuts** — "say this → insert that" rows (e.g. `insert email` →
  your email): press "Add voice shortcut", type both sides in the boxes,
  "Remove" deletes a row.
- **Test microphone** — records 4 s and shows what was recognized (useful for
  debugging mic/engine setup).
- **Live status** — the settings page also shows, in real time, where the hold-to-talk
  pipeline currently is (idle / recording / transcribing / "nothing recognized" /
  "too short"). If a cycle produces no text, look at this line to see where it stopped.

A separate **Models** page lives at `http://127.0.0.1:47111/models.html`: it lists every
model (Whisper sizes, Canary, Parakeet presets) plus anything else physically present in
the HF cache, with installed/present status and size, and lets you **Download** (pre-fetch
a model, needs internet once) or **Delete** it. Models already present are used offline.

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
