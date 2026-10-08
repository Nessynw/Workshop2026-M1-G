"""Initialise le volume SQLite puis lance le serveur sans privilèges root."""
import os
import sys
from pathlib import Path

data = Path("/app/data")
data.mkdir(parents=True, exist_ok=True)
if os.getuid() == 0:
    os.chown(data, 10001, 10001)
    for path in data.glob("alerts.db*"):
        os.chown(path, 10001, 10001, follow_symlinks=False)
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)
os.execvp(sys.argv[1], sys.argv[1:])
