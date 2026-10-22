"""Small native confirmation dialogs and a readable terminal progress display."""
import json
import math
import pathlib
import subprocess
import sys

TERMINAL = False


def choose(message, buttons, default=None, cancel="Cancel"):
    default = default or buttons[-1]
    if sys.platform == "darwin" and not TERMINAL:
        script = '''on run argv
set choices to items 2 thru -1 of argv
try
set answer to display dialog (item 1 of argv) with title "MW4 Ultra Textures" buttons choices default button "DEFAULT" cancel button "CANCEL" with icon note
return button returned of answer
on error errText number errNo
if errNo is -128 then return "CANCEL"
error errText number errNo
end try
end run'''.replace('DEFAULT', default).replace('CANCEL', cancel)
        r = subprocess.run(["/usr/bin/osascript", "-e", script, message, *buttons], capture_output=True, text=True)
        if r.returncode:
            raise ValueError("The confirmation window could not open: " + r.stderr.strip())
        reply = r.stdout.strip()
        if reply not in buttons:
            raise ValueError("No valid confirmation was received")
        return reply
    print(message)
    for i, label in enumerate(buttons, 1):
        print(f"  {i}. {label}")
    try:
        reply = input("Choose an option: ").strip()
    except EOFError:
        return cancel
    if reply.isdigit() and 1 <= int(reply) <= len(buttons):
        return buttons[int(reply) - 1]
    for label in buttons:
        if reply.casefold() == label.casefold():
            return label
    return cancel


def duration(seconds):
    if seconds is None or not math.isfinite(seconds):
        return "calculating"
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m {seconds:02d}s"


def progress_line(data, context):
    if context["kind"] == "verify":
        total = max(0, data.get("total", 0))
        done = min(total, data.get("done", 0))
        fraction = done / total if total else 1
        return f"Checking files  {fraction:6.1%}  {done:,} / {total:,} pieces  |  problems: {data.get('bad', 0):,}"
    total = context["total_bytes"]
    done = min(total, context["stored_bytes"] + data.get("bytes", 0))
    fraction = done / total if total else 0
    speed = max(0, data.get("mibps_now") or data.get("mibps", 0)) * 2**20
    eta = (total - done) / speed if speed > 0 else None
    state = data.get("state", "starting")
    names = {"running": "Downloading", "offline-wait": "Waiting for connection", "quota-wait": "Waiting for quota",
             "paused": "Paused", "disk-space": "Waiting for disk space", "done": "Download pass finished", "stopping": "Pausing"}
    filled = min(24, int(fraction * 24))
    return (f"{names.get(state, state)}  [{'#' * filled}{'-' * (24 - filled)}] {fraction:6.1%}  "
            f"{done / 2**30:.2f} / {total / 2**30:.2f} GiB  |  {speed / 1e6:.1f} MB/s  |  {duration(eta)} left")


class ProgressDisplay:
    def __init__(self, path, context, pid):
        self.path = pathlib.Path(path)
        self.context = context
        self.pid = pid
        self.last = None

    def update(self, final=False):
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        if data.get("pid") != self.pid:
            return
        line = progress_line(data, self.context)
        if line != self.last:
            print(("\r\033[2K" if sys.stdout.isatty() else "") + line,
                  end="" if sys.stdout.isatty() else "\n", flush=True)
            self.last = line
        if final and self.last and sys.stdout.isatty():
            print()
