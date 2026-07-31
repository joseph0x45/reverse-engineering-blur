"""Real 266-byte auth success reply, captured live 2026-07-22 via x32dbg MCP bridge.

Captured at bdAuthService::handleReply (blur.CEA4B0) entry, reading the reader
object's data buffer (this+0x08) after a real login against amax-emu's live
master.amax-emu.com server (using amax_auth.asi's bdPlatformStreamSocket hook).

Call arguments seen on the stack at handleReply entry (pre-prologue):
  [esp+4] (-> [ebp+8])   = 0x0000000B = 11        <- replyType, CONFIRMS the
                                                      replyType=11 "ticket read"
                                                      hypothesis from static analysis
  [esp+8] (-> [ebp+0xC]) = 0x1ECD2CE8              <- reader object pointer

Reader object fields (matches our documented layout exactly):
  this+0x08 data ptr   = 0x16AA9710
  this+0x10 size bytes = 0x10A (266)
  this+0x18 cap bits   = 0x850 (2128 = 266*8)
  this+0x1C cursor     = 1 bit (m_typeChecked already consumed by ctor)

First 4 bytes (78 05 00 00) exactly match our own hand-derived error_code=0x2BC
encoding from the 2026-07-20 session -- confirms the bdBitBuffer bit-packing
algorithm (LSB-first) was reverse-engineered correctly. Everything from byte 4
onward is real, previously-unseen ticket-bearing payload.
"""

CAPTURED_REPLY = bytes.fromhex(
    "780500003a984c00f0aeb6d5497ea066efba2225e94ec9a4acbc66830f5dd4b"
    "e530638988831eae62373500e224bdb8ce66c98d342d915f289e4185d6676af"
    "b2143d8d5128c0d54d58f888affc9f67d7c4e67d351c899b3101a319cbf418a"
    "65b8efa7bb628fb17006b954eb57845c67838c07fcfe3929405233ac6ba9c01"
    "5cdcf840468c2aac6cdc00c9619f73fb4069fd849c409a2f65b3efb632def1f"
    "e53ab3eeb97d450861f3528d3011ab7ce6d47e9bc5547e138e3a4b28d6805c3"
    "c08deedff56db3221068a102f53003d382ab49fb8d676d4fdb14f7856d11f8f"
    "23d25bc323a929b2569a0888234da383e5ce12787a44cd90bd20a4aac2a7050"
    "25b3a2da16600ae9feaa93df0000"
)

assert len(CAPTURED_REPLY) == 266, len(CAPTURED_REPLY)

if __name__ == "__main__":
    print(len(CAPTURED_REPLY), "bytes")
    print(CAPTURED_REPLY.hex())
