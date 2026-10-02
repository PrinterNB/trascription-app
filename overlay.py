"""A tiny status icon pinned to the top-right corner of the screen.

Windows 11 hides third-party tray icons by default, so the tray icon alone
does not tell you whether the app is recording or transcribing right now.
This module shows a small icon in the top corner of the displays for exactly
the two states that matter, and nothing at all the rest of the time.

Tk cannot do per-pixel translucency on Windows, but `-transparentcolor` makes
one exact colour fully see-through: the icon is pre-composited onto that
sentinel colour, so only the icon itself is visible. The window's frame is
placed just past the right edge of the displays so Windows clips it away.
"""

import base64
import io
import tkinter

import ctypes
from ctypes.wintypes import RECT as _RECT  # a {left,top,right,bottom} struct

import trayicon

# Window pixels of this exact colour become fully see-through (Tk's
# `-transparentcolor`, Windows only). No part of a drawn icon may use it.
SENTINEL = "#0f0f0f"

# The only states that get an on-screen indicator; everything else hides it.
SHOW_WHILE = ("recording", "processing")

ICON_SIZE = 64

_window = None  # (root, canvas) while an icon is shown
_current = None
_quitting = False  # set once close() ran: a live worker thread must not re-open


def _corner():
    """(far-right, top-of-right-most-display) in window-manager units.

    The x is never used as an actual position: asking for a point far off
    the right edge makes Windows/Tk slide the window back on-screen flush
    with the right edge, which is exactly what puts the window's frame
    past the last display, clipped away. The y comes from the GDI
    monitor boxes, which are in the same coordinate space the geometry
    command speaks, so it needs no scaling."""
    far = max(_monitor_rects(), key=lambda m: m[2])
    return far[1]


def _monitor_rects():
    rects = []

    def visit(_hdc, p2, p3):
        # Documented as (hdc, LPRECT, LPVOID), but the modern GDI hands the
        # rectangle in the other slot: take whichever one actually has it.
        for p in (p2, p3):
            try:
                rc = p.contents
            except Exception:
                continue
            if rc and rc.right > rc.left and rc.bottom > rc.top:
                rects.append((rc.left, rc.top, rc.right, rc.bottom))
                return 1
        return 1

    callback = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(_RECT), ctypes.POINTER(_RECT)
    )(visit)
    if not ctypes.windll.user32.EnumDisplayMonitors(None, None, callback, None):
        raise OSError("EnumDisplayMonitors failed")
    if not rects:
        raise OSError("no monitor rects")
    return rects


def _photo_for(status):
    from PIL import Image

    art = trayicon.image_for(status)
    base = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), SENTINEL)
    flat = Image.alpha_composite(base, art)  # icon on the see-through colour
    buf = io.BytesIO()
    flat.save(buf, format="PNG")
    return tkinter.PhotoImage(data=base64.b64encode(buf.getvalue()))


def _open(status):
    top = _corner()
    root = tkinter.Tk()
    try:
        # Asking for an x far past the right edge makes Windows/Tk slide the
        # window back on-screen flush with that edge - which leaves its content
        # in the top-right corner of the right-most display and pushes the
        # window's frame strip just off the edge, where it is not drawn.
        root.wm_attributes("-transparentcolor", SENTINEL)
        root.wm_geometry("%dx%d+%d+%d" % (ICON_SIZE, ICON_SIZE, 60000, top))
        root.configure(bg=SENTINEL)
        canvas = tkinter.Canvas(root, bg=SENTINEL, width=ICON_SIZE, height=ICON_SIZE)
        canvas.pack()
        canvas.create_image(0, 0, image=_photo_for(status), anchor="nw")
        root.update_idletasks()
        root.update()
    except Exception:
        root.destroy()  # every raise path after Tk() tears its window down
        raise
    return root, canvas


def _set_picture(status):
    """Swap the picture inside an already-open window (recording <->
    processing): no destroy/create, no flicker."""
    global _current
    canvas = _window[1]
    canvas.delete("all")
    canvas.create_image(0, 0, image=_photo_for(status), anchor="nw")
    _current = status


def _close():
    global _window, _current
    if _window:
        root, _canvas = _window
        _window = None
        _current = None
        root.destroy()


def set_status(status):
    """Show the corner icon while recording/processing, hide it otherwise.
    Never raises: a display glitch must not break a dictation cycle."""
    global _window, _current, _quitting
    try:
        if _quitting:
            # main() closed the HUD on Quit; the worker thread is still running
            # mid-cycle - it must not re-open a window nobody will tear down.
            return
        if status in SHOW_WHILE:
            if _window is None:
                _window = _open(status)
                _current = status
            elif _current != status:
                _set_picture(status)
        else:
            _close()
    except Exception:
        try:
            _close()
        except Exception:
            pass


def close():
    """Tear the window down; call it once when the app quits so the Tk
    interpreter does not sit around waiting for events at exit."""
    global _quitting
    _quitting = True  # a worker thread still running mid-cycle must not re-open
    _close()
