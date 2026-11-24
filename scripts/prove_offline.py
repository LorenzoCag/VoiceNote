"""Prove VoiceNote works with no network access.

Runs a normal VoiceNote command with every non-local network connection and DNS lookup
blocked and logged. If anything tried to reach the internet you will see it listed at the end.

    python scripts/prove_offline.py summarize eval/transcripts/grocery_todo.txt
    python scripts/prove_offline.py transcribe my_recording.wav --summarize

This works from inside the same process, so it needs no admin rights. For an independent,
OS-level check, also try turning Wi-Fi off, or watch connections with `nettop` / Little Snitch
(see README, "Verifying it's local").
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", None, ""}
attempts: list[tuple[str, object]] = []

_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo


def _is_remote(addr) -> bool:
    return isinstance(addr, tuple) and addr[0] not in LOCAL_HOSTS


def _guard_connect(self, addr, *args, **kwargs):
    if _is_remote(addr):
        attempts.append(("connect", addr))
        raise OSError(f"BLOCKED by prove_offline.py: {addr}")
    return _connect(self, addr, *args, **kwargs)


def _guard_connect_ex(self, addr, *args, **kwargs):
    if _is_remote(addr):
        attempts.append(("connect", addr))
        return 1
    return _connect_ex(self, addr, *args, **kwargs)


def _guard_getaddrinfo(host, *args, **kwargs):
    if host not in LOCAL_HOSTS:
        attempts.append(("dns", host))
        raise socket.gaierror(f"BLOCKED by prove_offline.py: {host}")
    return _getaddrinfo(host, *args, **kwargs)


def block_network() -> None:
    """Block and log every non-loopback connection and DNS lookup in this process."""
    socket.socket.connect = _guard_connect
    socket.socket.connect_ex = _guard_connect_ex
    socket.getaddrinfo = _guard_getaddrinfo


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    block_network()

    from voicenote.cli import main as voicenote_main

    print("[prove_offline] all non-local networking is blocked and logged\n")
    try:
        code = voicenote_main(sys.argv[1:])
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1

    print("\n" + "=" * 65)
    if attempts:
        print(f"[prove_offline] FAIL: {len(attempts)} network attempt(s) were blocked:")
        for kind, target in attempts:
            print(f"    {kind}: {target}")
        return 1
    if code:
        print(f"[prove_offline] The command failed (exit {code}), so this run proves nothing yet.")
        print("                (it made no network attempts, but it also didn't finish)")
        return code
    print("[prove_offline] PASS: the command completed with zero network attempts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
