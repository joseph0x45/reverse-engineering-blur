"""Replay the captured Blur LAN discovery beacon ("SpotUdp0") as a UDP broadcast,
to test whether Blur's "Find Game" screen picks it up as a real LAN lobby.

Captured live 2026-07-28 while hosting a real LAN game: broadcast to
192.168.1.255:57621 every ~30s, port fixed across separate hosting attempts,
payload byte-identical across attempts on this same machine/profile.
"""

import socket
import time

BEACON = bytes.fromhex(
    "53706f7455647030213887757e45f8f2000100044895c203665d62ffda0146"
    "873d346edf874f61f98580eb01"
)
PORT = 57621
BROADCAST_ADDR = "192.168.1.255"
INTERVAL_SECONDS = 5

SOURCE_ADDR = "192.168.1.84"  # secondary IP alias on eth1, added via
                               # `sudo ip addr add 192.168.1.84/24 dev eth1
                               # label eth1:1` -- used so the beacon doesn't
                               # come from the same IP Blur itself is running
                               # on (192.168.1.82), to rule out a same-IP
                               # self-filter in its LAN discovery listener.

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind((SOURCE_ADDR, 0))

print(f"Broadcasting {len(BEACON)}-byte beacon to {BROADCAST_ADDR}:{PORT} every {INTERVAL_SECONDS}s. Ctrl+C to stop.")
try:
    while True:
        sock.sendto(BEACON, (BROADCAST_ADDR, PORT))
        print(f"sent at {time.strftime('%H:%M:%S')}")
        time.sleep(INTERVAL_SECONDS)
except KeyboardInterrupt:
    print("stopped")
