"""Atomische, duurzame metadata en procesvergrendeling op de Linux-host."""
import contextlib
import fcntl
import json
import os
import tempfile
from pathlib import Path


def atomic(path, value, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            os.fchmod(out.fileno(), mode)
            out.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "beheer.lock").open("a") as out:
        try:
            fcntl.flock(out, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Er loopt al een installatie, back-up of update.") from None
        try:
            yield
        finally:
            fcntl.flock(out, fcntl.LOCK_UN)
