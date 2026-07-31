"""Variant of fake_lan_beacon.py that RANDOMIZES the bytes after the "SpotUdp0"
magic instead of replaying the exact captured payload.

Hypothesis being tested: the captured beacon's bytes[8:] were byte-identical
across two separate hosting attempts AND after a full Blur relaunch (new
process) -- meaning they're not a per-session random token, but something
persistent (machine/install identity). If so, Blur's LAN listener may be
silently filtering out beacons whose identity matches its own -- which would
explain why replaying the exact real capture never showed up in "Find Game",
even from a different source IP and even with Blur not hosting.

This sends a beacon with the same magic + structure but randomized bytes[8:44],
to see whether an entry NOW shows up (supporting the self-identity-filter
theory) or still doesn't (meaning the real gate is something else entirely,
e.g. a required checksum/signature we're not computing, and pure guessing
won't get further -- next step would be x64dbg).
"""

import random
import socket
import time

MAGIC = bytes.fromhex("53706f7455647030")  # "SpotUdp0"
TOTAL_LEN = 44
PORT = 57621
BROADCAST_ADDR = "192.168.1.255"
INTERVAL_SECONDS = 5
SOURCE_ADDR = "192.168.1.84"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind((SOURCE_ADDR, 0))

print(f"Broadcasting randomized-identity beacons to {BROADCAST_ADDR}:{PORT} every {INTERVAL_SECONDS}s. Ctrl+C to stop.")
try:
    while True:
        payload = MAGIC + bytes(random.getrandbits(8) for _ in range(TOTAL_LEN - len(MAGIC)))
        sock.sendto(payload, (BROADCAST_ADDR, PORT))
        print(f"sent at {time.strftime('%H:%M:%S')}: {payload.hex()}")
        time.sleep(INTERVAL_SECONDS)
except KeyboardInterrupt:
    print("stopped")
