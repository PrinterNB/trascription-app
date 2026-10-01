"""Settings UI served as a web page on 127.0.0.1 only (stdlib http.server).

A random high port plus the 127.0.0.1 address means no other machine on your
network can open it, so no password is needed. The settings are still saved
to config.json, and a save is pushed into the running app immediately."""

import ctypes
import json
import os
import random
import threading
import time

from http.server import BaseHTTPRequestHandler, HTTPServer

import webbrowser

import config as config_mod
import recorder
import asr

# Virtual key codes for polling key state (single source of truth; app.py imports this).
KEY_VK = {f"f{i}": 0x70 + i - 1 for i in range(1, 13)}
KEY_VK.update({"ctrl": 0x11, "alt": 0x12, "shift": 0x10})
for _c in range(ord("a"), ord("z") + 1):
    KEY_VK[chr(_c)] = _c - 32
for _d in range(10):
    KEY_VK[str(_d)] = ord(str(_d))

TRIGGER_KEYS = [f"f{i}" for i in range(1, 13)] + ["ctrl", "alt", "shift"]
TRIGGER_KEYS += [chr(c) for c in range(ord("a"), ord("z") + 1)]
TRIGGER_KEYS += [str(d) for d in range(10)]


def _key_label(name):
    if name in ("ctrl", "alt", "shift"):
        return name.capitalize()
    return name.upper()


ENGINE_ORDER = ["whisper", "canary", "parakeet", "custom"]
ENGINE_LABELS = {
    "whisper": "OpenAI Whisper (faster-whisper) - fast on CPU",
    "canary": "NVIDIA Canary - multilingual",
    "parakeet": "NVIDIA Parakeet - very accurate English ASR",
    "custom": "Custom model - any Hugging Face ASR model ID",
}

WHISPER_SIZES = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]
WHISPER_SIZE_LABELS = {
    "tiny": "tiny - fastest, least accurate",
    "base": "base - good default",
    "small": "small - better, slower",
    "medium": "medium - slow",
    "large-v3": "large-v3 - best Whisper accuracy, heavy",
    "large-v3-turbo": "large-v3-turbo - fast but large",
}

CANARY_MODELS = [
    ("nvidia/canary-180m-flash", "Canary 180M Flash - English/Spanish, fastest"),
    ("nvidia/canary-1b-v2", "Canary 1B v2 - 25 languages"),
    ("nvidia/canary-qwen-2.5b", "Canary Qwen 2.5B - best quality, heavy (several GB RAM)"),
]
PARAKEET_MODELS = [
    ("nvidia/parakeet-tdt-0.6b-v3", "Parakeet TDT 0.6B v3 - 26 languages"),
    ("nvidia/parakeet-ctc-1.1b", "Parakeet CTC 1.1B - English"),
    ("nvidia/parakeet-rnnt-1.1b", "Parakeet RNNT 1.1B - English"),
]

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

OUTPUT_MODES = [
    ("autotype", "Type into focused window"),
    ("clipboard", "Copy to clipboard"),
]


def detect_key(timeout):
    """Poll every candidate key until one is physically held (twice in a row)."""
    start = time.time()
    while time.time() - start < timeout:
        for name in TRIGGER_KEYS:
            vk = KEY_VK[name]
            if ctypes.windll.user32.GetKeyState(vk) & 0x8000:
                time.sleep(0.1)
                if ctypes.windll.user32.GetKeyState(vk) & 0x8000:
                    return name
        time.sleep(0.02)
    return None


def _page_data():
    return {
        "keys": [[k, _key_label(k)] for k in TRIGGER_KEYS],
        "engines": [[e, ENGINE_LABELS[e]] for e in ENGINE_ORDER],
        "whisper_sizes": [[s, WHISPER_SIZE_LABELS[s]] for s in WHISPER_SIZES],
        "canary": [[m, label] for m, label in CANARY_MODELS],
        "parakeet": [[m, label] for m, label in PARAKEET_MODELS],
        "languages": [[c, label] for c, label in LANGUAGES],
        "outputs": [[m, label] for m, label in OUTPUT_MODES],
    }


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Voice Dictation settings</title>
<style>
body{font-family:"Segoe UI",system-ui,sans-serif;background:#f6f7f8;color:#20242a;
     max-width:820px;margin:14px auto;padding:10px 16px;}
h1{font-size:1.3rem;}
.note{font-size:.85rem;color:#4a525c;}
#msg{position:sticky;top:10px;background:#17324f;color:#eef3f8;padding:9px 12px;
     border-radius:6px;font-weight:600;}
.row{display:flex;align-items:center;gap:8px;margin:8px 0;}
.lbl{font-weight:600;min-width:180px;}
select,textarea{font:inherit;}
select{min-width:120px;}
.ce{border:1px solid #8a94a0;border-radius:4px;padding:3px 8px;background:#fff;min-width:110px;}
textarea.ce{min-width:220px;white-space:pre-wrap;}
.cmdrow{display:flex;align-items:center;gap:8px;margin:8px 0;}
.btns{margin-top:22px;text-align:center;}
.btns button{margin:0 10px;}
</style>
</head>
<body>
<script>window.__INIT__ = __INIT_JSON__;</script>
<h1>Voice Dictation settings</h1>
<div class="note">This page is served only to this machine (127.0.0.1) - nobody
on your network can open it, so no password is needed. Settings are saved to
<code>config.json</code> in the app folder; the running app uses them right away.</div>
<div id="msg">Ready. Edit anything below, then press "Save settings". Press
"Done - close settings" when you are finished.</div>
<form id="f"></form>
<div class="btns">
<button id="btn-detect">Detect my key</button>
<button id="btn-save">Save settings</button>
<button id="btn-test">Test microphone (4 s)</button>
<button id="btn-close">Done - close settings</button>
</div>
<div class="note">"Detect my key": click the button, then physically hold the shortcut you
want for a moment - it is captured automatically. Prefer F-keys / Ctrl / Alt / Shift:
holding a letter or digit also types repeated characters in your document.</div>
<script>
var D = window.__INIT__.data;
var st = window.__INIT__.cfg;
st.language = typeof st.language === 'string' ? st.language : '';
st.cmds = (st.commands || []).map(function (o) {
  return { say: o.say || '', insert: o.insert || '' };
});
var f = document.getElementById('f');
var msgEl = document.getElementById('msg');

function setMsg(t) { msgEl.textContent = t; }

function post(path, obj, fn) {
  fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(obj)})
    .then(function (r) { return r.json(); })
    .then(fn)
    .catch(function (e) {
      setMsg('Could not reach the settings server (' + e +
        '). If you pressed "Done" earlier, reopen settings from the tray menu instead.');
    });
}

function keyLabel(k) {
  if (k === 'ctrl') return 'Ctrl';
  if (k === 'alt') return 'Alt';
  if (k === 'shift') return 'Shift';
  return k.toUpperCase();
}

var selKey = null, customEl = null, modelBlock = null;
var cmdRows = [];

function selectField(parent, name, field, opts, onChange) {
  var row = document.createElement('div'); row.className = 'row';
  var lab = document.createElement('span'); lab.className = 'lbl';
  lab.textContent = name;
  var sel = document.createElement('select');
  sel.onchange = function () {
    st[field] = sel.value;
    if (onChange) onChange();
  };
  for (var i = 0; i < opts.length; i++) {
    var o = document.createElement('option');
    o.setAttribute('value', opts[i][0]);
    o.textContent = opts[i][1];
    var cur = (st[field] === null || st[field] === undefined) ? '' : st[field];
    if (opts[i][0] === cur) o.selected = true;
    sel.appendChild(o);
  }
  row.appendChild(lab); row.appendChild(sel); parent.appendChild(row);
  return sel;
}

function fillModel() {
  while (modelBlock.firstChild) modelBlock.removeChild(modelBlock.firstChild);
  customEl = null;
  if (st.engine === 'whisper') {
    selectField(modelBlock, 'Whisper model size:', 'whisper_model',
      D.whisper_sizes, null);
  } else if (st.engine === 'canary') {
    selectField(modelBlock, 'Canary preset:', 'hf_model',
      D.canary, null);
  } else if (st.engine === 'parakeet') {
    selectField(modelBlock, 'Parakeet preset:', 'hf_model',
      D.parakeet, null);
  } else {
    var row = document.createElement('div'); row.className = 'row';
    var lab = document.createElement('span'); lab.className = 'lbl';
    lab.textContent = 'Custom model ID:';
    var ta = document.createElement('textarea');
    ta.rows = 1; ta.className = 'ce';
    ta.value = st.hf_model || '';
    ta.onblur = function () { st.hf_model = ta.value; };
    customEl = ta;
    row.appendChild(lab); row.appendChild(ta); modelBlock.appendChild(row);
  }
}

function cmdRowOf(o) {
  var row = document.createElement('div'); row.className = 'cmdrow';
  var say = document.createElement('span'); say.className = 'ce';
  say.contentEditable = 'true'; say.spellcheck = false;
  say.textContent = o.say;
  say.onblur = function () { o.say = say.textContent; };
  var ins = document.createElement('span'); ins.className = 'ce';
  ins.contentEditable = 'true'; ins.spellcheck = false;
  ins.textContent = o.insert;
  ins.onblur = function () { o.insert = ins.textContent; };
  var arrow = document.createElement('span'); arrow.textContent = '\u2192';
  var rm = document.createElement('button'); rm.textContent = 'Remove';
  rm.onclick = function () {
    var idx = st.cmds.indexOf(o);
    if (idx >= 0) st.cmds.splice(idx, 1);
    for (var k = 0; k < cmdRows.length; k++) {
      if (cmdRows[k] === row) { cmdRows.splice(k, 1); break; }
    }
    row.parentNode.removeChild(row);
  };
  row.appendChild(say); row.appendChild(arrow); row.appendChild(ins); row.appendChild(rm);
  f.appendChild(row);
  cmdRows.push(row);
}

function gather() {
  var c = {};
  c.trigger_key = st.trigger_key;
  c.output_mode = st.output_mode;
  c.engine = st.engine;
  c.whisper_model = st.whisper_model;
  c.hf_model = st.hf_model;
  if (st.engine === 'custom' && customEl && customEl.value.trim()) {
    c.hf_model = customEl.value.trim();
  }
  c.language = st.language || null;
  c.commands = [];
  for (var i = 0; i < st.cmds.length; i++) {
    var o = st.cmds[i];
    if (o.say.trim()) c.commands.push({ say: o.say.trim(), insert: o.insert });
  }
  return c;
}

selKey = selectField(f, 'Hold-to-talk key:', 'trigger_key', D.keys, null);
selectField(f, 'Output mode:', 'output_mode', D.outputs, null);
selectField(f, 'Transcription engine:', 'engine', D.engines, fillModel);
modelBlock = document.createElement('div');
f.appendChild(modelBlock);
fillModel();
selectField(f, 'Language:', 'language', D.languages, null);
var head = document.createElement('h3');
head.textContent = 'Voice shortcuts (say this \u2192 insert that)';
f.appendChild(head);
var addBtn = document.createElement('button');
addBtn.textContent = 'Add voice shortcut';
addBtn.onclick = function () {
  var o = { say: '', insert: '' };
  st.cmds.push(o);
  cmdRowOf(o);
};
f.appendChild(addBtn);
for (var i0 = 0; i0 < st.cmds.length; i0++) cmdRowOf(st.cmds[i0]);

document.getElementById('btn-detect').onclick = function () {
  setMsg('Now physically hold the shortcut key you want (up to 12 seconds)...');
  post('/detect-key', { timeout: 12 }, function (j) {
    if (j.key) {
      st.trigger_key = j.key;
      try { selKey.value = j.key; } catch (err) {}
      setMsg('Detected "' + keyLabel(j.key) + '". Press "Save settings" to use it as your trigger key.');
    } else {
      setMsg('No key was detected - try again.');
    }
  });
};

document.getElementById('btn-save').onclick = function () {
  setMsg('Saving...');
  post('/save', { cfg: gather() }, function (j) {
    setMsg(j.ok ? 'Settings saved - the running app uses them right away.'
                : 'Save failed: ' + (j.error || 'unknown'));
  });
};

document.getElementById('btn-test').onclick = function () {
  setMsg('Recording 4 seconds - speak now, then wait (the first run downloads the model)...');
  post('/test-mic', { cfg: gather() }, function (j) {
    if (j.error) setMsg('Test failed: ' + j.error);
    else setMsg(j.heard ? 'I heard: "' + j.heard + '"'
                : 'Nothing recognized - check your microphone or engine.');
  });
};

document.getElementById('btn-close').onclick = function () {
  post('/close', {}, function (j) {
    setMsg('Settings closed - you may close this tab now. To change settings again, ' +
      'right-click the tray icon and open settings from its menu.');
  });
};
</script>
</body>
</html>
"""

# Fixed local port so the page can be typed into a browser while the app runs
# (127.0.0.1 keeps it unreachable from other machines). Falls back to a random
# port if something else already holds this one (e.g. two app instances).
PREFERRED_PORT = 47111

LIVE_CFG = None
_DONE = {}


def _norm_cfg(raw):
    cfg = dict(config_mod.DEFAULTS)
    cfg.update(raw or {})
    if not cfg.get("language"):
        cfg["language"] = None
    if cfg.get("trigger_key") not in KEY_VK:
        cfg["trigger_key"] = "f9"
    if not cfg.get("hf_model"):
        cfg["hf_model"] = config_mod.DEFAULTS["hf_model"]
    if cfg.get("engine") not in ENGINE_ORDER:
        cfg["engine"] = "whisper"
    if cfg.get("output_mode") not in ("autotype", "clipboard"):
        cfg["output_mode"] = "autotype"
    if cfg.get("whisper_model") not in WHISPER_SIZES:
        cfg["whisper_model"] = "base"
    cmds = []
    for cmd in cfg.get("commands") or []:
        if not isinstance(cmd, dict):
            continue
        say = (cmd.get("say") or "").strip()
        if say:
            cmds.append({"say": say, "insert": cmd.get("insert") or ""})
    cfg["commands"] = cmds
    return cfg


def _log_note(msg):
    path = os.path.join(os.path.dirname(config_mod.CONFIG_PATH), "errors.log")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


class Handler(BaseHTTPRequestHandler):
    def _send_text(self, body):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            init = json.dumps(
                {"cfg": config_mod.load(), "data": _page_data()},
                ensure_ascii=False,
            ).replace("</", "<\\/")
            self._send_text(PAGE.replace("__INIT_JSON__", init))
        elif self.path == "/favicon.ico":
            self._send_text("")
        else:
            self._send_json({"error": "not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            reader = getattr(self, "rfile", None) or self.r
            raw = reader.read(length)
            body = json.loads(raw or b"{}")
        except Exception:
            body = {}
        if self.path == "/save":
            cfg = _norm_cfg(body.get("cfg"))
            config_mod.save(cfg)
            if LIVE_CFG is not None:
                LIVE_CFG.clear()
                LIVE_CFG.update(cfg)
            self._send_json({"ok": True})
        elif self.path == "/detect-key":
            try:
                timeout = min(max(float(body.get("timeout") or 10), 1), 30)
            except (TypeError, ValueError):
                timeout = 10
            key = detect_key(timeout)
            self._send_json(
                {"key": key, "error": None if key else "No key detected - try again."}
            )
        elif self.path == "/test-mic":
            cfg = _norm_cfg(body.get("cfg"))
            try:
                audio = recorder.record_fixed(4)
                text = asr.transcribe(audio, cfg)
                self._send_json({"heard": text})
            except Exception as e:
                self._send_json({"error": str(e)})
        elif self.path == "/close":
            _DONE["closed"] = True
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "unknown endpoint"})


def open_settings(cfg):
    global LIVE_CFG
    LIVE_CFG = cfg
    srv = None
    ports = [PREFERRED_PORT] + [random.randint(49152, 65535) for _ in range(6)]
    for port in ports:
        try:
            srv = HTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        _log_note("settings: could not open a local server port")
        return
    url = f"http://127.0.0.1:{port}/"
    if not webbrowser.open(url):
        _log_note(f"settings: no browser opened, URL was {url}")
    _DONE.clear()
    _DONE["closed"] = False
    threading.Thread(
        target=srv.serve_forever, name="voice-dictation-settings"
    ).start()
    try:
        while not _DONE["closed"]:
            time.sleep(0.3)
    finally:
        srv.shutdown()  # blocks until the serve_forever thread has finished


if __name__ == "__main__":
    open_settings(config_mod.load())
