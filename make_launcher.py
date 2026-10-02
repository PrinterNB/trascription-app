"""Generate the one-click launcher (VoiceDictation.bat) with absolute paths.

install.bat runs this after the venv and icon are created. Copy the generated
VoiceDictation.bat to your desktop (or anywhere) and double-click it to start
the app.
"""
import os

FOLDER = os.path.dirname(os.path.abspath(__file__))


def launcher_text():
    # cmd expands % even inside double quotes, so a literal % in a folder name
    # must be doubled here - only in the .bat text, never in os.path use.
    folder = FOLDER.replace("%", "%%").replace("'", "''")
    ps = (
        "powershell.exe -NoProfile -Command "
        "\"Start-Process -FilePath '{pythonw}' "
        "-ArgumentList '-X','utf8','app.py' -WorkingDirectory '{folder}'\""
    ).format(pythonw=folder + "\\.venv\\Scripts\\pythonw.exe", folder=folder)
    return "\r\n".join(["@echo off", ps, "exit /b", ""])


if __name__ == "__main__":
    path = os.path.join(FOLDER, "VoiceDictation.bat")
    try:
        data = launcher_text().encode("ascii")  # cmd misreads UTF-8 .bat bytes
    except UnicodeEncodeError:
        print(f"ERROR: this folder's path is not plain ASCII ({FOLDER}); "
              "cmd cannot run a launcher generated here - move or rename the folder")
        raise SystemExit(1)
    with open(path, "wb") as f:
        f.write(data)
    print(f"created: {path}")
