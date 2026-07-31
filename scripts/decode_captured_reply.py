"""Decode the real captured 266-byte auth success reply using the confirmed
bdBitBuffer bit-reading algorithm (LSB-first, per-chunk <=8 bits, no
byte-boundary crossing within a single chunk -- see CLAUDE.md 2026-07-20
'Bit-packing algorithm fully recovered' section).
"""

from captured_real_success_reply import CAPTURED_REPLY


class BitReader:
    def __init__(self, data: bytes):
        self.data = data
        self.cursor = 0  # bit position

    def read_bits(self, num_bits: int) -> int:
        result = 0
        result_bit_pos = 0
        remaining = num_bits
        while remaining > 0:
            byte_index = self.cursor >> 3
            bit_offset = self.cursor & 7
            chunk_size = min(remaining, 8 - bit_offset)
            current_byte = self.data[byte_index]
            mask = (1 << chunk_size) - 1
            extracted = (current_byte >> bit_offset) & mask
            result |= extracted << result_bit_pos
            result_bit_pos += chunk_size
            self.cursor += chunk_size
            remaining -= chunk_size
        return result

    def read_bytes_raw(self, num_bytes: int) -> bytes:
        # Ticket blobs are read as a raw run of bits (1024 bits = 128 bytes),
        # reassembled the same way -- 8 bits at a time via read_bits.
        return bytes(self.read_bits(8) for _ in range(num_bytes))


r = BitReader(CAPTURED_REPLY)

m_type_checked = r.read_bits(1)
print(f"m_typeChecked = {m_type_checked}  (cursor={r.cursor})")

error_code = r.read_bits(32)
print(f"error_code = {error_code:#x} ({error_code})  (cursor={r.cursor})")

# replyType=11 handler: "reads a value via CE0E00, then reads exactly 1024
# bits (128 bytes) via CE0EE0". Try that literally first.
value2 = r.read_bits(32)
print(f"next 32-bit value = {value2:#x} ({value2})  (cursor={r.cursor})")

remaining_bits = len(CAPTURED_REPLY) * 8 - r.cursor
print(f"remaining bits after error_code + value2 = {remaining_bits} ({remaining_bits/8} bytes)")

ticket = r.read_bytes_raw(128)
print(f"ticket (128 bytes) hex:\n{ticket.hex()}")

remaining_bits = len(CAPTURED_REPLY) * 8 - r.cursor
print(f"remaining bits after ticket = {remaining_bits} ({remaining_bits/8} bytes)")

tail = bytes(r.read_bits(8) for _ in range(remaining_bits // 8))
print(f"tail ({len(tail)} bytes) hex:\n{tail.hex()}")
