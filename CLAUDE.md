# Blur Online Revival — Project Notes

## Goal
Reverse engineer Blur (2010, Bizarre Creations) networking to allow private multiplayer
without Radmin VPN. The game's official servers are still partially alive but reject
unregistered accounts.

---

## Project Pivot (2026-07-28): relay via tsnet instead of Demonware auth emulation
Decided to stop reverse-engineering Demonware's auth ticket format (Steps 3-4 below,
`bdAuthTicket`/`bdBitBuffer` work) as the path to multiplayer. Reasoning: Blur has a
genuine, separate **LAN multiplayer mode** (confirmed via strings —
`CreateLanServer`, `JoinLanServer`, `MonitorJoinLanServer`,
`CheckLanServerNetworkVersion`, `EnumerateLanGames`/`IsEnumeratingLanGames`,
`NumLanServersEnumerated`, `GetLanLobbyList` vs `GetOnlineLobbyList`, `SystemLink`,
`RP_LAN`, and a whole menu screen `Screens\Multiplayer\MpLan.lua`) that doesn't touch
Demonware at all. LAN discovery/hosting protocols are typically simple, unencrypted UDP
broadcast/response — no auth tickets, no bit-packed `bdBitBuffer` ceremony.

**New plan:** use [`tsnet`](https://pkg.go.dev/tailscale.com/tsnet) (Tailscale's
userspace networking library, embeds a full Tailscale node in a Go program with no
external Tailscale client install needed) to put all players' machines on one virtual
LAN, then let Blur's native LAN mode do the actual hosting/joining over that virtual
network. A relay host with good upload bandwidth can improve the connection between
players if one of them has poor upstream (per another Claude Code session's research
into tsnet — unverified independently yet). This sidesteps the Demonware auth ticket
problem entirely — no ticket, no LSG protocol, no server-side emulation of Demonware's
services needed.

The auth-ticket reverse engineering below (Steps 3-4, the `bdBitBuffer`/`bdAuthTicket`
findings) is kept as historical record, not deleted, but is **no longer the active
path**. The Amax Emu mod (a third-party emulator using this same Demonware-emulation
approach) was explored as research material in a prior session and has since been
fully removed from both the repo and the Windows game install — this project does not
depend on it. See memory `blur-independence-from-amax` for why.

**New active goal:** reverse engineer Blur's LAN discovery/hosting protocol (find the
UDP broadcast port and packet format used by `EnumerateLanGames`/`CreateLanServer`/
`JoinLanServer`) via packet capture of a real two-machine LAN session, then build the
`tsnet` relay so that traffic can traverse a virtual LAN between players' real
machines.

**Project moved (2026-07-28):** the actual `tsnet` relay implementation lives in a
separate project, `~/blur-relay` (own `CLAUDE.md` there — a headless Go sidecar using
`tsnet`, byte-for-byte relaying LAN broadcast/game traffic without needing to decode
protocol meaning). This repo's job going forward is packet-capture/RE support for that
project, not full protocol reverse engineering as an end in itself — the relay design
only needs to replay bytes verbatim, not understand them. See `~/blur-relay/CLAUDE.md`'s
"Investigation Steps" section for current findings (LAN discovery port `57621`,
`"SpotUdp0"`-prefixed 44-byte beacon, and an open question about possible sender
validation that needs a real second machine to resolve — do not repeat deep x64dbg
reversing of the receive-validation code path, it's very likely unnecessary; see that
file for what was already tried and ruled out).

---

## What We're Building
A `tsnet`-based virtual LAN relay so a small group of friends can use Blur's native
LAN multiplayer mode over the internet, without Radmin VPN and without needing to
emulate Demonware's auth/lobby servers.

---

## Environment
- Game: Blur.exe (DODI repack) at `C:\Program Files (x86)\DODI-Repacks\Blur\Blur.exe`
- Analysis: WSL (Ubuntu) for static analysis, scripting, server code
- Packet capture: Wireshark on Windows
- Debugger: x64dbg on Windows (next step)
- VPS target: Hetzner Germany (€3-4/month, close to most players)

---

## Findings

### 1. Backend: Demonware
Blur uses Demonware (acquired by Activision in 2007) for all online services.
Found via string analysis on the binary.

**Server hostnames:**
```
blur-pc-live.auth.mmp3.demonware.net   # authentication server
blur-pc-live.lsg.mmp3.demonware.net    # lobby/session gateway
```

**STUN servers (NAT traversal):**
```
stun.au.demonware.net
stun.eu.demonware.net
stun.jp.demonware.net
stun.us.demonware.net
```

**Other:**
```
http://updates.blurgame.com/update_info/update_info.xml  # dead update server
```

### 2. Servers Are Still Alive
IP `185.34.107.28` resolves to the Demonware auth server and actively responds.
Whois confirms this IP block is owned by **Demonware Limited, Dublin, Ireland**
and was last modified in April 2026 — the infrastructure is actively maintained.

The server rejects connections with error code `05` (username not found) rather
than timing out, confirming it's a live running service.

### 3. Protocol Analysis
- **Transport:** TCP on port 3074
- **Encryption:** None — plain binary protocol, no TLS/SSL
- **Format:** Length-prefixed binary messages

**Auth packet structure (client → server, 24 bytes total, verified against
the raw hex in `blur_online_attempt.txt`):**
```
[00-03]  14 00 00 00   length header (20, little-endian, = bytes following this field)
[04-05]  00 0a         message type (auth request)
[06]     51            fixed — protocol marker/version
[07-10]  ?? ?? ?? ??   random nonce (changes every session)
[11-14]  da a4 00 00   fixed — Blur's title ID on Demonware
[15-22]  ?? ?? ?? ??   deterministic hash of username (same username = same bytes)
[23]     ??            username length (04 for "test", 05 for "test2")
```
(Note: earlier notes had this off by one byte — message type is 2 bytes
at [04-05], not 1 byte at [04]. Everything after shifts accordingly.)

**Server response (11 bytes):**
```
[00-03]  07 00 00 00   length header (7)
[04]     00            
[05]     0b            
[06]     80            
[07]     05            error code 05 = "username not found"
[08-10]  00 00 00      
```

Framing rule (both directions): 4-byte little-endian length header, where
the value is the number of bytes that follow (not including the header
itself).

**Key observations:**
- Username is hashed (not plaintext) with a static/deterministic function
- Nonce at [06-09] is random per session
- Password is NOT sent in this first packet — this is a username lookup step
- Hash at [14-21] is 8 bytes — not standard MD5/SHA1, likely truncated or custom

### 4. Internal Code Info (from string analysis)
Leaked build path from binary:
```
Z:\buildagent\workspace\Bizarre\Blur\Release_PC\Game\code\amax\game\...
```
- Game engine name: **Mercury**
- Game layer name: **Amax** (this is why the emulator is called "Amax Emu")

---

## What We Need to Do Next

### Status
Decided to skip reverse-engineering the username hash function for now —
since we control the emulator, we don't need to decode it, just treat the
8 bytes as an opaque account ID and return success instead of error 05.
This unblocks testing without needing x64dbg work.

### Step 1: Minimal auth server — DONE (untested against real client)
`scripts/auth_server.py` — asyncio TCP server on port 3074. Parses the
auth request per the structure above and replies with a guessed success
packet (`07 00 00 00 00 0b 80 00 00 00 00`, i.e. the real error packet
with the status byte cleared to 00). Response format is unverified —
this is the thing to check by actually testing it.

### Step 2: Redirect traffic to our server (next — see below for hosts file info)
Edit Windows hosts file to point Blur's auth hostname at wherever
`auth_server.py` is running:
```
<our-vps-ip>   blur-pc-live.auth.mmp3.demonware.net
<our-vps-ip>   blur-pc-live.lsg.mmp3.demonware.net
```

### Step 3: Test login and observe — DONE, found the real blocker
Ran `auth_server.py` (with the 4-byte pre-ack fix) against the live client
over the WSL loopback-forwarded hosts redirect. Wireshark capture
(`capture.txt`) confirmed:
- Framing and timing now match the real server exactly (SYN/ACK, 4-byte
  hello gets no reply, 24-byte auth request, our 4-byte ack, our 11-byte
  guessed "success" response).
- The client ACKs our 11-byte response, then **immediately sends FIN** —
  no second connection to LSG is ever attempted. So the failure is at the
  auth stage, not LSG.

Cross-referenced against `blur_strings.txt` and found the actual cause:
```
95866  offset == BD_AUTH_TICKET_SIZE
95867  .\bdAuthTicket.cpp
95868  bdAuthTicket::deserialize
95869  Decoded auth ticket was the wrong size.
```
A real success response isn't a status byte — `bdAuthService::handleReply`
reads (in this rough order): an error code, an "Encrypted cd key", a
**user ticket**, and an **LSG ticket** (`bdAuthService.cpp`: "Failed to
read LSG ticket.", "Failed to read user ticket."). Each ticket is
deserialized via `bdAuthTicket::deserialize`, which asserts the decoded
size equals `BD_AUTH_TICKET_SIZE`. Our 7-byte body is nowhere near big
enough, so the client rejects it and shows "server not available" — this
is almost certainly the exact code path failing.

`BD_AUTH_TICKET_SIZE` and the ticket field layout aren't recoverable from
strings — need x64dbg for that (see Step 4).

Also noted a probable hash algorithm lead: `bdAuthUtility::getUserKey` and
`getLicenseKey` call `tigerHash.hash(...)` on the password/license code;
`getUserID` (same utility, same "Hash failed." error pattern) is likely
what produces the 8-byte username hash we captured, via **Tiger hash**
truncated to 8 bytes. Unverified — no Tiger implementation available in
the WSL sandbox to check `Tiger("test")` against `d0 9b 1d e4 4f c1 fe 68`
(no sudo/pip access in that environment). Not needed for the emulator
itself since we treat the hash as opaque, but worth confirming later if
we ever need to map hashes back to real usernames.

### Step 4: Find BD_AUTH_TICKET_SIZE and the ticket layout (x64dbg) — IN PROGRESS
`BD_AUTH_TICKET_SIZE = 0x80 = 128 bytes` — found 2026-07-18 via x32dbg static
analysis on the DODI repack build of Blur.exe. In `bdAuthTicket::deserialize`
(module offset `0x00CF83F8` region in this build — offsets will differ per
build/ASLR, re-find via string xref to "Decoded auth ticket was the wrong
size." if reusing this in a fresh debug session):
```
00CF840E   cmp dword ptr ss:[ebp-4], 80      ; offset == BD_AUTH_TICKET_SIZE
00CF8415   sete dl
00CF841B   push eax
00CF841C   call blur.D216A0                  ; assert handler
```
Confirmed by the exact strings pushed alongside it: `"offset ==
BD_AUTH_TICKET_SIZE"`, `".\bdAuthTicket.cpp"`, `"bdAuthTicket::deserialize"`.
`[ebp-4]` is the running read-cursor into the source buffer, incremented as
each field is deserialized — so a valid ticket blob must be exactly 128
bytes and every field read must succeed (no truncation) for this assert to
pass.

`deserialize` reads fields sequentially via a shared helper (`call
blur.CE0460`), each call passing: a type code (`push 3`, `push 4`, ...), a
destination pointer (`[ebp-64] + <struct offset>`, e.g. `0x80`, `0x83` seen
so far), and the running cursor (`[ebp-4]`). Each call returns success/fail
in `al`; failure funnels into the same "wrong size" error sink regardless of
which field failed — so that error string is a shared failure path, not
proof of a size mismatch specifically.

**Next:** scroll to the top of `deserialize` (above the block already
inspected) and catalog every `push <type_code>` / destination-offset pair
up to the `cmp ..., 80` — this gives the full field layout needed to build
a real 128-byte ticket blob (still open, mapping in progress).

Only needed for persistent per-account identity (stats, unlocks,
friends) is the username hash itself (getUserID) — separate from the
ticket structure work above, and lower priority.

#### Major structural discovery (2026-07-18): the response is a tagged bit-stream, not flat bytes
Padded `auth_server.py`'s response to 300+ zero bytes to see how far
`bdAuthTicket::deserialize` would get — it never got called at all (no
`blur.CE0460` hits with `maxSize==0x80`, confirmed via a filtered x64dbg
log breakpoint). Traced the real failure by breakpointing
`bdAuthService::handleReply` (find via string xref to `"bdAuthService"` /
`.\bdAuthService.cpp"` — earliest ref currently at module offset
`0x00CEA51A`, actual function prologue a bit above that, at `0x00CEA4B0`
in this session's build) and single-stepping from function entry.

`handleReply` reads a leading **"error code" as a UInt32** via
`bdBitBuffer` (not a raw byte read):
```
call blur.CE0E00   ; reader->readErrorCode(&result) — thiscall, ecx=reader obj
```
Inside `CE0E00`: reads an 8-bit/type-tag value via `blur.CE1130`
(`bdBitBuffer::readDataType`, expects type `8` = `UInt32` per the enum
below), then reads the actual 32-bit value via `blur.CE0EE0`. With our
all-zero padded body this decoded to `0x40` (64) — nonsense, because
`bdBitBuffer` is a **bit-packed, self-describing stream**, not
byte-aligned raw values.

Confirmed via `blur_strings.txt` (line ~95505): `bdBitBuffer`'s
constructor does `readBits(&m_typeChecked, 1)` — **the very first bit of
any bdBitBuffer stream** selects whether the rest of the buffer is
type-tagged (each value prefixed by a type tag that gets validated) or
raw. Get that single bit wrong and everything downstream decodes as
garbage — which is exactly what was happening.

Full `bdBitBuffer` type enum, recovered from the string table right after
`bdBitBuffer::readDataType` / `"Expected: %s , read: %s"` (line ~95573,
order reversed from dump order since `NoType` as index 0 makes sense as
an enum's first member — confirmed by `UInt32`==8 matching the "error
code" field we found expects type 8):
```
0  NoType            7  Int32              14 Float64
1  Bool              8  UInt32             15 RangeFloat32
2  Char8             9  Int64              16 MultiByteString
3  UChar8            10 UInt64             17 Blob
4  WChar16           11 RangedInt32        18 FullType
5  Int16             12 RangeUInt32        19 Unknown Type (sentinel)
6  UInt16            13 Float32
```

The overall reply is compared against a **fixed constant `0x2BC` (700
decimal)**, not `0`:
```
00CEA53D   cmp dword ptr ss:[ebp-10], 2BC
00CEA544   jne blur.CEB25F   ; taken with our garbage 0x40 value — skips
                              ; the entire reply-type dispatch/jump-table
                              ; at CEA570-CEA57D that would route into the
                              ; ticket/cd-key readers
```
This (not any assert) is why every prior test failed instantly with no
breakpoint firing — we were never supplying a real `0x2BC` value because
we weren't bit-packing it correctly.

Also note: the ticket field type codes found earlier (`3`, `4`, `0x18`,
`0x40`) do **not** match this `bdBitBuffer` enum (max valid value here is
19) — `bdAuthTicket::deserialize`'s field reader (`blur.CE0460`) is a
**separate** framework, most likely `bdByteBuffer` (also has its own
`readDataType`/type-checking, per
`"readArrayStart: Expected type %d but read type %d"` in the strings
dump) — a byte-oriented typed-field system layered *inside* the outer
bit-packed `bdBitBuffer` reply. So the full reply format is two
serialization layers stacked: `bdBitBuffer` (bits) wrapping
`bdByteBuffer`-style fields (bytes) for the actual ticket payloads.

**Next actionable step:** find and step through `bdBitBuffer::readBits`
itself (the lowest-level primitive both `readDataType` calls above it)
with a controlled/known input, to recover the exact bit-packing
convention (MSB vs LSB first, byte-boundary crossing behavior). Once that
one primitive is understood, we can hand-construct the `m_typeChecked`
bit + type tag + `0x2BC` value correctly, and likely reuse the same
routine to eventually build real ticket blobs too.

#### External resource found: Aib0t / Amax Emu author's write-ups repo
User cloned `write-ups/` (a personal RE blog repo by "Aib0t", who — per
the `blur-ads` write-up in that repo — is the actual author of Amax Emu).
Confirmed via `write-ups/reversing-network-related-stuff-101/03_where_to_start.md`,
which uses Blur as its own worked example and references a leaked
**Call of Duty Black Ops (2010) dedicated server binary with PDB debug
symbols** (~1.09GB, originally leaked 2014 on unknowncheats.me, mirrored
on se7ensins/nextgenupdate) as the standard reference sample for
Demonware 2.0-era titles. Black Ops (Nov 2010) and Blur (2010) are both
Demonware 2.0 — and since today's finding shows Blur's auth reply uses
generic `bdCore`/`bdContainers` SDK classes (`bdBitBuffer`,
`bdByteBuffer`) rather than game-specific code, these are much more
likely to exist unchanged in that leaked symbol set than game-specific
classes would be. User declined to pursue downloading it for now (opted
to keep going with live x64dbg on Blur directly) — worth revisiting if
the live approach stalls, since a symboled `bdBitBuffer`/`bdByteBuffer`
would settle the bit-packing question directly instead of reversing it
by hand.

#### Tooling change (2026-07-20): Claude Code now drives x32dbg directly via MCP
Set up `dariushoule/x64dbg-automate` (official PyPI package + x64dbg plugin)
so Claude Code (running in WSL) controls x32dbg on Windows directly —
breakpoints, stepping, register/memory read, disassembly — instead of the
manual screenshot-relay workflow used in every prior session. Requires WSL
mirrored networking (`networkingMode=mirrored` in `.wslconfig`) so WSL's
`localhost` reaches the Windows-hosted plugin. Full setup, gotchas (the
plugin's ZMQ ports are dynamic — re-check x32dbg's Log tab each session),
and reconnect steps are recorded in Claude's memory
(`x64dbg-mcp-bridge-setup`), not duplicated here since it's tooling, not a
Blur-specific finding. This unblocked the finding below, which had stalled
for a full session under manual stepping.

#### Bit-packing algorithm fully recovered (2026-07-20), correcting the earlier MSB-first guess
Using direct MCP-driven tracing, stepped live through the entire call chain
`bdAuthService::handleReply` (`blur.CEA4B0`) → `blur.CE0E00`
(`readErrorCode`) → `blur.CE1130` (`readDataType`/type-tag check) →
`blur.CE0EE0` — this last one is the actual bit-reading primitive (NOT
`blur.CE0BC0`, which earlier sessions couldn't reach by manual stepping;
`CE0BC0` turned out to be dead code for our test packets, gated behind a
flag that was never true in any test — see below).

**Reader object layout** (the `bdBitBuffer`-like reader passed as `ecx` throughout):
```
this+0x08   data buffer pointer
this+0x10   data size in bytes           (310 for our test payload)
this+0x18   capacity in bits             (2480 = 310*8)
this+0x1C   read cursor, in bits         (starts at 0, advances as bits are consumed)
this+0x20   overflow/error flag (byte)   (set to 1 if a read would exceed capacity)
this+0x21   a per-field flag (byte) gating whether blur.CE0BC0 (type-tag
            verification) runs for the current field — observed FALSE
            (0) for every test payload tried so far (both 0x00 and 0x80 for
            byte 0), so the mechanism that sets this flag is still
            unconfirmed. Not required for the algorithm below.
```

**Core bit-read primitive** (`blur.CE0EE0`, signature roughly
`bool ReadBits(void* dest, int numBits)`, thiscall):
```
byteIndex   = cursor >> 3
bitOffset   = cursor & 7              ; 0 = LSB of the byte, NOT MSB
chunkSize   = min(numBits, 8)         ; further reduced if bitOffset+chunkSize > 8
                                       ; (byte-boundary-spanning case, not yet
                                       ; fully mapped — only the common
                                       ; single-byte-fits case below is confirmed)
currentByte = data[byteIndex]
mask        = 0xFF >> (8 - chunkSize)
extracted   = (currentByte >> bitOffset) & mask
*dest       = extracted; dest++
cursor     += chunkSize
numBits    -= chunkSize
; loops (jmp blur.CE0F27) until numBits reaches 0
```
Each loop iteration writes one raw extracted byte to consecutive `dest`
addresses — for a 32-bit read this naturally reconstructs a little-endian
int in memory (dest[0] = least-significant chunk, matching x86 layout), so
no separate reassembly step exists; the shift-and-mask IS the whole
algorithm.

**Correction to prior sessions' notes:** earlier black-box testing (varying
byte 0 across `0x00`/`0x80`/`0xFF` and watching the decoded "error code" at
a checkpoint in `handleReply`) concluded bit 0 of the stream = MSB of byte
0. That conclusion was inferred from macro-level output only and is
**contradicted** by this primitive: `bitOffset = cursor & 7` then
`currentByte >> bitOffset` unambiguously reads **LSB-first** (bit 0 of the
stream = bit value `0x01` of byte 0, not `0x80`). The old macro-level
"clean vs garbage" pattern wasn't actually isolating one bit — it reflects
the combined effect of several packed fields at once. Trust this
disassembly-derived algorithm over any earlier empirical bit-flip
conclusion.

**Next actionable step:** use this exact algorithm to hand-compute the byte
sequence needed to encode `m_typeChecked` + a valid `UInt32` tag (8) +
`error_code = 0x2BC (700)`, construct it in `auth_server.py`, and verify via
the same MCP-driven checkpoint at `handleReply`'s `[ebp-10]` before moving
on to the ticket fields. Also still open: the byte-boundary-spanning read
path (`blur.CE0FE1` onward, not yet disassembled) and what actually
controls the `this+0x21` flag gating `blur.CE0BC0`.

#### First real gate cleared (2026-07-20): error_code = 0x2BC accepted, client proceeds past the initial check
Applied the algorithm above for real, with one correction found by testing:
the reader's `this+0x10` (data size) measured exactly 310 bytes against a
312-byte body (2-byte custom prefix + 310-byte padding) — meaning the
`bdBitBuffer`'s actual view starts **2 bytes into the response body**, not
at byte 0. Those first 2 bytes are consumed as some kind of header before
the bit-stream begins (contents/meaning not yet determined — currently
sending zero there).

With that correction, body layout that works:
```
[0-1]     00 00                zero (header, purpose unconfirmed, works as zero)
[2-3]     78 05                bit-packed: bit0=0 (m_typeChecked=false),
                                bits1-32 = error_code 0x2BC (700), LSB-first
[4-311]   00 ...                zero padding
```
Verified live via MCP: `handleReply`'s `[ebp-10]` reads back as
`BC 02 00 00` = `0x000002BC` = 700 exactly, and stepping through the gate
at `0xCEA53D` (`cmp [ebp-10], 2BC` / `jne blur.CEB25F`) confirmed the jump
is **not** taken — execution falls through into the reply-type
dispatch/jump-table for the first time this project. This is the furthest
the client has ever gotten past error-code parsing.

**Next actionable step:** step through the dispatch/jump-table right after
`0xCEA54A` to find what it reads next (almost certainly the "Encrypted cd
key" field per `bdAuthService.cpp` strings, then user ticket, then LSG
ticket) and apply the same encode-verify loop to each.

#### `replyType` dispatch investigated (2026-07-20) — byte-0-as-type theory ruled out, real mechanism still unknown
The jump table at `0xCEA570`/`jmp [eax*4+CEB2C8]` dispatches on a byte at
`handleReply`'s `[ebp+8]` (an argument, not something in our bit-stream
body). Valid cases: `replyType` in `{11,13,15,17,21,25,27}` each get a
distinct handler; `{12,14,16,18,19,20,22,23,24,26}` share one generic
handler (case index 7); everything else (including our observed value,
`0`) falls to `blur.CEB235`. **Confirmed `CEB235` is a genuine failure
path** — it unconditionally calls the assert/log helper `blur.D21870`
before returning, same as the sibling failure path `CEB25F` (the
error_code-mismatch handler). So a valid `replyType` is required to
proceed; `0` is not a benign default.

Case `replyType=11` (`0xCEA584`) is notable: it reads a value via
`blur.CE0E00`, then reads exactly **1024 bits (128 bytes)** via
`blur.CE0EE0` — almost certainly the raw ticket blob, matching
`BD_AUTH_TICKET_SIZE=0x80` from the 2026-07-18 finding. Strong candidate
for "the success/ticket case" once `replyType` can actually be controlled.

`handleReply`'s caller (`blur.CE9B90`, calls `handleReply` at `0xCE9C3F`)
gets this byte from its own local `[ebp-D]`, which is set via a call to
`blur.CF48D0(connectionObj, &replyTypeOut, &readerOut)` — a large,
still-only-partially-read function (400+ bytes disassembled so far,
0xCF48D0–0xCF4AF9) that does socket-level receive buffering (peek/recv
calls: `CF5FD0`, `CF61D0`, `D208F0`, `D86300`, `CF6230`, plus what looks
like a **separate nested connection-state machine** — `[connObj+0x24]`
cycling through states 0-4 — unrelated to message type, easy to
mis-attribute if skimming).

**Ruled out:** byte 0 of our response body is NOT `replyType` directly.
Set a hardware write-breakpoint on the exact stack slot that becomes
`[ebp-D]` and caught the real write live: it arrives via a `rep movsd`
bulk copy whose **source buffer was entirely zero for 128 bytes** around
the relevant offset — none of our sent bytes (tried `0x0B`/`0x00`) were
anywhere in that source region. So this copy is most likely a local
struct zero-init, not a parse of our data. Given every other field in this
protocol turned out to be `bdBitBuffer`-packed rather than raw-byte, the
leading hypothesis is that `replyType` is *also* a bit-packed field read
somewhere in the unread ~portion of `CF48D0`, not a fixed-offset raw byte
— not yet confirmed.

**Session note:** doing this investigation via hardware breakpoints on
computed stack addresses is fragile if the debuggee process restarts
between attempts (Windows tends to reuse the same stack address range for
the new process, causing the old breakpoint to fire on unrelated writes —
happened twice this session, each time looking like x32dbg was "stuck" on
F9). Not an issue if the same process instance survives across retries
(just retry login in the same running game window) — only relaunching
Blur.exe invalidates it.

**Next actionable step:** either (a) keep reading `CF48D0`'s disassembly
past `0xCF4AF9` looking for a `bdBitBuffer`-style read (a call matching
the `CE0EE0`/`CE1130` pattern) that writes through the `[ebp+8]` output
parameter, or (b) set a fresh hardware write-breakpoint per-session (same
process, no relaunch) at the top of `CF48D0` to catch the *real* write if
one happens later in the function than what's been read so far.

#### Major detour (2026-07-22): found and used the "Amax Emu" mod to capture real server traffic — replyType mystery resolved
Found a Nexus Mods page for Blur with a client mod bundling `amax_auth.asi`
(a Rust DLL, built with `retour` for hooking, `rustls`/`tungstenite`/
`aws-lc-rs` for crypto). String analysis of the binary (module paths embed
directly, since Rust panics include source paths) revealed the real
architecture: it hooks **`bdPlatformStreamSocket`'s methods directly**
(`create`/`connect`/`sent_to`/`receive`/`close`, plus a `ws.rs` — see
`blur_dll2\src\bd_platform_stream_socket\*.rs` in the strings dump) and
tunnels the bytes over a WebSocket to their own server, `master.amax-emu.com`,
instead of raw TCP to Demonware. Blur's own code still builds/parses the
exact same `bdBitBuffer`-packed bytes we've been reversing — the mod just
moves *where* those bytes travel. A separate internal system, **"porygon"**
(`prg_auth.rs`, `prg_hwid.rs`), authenticates the mod itself against
`prg-client.amax-emu.com` via HWID + account login (account created on
their website, gives you in-game login credentials).

The account's download bundle included a full replacement `Blur.exe`
(13,738,496 bytes, dated 2013-07-21 — a different, much smaller build than
the DODI repack's 28,898,304-byte exe) plus a `cache/gamedata.pak` +
`.sig` that turned out **byte-identical** (same SHA-256) to the DODI
repack's own copy — so only the exe itself mattered; the mod's hardcoded
memory-patch offsets (`amax-redirect.cfg`) and hook targets are specific to
this exact build. Backed up the original DODI exe, dropped in the new one
plus the mod's loader files (`d3d9.dll`, `discord-rpc.dll`, `lua5.1.dll`,
`amax/`), same layout as the official install guide.

**Huge, unexpected confirmation:** despite being a different file
(different size/hash/date), the new build's `.text`/`.rdata` sections are
laid out **identically** to the DODI repack's — `bdAuthService::handleReply`
disassembles byte-for-byte the same at `blur.CEA4B0`, same stack-cookie
setup, same `[ebp-0x10]` zero-init for `error_code`. Every previously-found
address (`CEA4B0`, `CE0EE0`, `CE1130`, `CE0E00`, the `CEA53D` gate, the
`CEB2C8`/`CEB2E8` jump tables) carried over with zero rework needed.

Relaunched x32dbg on the new exe, reconnected the MCP bridge, resumed
through a long chain of TLS-callback breakpoints (d3d9.dll → shlwapi.dll →
amax_auth.asi ×2 → lua5.1.dll → lua_hooks.asi → graphics driver DLLs —
disabled `[Events] TlsCallbacks` via `set_setting` partway through since
graphics-driver TLS noise was unbounded), let the game reach the real
entry point, then had the user actually log in in-game with their
amax-emu account against the live `master.amax-emu.com` server.

**The `bdAuthService::handleReply` breakpoint (`CEA4B0`) hit with real
data for the first time ever.** Since the breakpoint fires *before* the
function prologue runs, the raw call arguments were still sitting on the
stack unprocessed:
```
[esp+4]  (-> [ebp+8])  = 0x0000000B = 11         <- replyType
[esp+8]  (-> [ebp+0xC]) = 0x1ECD2CE8              <- reader object pointer
```
This resolves the entire replyType investigation from the previous
session: **replyType is simply passed as a plain stack argument to
`handleReply`** by its caller — not embedded in the response body at some
fixed offset (which is why every earlier attempt to control it via byte 0
of our fake response failed). And critically: **the real server actually
used replyType=11**, confirming the earlier static-analysis guess that
case 11 (the one reading a full 1024-bit/128-byte blob, matching
`BD_AUTH_TICKET_SIZE`) is the real ticket/success path.

Read the reader object at `0x1ECD2CE8` — matches our documented layout
from 2026-07-20 exactly: data ptr at `+0x08` (`0x16AA9710`), size at
`+0x10` (`0x10A` = 266 bytes), capacity at `+0x18` (`0x850` bits =
266×8 ✓), cursor at `+0x1C` already at 1 bit (the `m_typeChecked` bit,
consumed by the reader's constructor before `handleReply` even starts
reading fields). Dumped the full 266-byte buffer — a genuine, complete,
real "success" auth reply, saved verbatim to
`scripts/captured_real_success_reply.py` (also `.bin`).

Decoded the first field with the confirmed bit-reader algorithm
(`scripts/decode_captured_reply.py`): `m_typeChecked = 0`, then
`error_code = 0x2BC` (700) — **byte-for-byte identical** to our own
hand-derived encoding from 2026-07-20 (`78 05` bit pattern), which
independently confirms that earlier reverse-engineered bit-packing
algorithm was exactly correct. Everything after that (~262 bytes) decodes
to high-entropy data with no obvious sub-field structure (a raw 32-bit
"value" read attempt produced `0x264c1d`, not a plausible length/count) —
consistent with this actually being the "Encrypted cd key" + user ticket +
LSG ticket that `bdAuthService.cpp`'s strings describe: genuinely
encrypted payload, not something we can subdivide by guessing chunk sizes
from statistical inspection alone.

**Reframing for our own emulator:** since our own server will implement
*both* the auth and LSG sides, we don't actually need to replicate
Demonware's real ticket encryption — only the wrapper format (already
solved: `m_typeChecked` bit, `error_code`, `replyType`, per-field bit
packing) and the correct field *sizes*/boundaries, so our own
self-consistent opaque ticket bytes get accepted structurally by the
client. The remaining open question is exactly where the cd-key field
ends and the 128-byte user ticket begins (and where the LSG ticket sits)
— needs either live single-stepping through the real `CE0E00`/`CE0EE0`
calls during a fresh capture (the debugger breakpoint at `CEA4B0` is still
in place and reusable — just have the user log in again, single-step
instead of `go()`-ing straight through), or may not matter at all if we
just pick fixed sizes for our own emulator's tickets matching
`BD_AUTH_TICKET_SIZE` and whatever the surrounding structure requires.

**Detour explicitly closed out, same session.** Testing the mod against
its live server unexpectedly landed in a real multiplayer match with other
Amax Emu users. That made clear this approach risked turning into a
dependency on their infrastructure, which runs against the whole point of
this project (an independent server for a small friend group). Decision:
no further live captures, logins, or play sessions against
`master.amax-emu.com`/`prg-client.amax-emu.com`. `amax-emu-4-1-1751578882/`
and `blur_12/` stay in the repo as already-mined static reference material
only. Everything from here builds our own standalone auth + LSG server,
using our own self-consistent (not Demonware-compatible) ticket format.

### Step 5: Build out the rest of the emulator
Once auth round-trips correctly:
1. Handle whatever comes after auth (password packet, or straight to LSG)
2. Handle LSG — lobby list, session creation, matchmaking

### Step 6: Figure out gameplay traffic
Is in-game traffic peer-to-peer or relayed through Demonware servers?
Capture traffic during an actual game session (once auth works) to find out.

---

## Files
- `blur_strings.txt` — full strings dump of Blur.exe
- `blur_analysis.txt` — grep output for servers, IPs, middleware, ports
- `blur_online_attempt.txt` — Wireshark capture (text export), username "test"
- `blur_online_attempt_capture.pcapng` — same capture, raw pcapng
- `scripts/auth_server.py` — minimal stand-in auth server (see Step 1 above)
- `scripts/captured_real_success_reply.py` / `.bin` — real 266-byte auth
  success reply captured live from amax-emu's server 2026-07-22 (see Step 4
  "Major detour" section above)
- `scripts/decode_captured_reply.py` — bit-level decoder for the above,
  using the confirmed `bdBitBuffer` algorithm
- `amax-emu-4-1-1751578882/` — the Amax Emu client mod (from Nexus Mods),
  used as prior-art reference; not our own code
- `blur_12/` — the exact `Blur.exe` build + `cache` the amax-emu account
  provides, required for the mod's hardcoded offsets to work

(Older notes referenced `blur_login_attempt2.txt`/`3.txt` and a
`whois_output` file — these aren't in the repo; only the files above
currently exist.)

---

## Known Unknowns
- Exact hash algorithm used for username
- Whether password is sent separately or combined with username hash
- Whether gameplay is P2P or server-relayed
- What the LSG protocol looks like (we've only seen auth so far)
- Whether Amax Emu is public or who runs it
