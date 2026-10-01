"""Generate the one-click launcher (VoiceDictation.bat) with absolute paths.

install.bat runs this after the venv and icon are created. Copy the generated
VoiceDictation.bat to your desktop (or anywhere) and double-click it to start
the app.
"""
import os

FOLDER = os.path.dirname(os.path.abspath(__file__))


def launcher_text():
    ps = (
        "powershell.exe -NoProfile -Command "
        "\"Start-Process -FilePath '{pythonw}' "
        "-ArgumentList '-X','utf8','app.py' -WorkingDirectory '{folder}'\""
    ).format(pythonw=FOLDER.replace("'", "''") + "\\.venv\\Scripts\\pythonw.exe",
             folder=FOLDER.replace("'", "''"))
    return "\r\n".join(["@echo off", ps, "exit /b", ""])


if __name__ == "__main__":
    path = os.path.join(FOLDER, "VoiceDictation.bat")
    with open(path, "w", encoding="ascii", newline="") as f:
        f.write(launcher_text())
    print(f"created: {path}")
