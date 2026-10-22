"""Keep one verified file per indexed chunk; never prune by texture size."""
import contextlib
import fcntl
import hashlib
import os
import pathlib
import re
import sqlite3
import stat

NAME = re.compile(r'([0-9a-f]{16})_([0-9a-f]{8})_([01])(\.part)?\Z')


@contextlib.contextmanager
def mirror_lock(mirror):
    """Shared by copies of this add-on, and held for the entire serving session."""
    mirror = pathlib.Path(mirror)
    mirror.mkdir(parents=True, exist_ok=True)
    path = mirror / '.mw4-operation.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('This texture storage is already in use. Stop its texture session or download first.')
        yield


def identity(path):
    s = path.lstat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns


def regular(path):
    return stat.S_ISREG(path.lstat().st_mode)


def verified(path, wire, etag):
    if not etag or not re.fullmatch('[a-fA-F0-9]{32}', etag):
        return False
    try:
        if not regular(path) or path.lstat().st_size != wire:
            return False
        digest = hashlib.md5()
        with path.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest() == etag.lower()
    except OSError:
        return False


def remove_redundant(mirror):
    """Caller holds mirror_lock and has verified the complete campaign set.

    Only remove regular, canonical-layout variants of an indexed status=1 id
    whose current file independently passes length + MD5. Unknown ids/files,
    symlinks and every current indexed file are kept. No game-cache access.
    """
    mirror = pathlib.Path(mirror)
    objects = mirror / 'objects'
    result = dict(deleted=0, logical_bytes_removed=0, skipped=0)
    if not objects.is_dir() or objects.is_symlink():
        return result
    db = mirror / 'index.sqlite'
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as connection:
        rows = {sid & (2**64-1): (wire, flag, etag) for sid, wire, flag, etag in
                connection.execute('select id,wire,flag,etag from chunks where status=1')}
    for shard in objects.iterdir():
        if not re.fullmatch('[0-9a-f]{2}', shard.name) or shard.is_symlink() or not shard.is_dir():
            continue
        candidates = {}
        for path in shard.iterdir():
            match = NAME.fullmatch(path.name)
            if not match:
                continue
            try:
                if not regular(path):
                    continue
                before = identity(path)
            except OSError:
                result['skipped'] += 1
                continue
            cid = int(match[1], 16)
            if match[1][-2:] != shard.name or cid not in rows:
                continue
            wire, flag, etag = rows[cid]
            expected = shard / f'{cid:016x}_{wire:08x}_{flag}'
            if path != expected:
                candidates.setdefault(cid, []).append((path, before))
        for cid, variants in candidates.items():
            wire, flag, etag = rows[cid]
            expected = shard / f'{cid:016x}_{wire:08x}_{flag}'
            if not verified(expected, wire, etag):
                result['skipped'] += len(variants)
                continue
            try:
                current_identity = identity(expected)
            except OSError:
                result['skipped'] += len(variants)
                continue
            for path, before in variants:
                try:
                    if (objects.is_symlink() or shard.is_symlink() or not regular(expected) or
                            identity(expected) != current_identity or not regular(path) or identity(path) != before):
                        result['skipped'] += 1
                        continue
                    path.unlink()
                    result['deleted'] += 1
                    result['logical_bytes_removed'] += before[2]
                except OSError:
                    result['skipped'] += 1
    return result
