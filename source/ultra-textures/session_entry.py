"""Isolated entry for the narrow privileged supervisor. Imports no vendor modules."""
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from texture_bridge import change_hosts, privileged_session

if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--restore":
            if os.geteuid() != 0:
                raise ValueError("Administrator permission is required to restore routing")
            change_hosts("/etc/hosts", sys.argv[2], False)
            subprocess.run(["/usr/bin/dscacheutil", "-flushcache"], check=False)
            print("Texture routing restored.")
            raise SystemExit(0)
        if len(sys.argv) != 4:
            raise ValueError("Invalid texture session arguments")
        raise SystemExit(privileged_session(*sys.argv[1:]))
    except (OSError, ValueError, RuntimeError) as error:
        print("ERROR:", error, file=sys.stderr)
        raise SystemExit(1)
