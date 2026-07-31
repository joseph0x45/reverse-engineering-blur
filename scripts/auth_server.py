#!/usr/bin/env python3
"""Minimal stand-in for Blur's Demonware auth server.

Speaks the length-prefixed framing observed in blur_online_attempt.txt
and replies with a guessed "success" status instead of the real
server's error 05 (username not found). Point the game's hosts file
at this machine for blur-pc-live.auth.mmp3.demonware.net and watch
the logs to see what the client does next.
"""

import asyncio
import logging
import struct

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("auth")

HOST = "0.0.0.0"
PORT = 3074

AUTH_REQUEST_TYPE = b"\x00\x0a"


async def read_message(reader: asyncio.StreamReader) -> bytes:
    header = await reader.readexactly(4)
    length = struct.unpack("<I", header)[0]
    return await reader.readexactly(length)


def parse_auth_request(payload: bytes) -> dict:
    # Layout from the 24-byte capture in blur_online_attempt.txt:
    # [0-1] msg type (00 0a)  [2] marker (51)  [3-6] nonce
    # [7-10] title id (da a4 00 00)  [11-18] username hash  [19] username len
    return {
        "marker": payload[2],
        "nonce": payload[3:7],
        "title_id": payload[7:11],
        "username_hash": payload[11:19],
        "username_len": payload[19],
    }


def build_auth_success() -> bytes:
    # header[0] = replyType, read by blur.CF48D0 before handleReply's
    # bdBitBuffer even starts. Jump table at blur.CEB2C8 (indexed via a
    # remap table at blur.CEB2E8) shows replyType=11 is the only case that
    # reads a full 1024-bit (128-byte = BD_AUTH_TICKET_SIZE) blob via
    # blur.CE0EE0 -- almost certainly the real ticket-reading path.
    reply_type = 11
    header = bytes([reply_type, 0x00])
    bitstream = bytes([0x78, 0x05]) + bytes(308)
    body = header + bitstream
    return struct.pack("<I", len(body)) + body


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    log.info("connection from %s", peer)
    try:
        while True:
            payload = await read_message(reader)
            log.info("recv %d bytes: %s", len(payload), payload.hex())

            if len(payload) >= 20 and payload[0:2] == AUTH_REQUEST_TYPE:
                fields = parse_auth_request(payload)
                log.info("auth request: %s", fields)

                # Real server sends a bare 4-byte 00 00 00 00 immediately
                # after the auth request, then the real status packet
                # ~270ms later (see frames 6/7/12 in blur_online_attempt.txt).
                ack = struct.pack("<I", 0)
                writer.write(ack)
                await writer.drain()
                log.info("sent %d bytes: %s", len(ack), ack.hex())

                await asyncio.sleep(0.27)

                response = build_auth_success()
                writer.write(response)
                await writer.drain()
                log.info("sent %d bytes: %s", len(response), response.hex())
            else:
                log.warning("unrecognized message, no response sent")
    except asyncio.IncompleteReadError:
        log.info("connection closed by %s", peer)
    finally:
        writer.close()


async def main() -> None:
    server = await asyncio.start_server(handle_client, HOST, PORT)
    log.info("listening on %s:%d", HOST, PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
