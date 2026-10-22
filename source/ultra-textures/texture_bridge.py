"""Offline, full-quality texture service. Only loopback listeners; no game process access."""
import hashlib
import http.server
import ipaddress
import json
import os
import pathlib
import re
import signal
import socket
import sqlite3
import threading
import time
from urllib.parse import urlsplit

HOST = "cod-assets.cdn.callofduty.com"
PREFIX = "# >>> MW4 Ultra Textures "
SUFFIX = "# <<< MW4 Ultra Textures "
PATTERN = re.compile(r"^/pc/iw9_3/23/([0-9a-f]{2})/([0-9a-f]{16})_([0-9a-f]{8})_([01])$")
TOKEN_PATTERN = re.compile(r"[0-9a-f]{48}")


def mapping_lines(text):
    out = []
    for line in text.splitlines():
        fields = line.split("#", 1)[0].split()
        if len(fields) >= 2 and HOST in [x.lower() for x in fields[1:]]:
            out.append(line)
    return out


def hosts_block(token, newline="\n"):
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("Invalid session identifier")
    return newline.join((PREFIX + token + " >>>", "::1 " + HOST,
                         "127.0.0.1 " + HOST, SUFFIX + token + " <<<", ""))


def edit_hosts(raw, token, enable):
    # Keep the original bytes, including arbitrary encodings and line endings.
    text = raw.decode("latin-1")
    nl = "\r\n" if "\r\n" in text else "\n"
    block = hosts_block(token, nl)
    if enable:
        if PREFIX in text or SUFFIX in text or mapping_lines(text):
            raise ValueError("This CDN already has a hosts override. Restore it before starting this add-on.")
        # Refuse the rare non-terminated file; appending a separator would make exact undo ambiguous.
        if text and not text.endswith("\n"):
            raise ValueError("The hosts file has no final newline; it was left unchanged.")
        return (text + block).encode("latin-1")
    if block in text:
        if text.count(block) != 1:
            raise ValueError("Ambiguous add-on block; the hosts file was left unchanged.")
        return text.replace(block, "", 1).encode("latin-1")
    if PREFIX + token in text or SUFFIX + token in text:
        raise ValueError("The add-on block changed. Restore the saved hosts backup manually.")
    return raw


def change_hosts(path, token, enable, expected_sha256=None):
    import fcntl
    # In-place update retains owner, mode and ACL; only our exact block is removed on exit.
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "r+b") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        old = f.read()
        if expected_sha256 and hashlib.sha256(old).hexdigest() != expected_sha256:
            raise ValueError("Hosts changed during preparation; the file was left unchanged.")
        new = edit_hosts(old, token, enable)
        if new == old:
            return False
        try:
            f.seek(0); f.write(new); f.truncate(); f.flush(); os.fsync(f.fileno())
            f.seek(0)
            if f.read() != new:
                raise OSError("Hosts read-back mismatch")
        except BaseException:
            f.seek(0); f.write(old); f.truncate(); f.flush(); os.fsync(f.fileno())
            raise
        return True


def load_objects(mirror):
    db = pathlib.Path(mirror) / "index.sqlite"
    c = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = c.execute("select id,wire,flag,etag,cod_key from chunks where status=1").fetchall()
    finally:
        c.close()
    out = {}
    for sid, wire, flag, etag, key in rows:
        cid = sid & (2**64 - 1)
        if not etag or not re.fullmatch(r"[a-fA-F0-9]{32}", etag):
            continue
        if key is not None and ("\r" in key or "\n" in key):
            continue
        name = f"/pc/iw9_3/23/{cid & 255:02x}/{cid:016x}_{wire:08x}_{flag}"
        out[name] = (wire, etag.lower(), key)
    return out


def byte_range(value, length):
    if value is None:
        return 0, length - 1, False
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not m or not any(m.groups()) or length <= 0:
        raise ValueError("Unsupported range")
    a, b = m.groups()
    if not a:
        if int(b) <= 0:
            raise ValueError("Empty suffix range")
        start, end = max(0, length - int(b)), length - 1
    else:
        start, end = int(a), min(int(b), length - 1) if b else length - 1
    if start >= length or start > end:
        raise ValueError("Unsatisfiable range")
    return start, end, True


class Service:
    def __init__(self, mirror, token):
        self.mirror = pathlib.Path(mirror).resolve()
        self.token = token
        self.objects = load_objects(self.mirror)
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.verified = {}
        self.stats = dict(version="0.1", started=time.time(), requests=0, delivered=0, bytes=0,
                          misses=0, corrupt=0, ranges=0, indexed=len(self.objects), quality="Ultra / no size filter",
                          serving_uid=os.geteuid())

    def add(self, **values):
        with self.lock:
            for key, value in values.items():
                self.stats[key] += value

    def snapshot(self):
        with self.lock:
            return dict(self.stats)

    def open_object(self, path):
        wire, etag, key = self.objects[path]
        m = PATTERN.fullmatch(path)
        obj = self.mirror / "objects" / m[1] / path.rsplit("/", 1)[1]
        # Do not serve a file redirected outside the mirror by a symlink.
        if not obj.resolve().is_relative_to(self.mirror / "objects"):
            raise OSError("Object outside the mirror")
        fd = os.open(obj, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        f = os.fdopen(fd, "rb")
        try:
            st = os.fstat(f.fileno())
            identity = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
            if st.st_size != wire:
                raise OSError("Object size mismatch")
            with self.lock:
                known = self.verified.get(path) == identity
            if not known:
                digest = hashlib.md5()
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(block)
                if digest.hexdigest() != etag:
                    raise OSError("Object checksum mismatch")
                with self.lock:
                    self.verified[path] = identity
            f.seek(0)
            return f, wire, etag, key
        except BaseException:
            f.close()
            raise


def handler(service):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def setup(self):
            super().setup()
            self.connection.settimeout(20)
        def log_message(self, *args):
            pass
        def reply(self, status, body=b"", headers=()):
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        def do_HEAD(self):
            self.do_GET()
        def do_GET(self):
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                return self.reply(403)
            path = urlsplit(self.path).path
            if path == "/__mw4/status":
                return self.reply(200, json.dumps(service.snapshot()).encode(), (("Content-Type", "application/json"),))
            service.add(requests=1)
            if not PATTERN.fullmatch(path) or path not in service.objects:
                service.add(misses=1)
                return self.reply(404)
            try:
                f, wire, etag, key = service.open_object(path)
            except OSError:
                service.add(corrupt=1)
                return self.reply(404)
            with f:
                value = self.headers.get("Range")
                if self.headers.get("If-Range") not in (None, '"' + etag + '"'):
                    value = None
                try:
                    start, end, partial = byte_range(value, wire)
                except ValueError:
                    return self.reply(416, headers=(("Content-Range", f"bytes */{wire}"),))
                self.send_response(206 if partial else 200)
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("ETag", '"' + etag + '"')
                if key:
                    self.send_header("x-amz-meta-cod-key", key)
                if partial:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{wire}")
                    service.add(ranges=1)
                self.end_headers()
                if self.command == "HEAD":
                    return
                f.seek(start)
                remaining = end - start + 1
                try:
                    while remaining:
                        data = f.read(min(262144, remaining))
                        if not data:
                            break
                        self.wfile.write(data)
                        remaining -= len(data)
                        service.add(bytes=len(data))
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    return
                if remaining == 0:
                    service.add(delivered=1)
        def do_POST(self):
            if self.path != "/__mw4/stop" or self.headers.get("Authorization") != "Bearer " + service.token:
                return self.reply(403)
            self.reply(200, b"Stopping textures and restoring routing.\n")
            service.stop.set()
    return Handler


class Server4(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Server6(Server4):
    address_family = socket.AF_INET6
    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


def listeners(port, request_handler):
    servers = []
    try:
        for cls, addr in ((Server6, ("::1", port)), (Server4, ("127.0.0.1", port))):
            if servers and port == 0:
                addr = (addr[0], servers[0].server_address[1])
            servers.append(cls(addr, request_handler))
        return servers
    except BaseException:
        for server in servers:
            server.server_close()
        raise


def run_servers(servers, service):
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for thread in threads:
        thread.start()
    try:
        service.stop.wait()
    finally:
        for server in servers:
            server.shutdown(); server.server_close()


def privileged_session(mirror, token, expected_hosts_sha256):
    """Short root supervisor; the file-serving child drops to the invoking user."""
    if os.geteuid() != 0:
        raise ValueError("Start this session through Start-Textures.command")
    uid = int(os.environ.get("SUDO_UID", "0"))
    gid = int(os.environ.get("SUDO_GID", "0"))
    if uid <= 0 or gid <= 0:
        raise ValueError("An ordinary invoking user is required")
    hostfile = pathlib.Path("/etc/hosts")
    raw = hostfile.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hosts_sha256:
        raise ValueError("Hosts changed since the backup. Start the add-on again.")
    edit_hosts(raw, token, True)  # Validate before binding or starting a child.
    servers = listeners(80, handler(None))
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_fd)
        try:
            os.setgroups([]); os.setgid(gid); os.setuid(uid)
            # All mirror parsing and file serving happens after privilege drop.
            service = Service(mirror, token)
            for server in servers:
                server.RequestHandlerClass = handler(service)
            for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                signal.signal(sig, lambda *_: service.stop.set())
            os.write(write_fd, b"READY"); os.close(write_fd)
            run_servers(servers, service)
            os._exit(0)
        except BaseException as error:
            print("Texture service failed:", str(error), flush=True)
            os._exit(1)
    os.close(write_fd)
    for server in servers:
        server.server_close()
    import select
    import subprocess
    changed = False
    stopping = False
    def stop_child(*_):
        nonlocal stopping
        stopping = True
        try:
            os.kill(child, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop_child)
    try:
        readable, _, _ = select.select([read_fd], [], [], 20)
        if not readable or os.read(read_fd, 5) != b"READY" or stopping:
            raise RuntimeError("The texture service did not become ready; routing was left unchanged.")
        if hashlib.sha256(hostfile.read_bytes()).hexdigest() != expected_hosts_sha256:
            raise RuntimeError("Hosts changed during startup; routing was left unchanged.")
        changed = change_hosts(hostfile, token, True, expected_hosts_sha256)
        for cmd in (("/usr/bin/dscacheutil", "-flushcache"),):
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        for family, expected in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            answers = {x[4][0] for x in socket.getaddrinfo(HOST, 80, family, socket.SOCK_STREAM)}
            if answers != {expected}:
                raise RuntimeError("The system resolver did not adopt the texture routing; routing will be restored.")
        print("Ultra textures are on. Keep this window open and launch the game with your existing fix.", flush=True)
        print("Press Control-C or open Stop-Textures.command when you finish.", flush=True)
        while True:
            pid, status = os.waitpid(child, os.WNOHANG)
            if pid:
                return os.waitstatus_to_exitcode(status)
            time.sleep(0.2)
    finally:
        os.close(read_fd)
        stop_child()
        try:
            os.waitpid(child, 0)
        except ChildProcessError:
            pass
        if changed:
            change_hosts(hostfile, token, False)
            for cmd in (("/usr/bin/dscacheutil", "-flushcache"),):
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            print("Texture routing restored.", flush=True)
