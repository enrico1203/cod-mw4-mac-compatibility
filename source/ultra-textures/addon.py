#!/usr/bin/env python3
"""Separate Ultra texture add-on. Existing compatibility fix and game files stay in place."""
import argparse
import contextlib
import fcntl
import hashlib
import http.client
import json
import os
import pathlib
import secrets
import shutil
import signal
import subprocess
import sys
import time
from storage import mirror_lock, remove_redundant

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "Data"
CONFIG = DATA / "settings.json"
MiB, GiB = 2**20, 2**30
VERSION = "0.2.2"
DEFAULT_RESERVE_GIB = 10


def save_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        os.chmod(temp, 0o600)
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(temp, path)


def settings():
    try:
        return json.loads(CONFIG.read_text())
    except FileNotFoundError:
        return {}


def pick_folder(prompt):
    if sys.platform != "darwin":
        raise ValueError("Set --game-root and --mirror from the command line.")
    escaped = prompt.replace('"', '\\"')
    r = subprocess.run(["/usr/bin/osascript", "-e", 'POSIX path of (choose folder with prompt "' + escaped + '")'],
                       capture_output=True, text=True)
    if r.returncode:
        raise ValueError("Folder selection cancelled.")
    return pathlib.Path(r.stdout.strip()).resolve()


def configure(game=None, mirror=None, choose=False):
    cfg = settings()
    # When this add-on folder is inside sp26, no game-folder picker is needed.
    if not game:
        for candidate in (ROOT, ROOT.parent, ROOT.parent.parent):
            if candidate.name == 'sp26' and (candidate / 'sp26-cod.exe').is_file():
                game = candidate.parent
                break
            if (candidate / 'sp26/sp26-cod.exe').is_file():
                game = candidate
                break
    if choose or not (game or cfg.get("game_root")):
        game = pick_folder("Choose the game folder that contains sp26")
        if game.name == "sp26":
            game = game.parent
    game = pathlib.Path(game or cfg["game_root"]).expanduser().resolve()
    if not (game / "sp26/sp26-cod.exe").is_file():
        raise ValueError("Choose the game folder containing sp26/sp26-cod.exe.")
    if choose:
        mirror = pick_folder("Choose a drive or folder for the Ultra texture download") / "MW4-Ultra-Mirror"
    mirror = pathlib.Path(mirror or cfg.get("mirror") or game.parent / (game.name + ' - Ultra Textures')).expanduser().resolve()
    # Store mirror content separately from every part of the installed game.
    if mirror == game or mirror.is_relative_to(game):
        raise ValueError("Choose a texture storage folder outside the game folder.")
    reserve = cfg.get("min_free_gib", DEFAULT_RESERVE_GIB)
    if cfg.get("version") in ("0.1", "0.2") and reserve == 40:
        # Migrate the former generated default; keep other user-set reserves.
        reserve = DEFAULT_RESERVE_GIB
    cfg.update(version=VERSION, game_root=str(game), mirror=str(mirror), min_free_gib=reserve)
    save_json(CONFIG, cfg)
    return cfg


def load_vendor(cfg):
    os.environ.update(CCS_GAME_ROOT=cfg["game_root"], CCS_MIRROR_DIR=cfg["mirror"], CCS_WORK=str(DATA / "Work"))
    sys.path.insert(0, str(ROOT / "vendor"))
    from ccslib import pack, paths
    paths.reload()
    return pack


def plan(cfg):
    pack = load_vendor(cfg)
    # Ultra's 4096 MiB boundary includes the entire uint32 raw-size catalogue.
    p = pack.plan("sp", level="ultra", root=cfg["game_root"], mirror_dir=cfg["mirror"])
    p["quality"] = "Ultra: every SP + boot chunk, no texture-size filtering"
    p["reserve_gib"] = cfg["min_free_gib"]
    p["fits_with_reserve"] = p["free_gib"] >= p["need_gib"] + cfg["min_free_gib"]
    p["estimated_free_after_download_gib"] = p["free_gib"] - p["total"]["pending_gib"]
    return p


def catalogue_signature(cfg):
    pack = load_vendor(cfg)
    root = pathlib.Path(cfg['game_root'])
    entries = {}
    for package in ('sp', 'boot'):
        for relative in pack.list_files(package):
            path = root / relative
            if path.is_file():
                entries[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return entries


def show_plan(p, cfg):
    total = p["total"]
    print(f"MW4 Ultra Textures {VERSION} — separate add-on")
    print("Quality: Ultra / all campaign texture sizes")
    print(f"Campaign + boot: {total['chunks']:,} pieces, {total['gib']:.2f} GiB")
    print(f"Downloaded: {total['stored']:,}; remaining: {total['pending_gib']:.2f} GiB")
    print("Texture folder:", cfg["mirror"])
    print(f"Free space: {p['free_gib']:.1f} GiB; space kept free: {p['reserve_gib']:g} GiB")
    print(f"Estimated free space after download: {p['estimated_free_after_download_gib']:.1f} GiB")
    if not p["fits_with_reserve"]:
        print("Open Ultra-Textures.command and choose a location with more free space.")


@contextlib.contextmanager
def operation_lock():
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / "operation.lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("A download or verification is already running.")
        yield


def child_env(cfg):
    env = dict(os.environ)
    for key in tuple(env):
        if key.startswith("CCS_"):
            del env[key]
    env.update(CCS_GAME_ROOT=cfg["game_root"], CCS_MIRROR_DIR=cfg["mirror"], CCS_WORK=str(DATA / "Work"),
               PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
    return env


def vendor_command(cfg, args, pause=False, progress_context=None, quiet=False):
    cmd = [sys.executable, str(ROOT / "vendor/ccsmirror.py"), *args]
    stopfile = DATA / "PAUSE"
    interrupted = False
    def request_pause(*_):
        nonlocal interrupted
        interrupted = True
        stopfile.touch()
        print("Pausing after the current pieces finish. Please keep this window open.", flush=True)
    old = {}
    if pause:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            old[sig] = signal.signal(sig, request_pause)
    try:
        if progress_context is None and not quiet:
            p = subprocess.Popen(cmd, env=child_env(cfg), start_new_session=True)
            return p.wait(), interrupted
        from interaction import ProgressDisplay
        progress_path = pathlib.Path(args[args.index('--progress-json') + 1]) if progress_context else None
        if progress_path:
            progress_path.unlink(missing_ok=True)
        logs = DATA / 'Logs'
        logs.mkdir(parents=True, exist_ok=True)
        logfile = logs / (args[0] + '-' + str(time.time_ns()) + '.txt')
        with logfile.open('w') as log:
            os.chmod(logfile, 0o600)
            p = subprocess.Popen(cmd, env=child_env(cfg), start_new_session=True, stdout=log, stderr=subprocess.STDOUT)
            display = ProgressDisplay(progress_path, progress_context, p.pid) if progress_context else None
            while p.poll() is None:
                if display:
                    display.update()
                time.sleep(0.5)
            if display:
                display.update(final=True)
        if p.returncode:
            print('Details of this problem:', logfile)
        return p.returncode, interrupted
    finally:
        for sig, previous in old.items():
            signal.signal(sig, previous)


def download(cfg):
    with operation_lock():
        p = plan(cfg)
        show_plan(p, cfg)
        if p["missing"] or not p["total"]["chunks"]:
            raise ValueError("The campaign chunk lists are missing. Check the selected game folder.")
        if not p["fits_with_reserve"]:
            return 2
        from interaction import choose
        total = p['total']
        approved_catalogue = catalogue_signature(cfg)
        label = 'Resume Download' if total['stored'] else 'Download'
        message = (f"Download the highest-quality campaign textures?\n\n"
                   f"Complete set: {total['gib'] * 2**30 / 1e9:.1f} GB ({total['gib']:.1f} GiB)\n"
                   f"Remaining download: {total['pending_gib'] * 2**30 / 1e9:.1f} GB\n"
                   f"Available space: {p['free_gib']:.1f} GiB\n"
                   f"Estimated free after download: {p['estimated_free_after_download_gib']:.1f} GiB\n"
                   f"Minimum space kept free: {p['reserve_gib']:g} GiB\n"
                   f"Pieces: {total['chunks']:,}\nLocation: {cfg['mirror']}\n\n"
                   "This folder stores files for the local texture service.\n"
                   "It is separate from the game's own texture cache.\n\n"
                   "You can pause and resume. Every piece will be checked.\n"
                   "After verification, redundant older copies of the same pieces will be removed.\n"
                   "The local texture service must stay open while you play.")
        if choose(message, ['Cancel', label], default=label) != label:
            print('Download cancelled. No textures were downloaded.')
            return 0
        with mirror_lock(cfg['mirror']):
            return download_approved(cfg, approved_catalogue)


def download_approved(cfg, approved_catalogue):
    # The catalogue/location shown above must still be the one we will use.
    p = plan(cfg)
    if not p['fits_with_reserve'] or catalogue_signature(cfg) != approved_catalogue:
        raise ValueError('The download plan changed. Open Ultra-Textures.command to review it again.')
    # Refresh metadata without trusting an orphan object's length.
    print('Reading the texture catalogue...', flush=True)
    code, _ = vendor_command(cfg, ["init", "--scope", "sp"], quiet=True)
    if code:
        return code
    save_json(DATA / 'ready.json', dict(complete=False))
    code, paused = vendor_command(cfg, ["run", "--scope", "sp", "--level", "ultra", "--workers", "4",
         "--min-free-gib", str(cfg["min_free_gib"]), "--max-rps", "50", "--budget-gib", "0",
         "--progress-json", str(DATA / "download-progress.json"), "--stop-file", str(DATA / "PAUSE"),
         "--accept-notice"], pause=True, progress_context=dict(kind='download',
             total_bytes=int(p['total']['gib'] * GiB), stored_bytes=int(p['total']['stored_gib'] * GiB)))
    if code:
        return code
    if paused:
        print("Download paused. Open Ultra-Textures.command to resume.")
        return 0
    p = plan(cfg)
    total = p["total"]
    if total["stored"] != total["chunks"]:
        print("Download is incomplete. Open Ultra-Textures.command to review and resume.")
        return 2
    return verify(cfg)


def verify(cfg):
    save_json(DATA / 'ready.json', dict(complete=False))
    # Refresh wire/flag metadata before verifying or removing older variants.
    code, _ = vendor_command(cfg, ["init", "--scope", "sp"], quiet=True)
    if code:
        return code
    code, _ = vendor_command(cfg, ["verify", "--all", "--progress-json", str(DATA / "verification.json")],
                             progress_context=dict(kind='verify'))
    if code:
        print("Some pieces failed verification. They will be retried when you reopen Ultra-Textures.command.")
        vendor_command(cfg, ["verify", "--all", "--fix", "--progress-json", str(DATA / "verification.json")], quiet=True)
        return 2
    p = plan(cfg)
    complete = p["total"]["chunks"] > 0 and p["total"]["stored"] == p["total"]["chunks"]
    if complete:
        cleaned = remove_redundant(cfg['mirror'])
        if cleaned['deleted']:
            print(f"Removed {cleaned['deleted']} redundant old/partial files "
                  f"({cleaned['logical_bytes_removed'] / GiB:.2f} GiB logical size).")
        if cleaned['skipped']:
            print(f"Kept {cleaned['skipped']} files that could not be safely cleaned.")
    save_json(DATA / "ready.json", dict(complete=complete, checked_at=time.time(), mirror=cfg["mirror"],
                                      storage_revision=1,
                                      chunks=p["total"]["chunks"], game_root=cfg["game_root"],
                                      catalogue_signature=catalogue_signature(cfg)))
    print("All campaign pieces are verified. Open Ultra-Textures.command before launching the game." if complete
          else "Stored pieces verified; the full Ultra campaign set is still incomplete.")
    return 0 if complete else 2


def request(method, path, token=None):
    c = http.client.HTTPConnection("127.0.0.1", 80, timeout=3)
    try:
        headers = {"Authorization": "Bearer " + token} if token else {}
        c.request(method, path, headers=headers)
        r = c.getresponse()
        body = r.read()
        if r.status != 200:
            raise ValueError("Texture service returned HTTP " + str(r.status))
        return body
    finally:
        c.close()


def start(cfg):
    with operation_lock(), mirror_lock(cfg["mirror"]):
        p = plan(cfg)
        if not p["total"]["chunks"] or p["total"]["stored"] != p["total"]["chunks"]:
            raise ValueError("Download the complete Ultra campaign set before starting offline textures.")
        try:
            ready = json.loads((DATA / "ready.json").read_text())
        except FileNotFoundError:
            ready = {}
        if not ready.get("complete") or ready.get("storage_revision") != 1 or ready.get("mirror") != cfg["mirror"] or ready.get("chunks") != p["total"]["chunks"] or ready.get("game_root") != cfg["game_root"]:
            raise ValueError("Open Ultra-Textures.command to verify this mirror before starting.")
        if ready.get('catalogue_signature') != catalogue_signature(cfg):
            raise ValueError('The texture catalogue changed. Open Ultra-Textures.command to refresh the mirror.')
        from texture_bridge import edit_hosts
        token = secrets.token_hex(24)
        raw = pathlib.Path("/etc/hosts").read_bytes()
        edit_hosts(raw, token, True)
        DATA.mkdir(parents=True, exist_ok=True)
        backup = DATA / ("hosts-before-" + time.strftime("%Y%m%d-%H%M%S") + ".txt")
        with backup.open("xb") as f:
            os.chmod(backup, 0o600); f.write(raw)
        save_json(DATA / "session.json", dict(token=token, mirror=cfg["mirror"], hosts_backup=str(backup), started=time.time()))
        print("Start this before launching the game. Your Mac will request an administrator password.", flush=True)
        print("Only the temporary texture routing and port 80 need that permission.", flush=True)
        # Isolated Python startup ignores PYTHONPATH and user site customizations under sudo.
        def end_session(*_):
            print('Stopping the texture session; waiting for routing cleanup.', flush=True)
            try:
                request('POST', '/__mw4/stop', token)
            except (OSError, ValueError):
                pass  # The sudo supervisor also receives Terminal's interrupt/hangup.
        old = {sig: signal.signal(sig, end_session) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        try:
            return subprocess.run(["/usr/bin/sudo", "--", sys.executable, "-I", str(ROOT / "session_entry.py"),
                cfg["mirror"], token, hashlib.sha256(raw).hexdigest()]).returncode
        finally:
            for sig, previous in old.items():
                signal.signal(sig, previous)


def stop():
    try:
        session = json.loads((DATA / "session.json").read_text())
        print(request("POST", "/__mw4/stop", session["token"]).decode().strip())
    except (OSError, ValueError, KeyError):
        print("No responding texture session. Open Ultra-Textures.command if routing needs recovery.")
        return 1
    return 0


def restore():
    session = json.loads((DATA / "session.json").read_text())
    from texture_bridge import edit_hosts
    raw = pathlib.Path("/etc/hosts").read_bytes()
    if edit_hosts(raw, session["token"], False) == raw:
        print("No add-on routing remains.")
        return 0
    return subprocess.run(["/usr/bin/sudo", "--", sys.executable, "-I", str(ROOT / "session_entry.py"),
                           "--restore", session["token"]]).returncode


def mirror_ready(cfg, p):
    try:
        ready = json.loads((DATA / 'ready.json').read_text())
    except (OSError, ValueError):
        return False
    return (ready.get('complete') and ready.get('storage_revision') == 1 and ready.get('mirror') == cfg['mirror'] and
            ready.get('game_root') == cfg['game_root'] and ready.get('chunks') == p['total']['chunks'] and
            ready.get('catalogue_signature') == catalogue_signature(cfg))


def open_flow(cfg):
    from interaction import choose
    from texture_bridge import PREFIX
    try:
        session = json.loads((DATA / 'session.json').read_text())
    except (OSError, ValueError):
        session = {}
    try:
        active = json.loads(request('GET', '/__mw4/status'))
    except (OSError, ValueError):
        active = None
    if active:
        answer = choose('Ultra textures are already on.\n\nKeep the texture window open while you play. '
                        'When you finish the game, choose Stop Textures to restore normal routing.',
                        ['Close', 'Stop Textures'], default='Close', cancel='Close')
        return stop() if answer == 'Stop Textures' else 0
    if session.get('token') and PREFIX + session['token'] in pathlib.Path('/etc/hosts').read_text():
        answer = choose('A previous texture session did not finish restoring its routing.\n\nRestore it before continuing.',
                        ['Cancel', 'Restore Routing'], default='Restore Routing')
        return restore() if answer == 'Restore Routing' else 0
    while True:
        p = plan(cfg)
        total = p['total']
        if p['missing'] or not total['chunks']:
            raise ValueError('The campaign texture lists are missing. Check that this folder is inside the correct sp26 folder.')
        complete = total['stored'] == total['chunks']
        if complete:
            if mirror_ready(cfg, p):
                answer = choose('Your Ultra campaign textures are downloaded and verified.\n\n'
                                'Start the local texture service, then launch the game with your existing fix. '
                                'Keep the service window open while playing.',
                                ['Close', 'Verify Files', 'Start Textures'], default='Start Textures', cancel='Close')
                if answer == 'Start Textures':
                    return start(cfg)
                if answer == 'Close':
                    return 0
            else:
                answer = choose('All campaign pieces are present. Check them before using this mirror.',
                                ['Cancel', 'Verify Files'], default='Verify Files')
                if answer == 'Cancel':
                    return 0
            with operation_lock(), mirror_lock(cfg["mirror"]):
                result = verify(cfg)
            if result:
                return result
            continue
        if not p['fits_with_reserve']:
            needed = p['need_gib'] + p['reserve_gib']
            answer = choose(f"Ultra campaign textures need more space.\n\n"
                            f"Complete download: {total['gib'] * GiB / 1e9:.1f} GB ({total['gib']:.1f} GiB)\n"
                            f"Required free space, including the reserve: {needed:.1f} GiB\n"
                            f"Minimum space kept free: {p['reserve_gib']:g} GiB\n"
                            f"Available: {p['free_gib']:.1f} GiB\n\n"
                            "Choose storage for the local texture service. It can be on another drive; "
                            "this is separate from the game's own cache.",
                            ['Cancel', 'Choose Location'], default='Choose Location')
            if answer == 'Cancel':
                return 0
            folder = pick_folder('Choose a drive or folder for the Ultra textures') / 'MW4-Ultra-Mirror'
            cfg = configure(game=cfg['game_root'], mirror=folder)
            continue
        result = download(cfg)
        after = plan(cfg)
        if result == 0 and mirror_ready(cfg, after):
            continue  # The next screen offers Start Textures; activation is never automatic.
        return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("open", "configure", "plan", "download", "verify", "start", "stop", "status", "restore"))
    ap.add_argument("--game-root"); ap.add_argument("--mirror"); ap.add_argument("--json", action="store_true")
    ap.add_argument('--terminal', action='store_true', help='show confirmations in this terminal')
    a = ap.parse_args()
    import interaction
    interaction.TERMINAL = a.terminal
    if a.action == "stop":
        return stop()
    if a.action == "restore":
        return restore()
    cfg = configure(a.game_root, a.mirror, choose=a.action == "configure" and not a.game_root)
    if a.action == 'open':
        return open_flow(cfg)
    if a.action == "download":
        return download(cfg)
    if a.action == "verify":
        with operation_lock(), mirror_lock(cfg["mirror"]):
            return verify(cfg)
    if a.action == "start":
        return start(cfg)
    p = plan(cfg)
    if a.action == "status":
        try:
            p["texture_service"] = json.loads(request("GET", "/__mw4/status"))
        except (OSError, ValueError):
            p["texture_service"] = "off"
    if a.json:
        print(json.dumps(p))
    else:
        show_plan(p, cfg)
        if "texture_service" in p:
            print("Texture service:", p["texture_service"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print("ERROR:", str(error), file=sys.stderr)
        raise SystemExit(1)
