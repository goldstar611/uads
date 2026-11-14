# uads vs UA_source — network implementation findings

Comparison of the Python dedicated server (`net_classes.py`, `net_messages.py`, `uads.py`,
`net_games.py`) against the C++ engine (`src/netlib/*`, `src/windp.cpp`, `src/yw_net.cpp`,
`src/yw_net.h`, `src/yw_func2.cpp`).

All wire formats verified byte-for-byte unless noted below.

---

## 1. `UAMsgWelcome` payload is 1 byte too long (breaks the client message walk)

- `net_classes.py:357,385` sends payload_length `0x14` (20 bytes: `faction(H) + ready(B) + cd(B)`).
- Engine defines `uamessage_welcome` as `fraction(int16) + rdy(uint8)` = **19 bytes**
  (`yw_net.h:276-281` — the `cd` byte is commented out).
- Clients walk UA messages back-to-back inside one `USR_MSG_DATA` payload using
  `sizeof(struct)` (`yw_net.cpp:3346-3351`). After a 20-byte welcome the walk resumes at
  offset 19 → garbage msgID → "unknown message" errors / corrupt lobby state
  (fraction selection, `Welcomed` flag) on every join.
- **Fix:** drop the `cd` byte, payload `0x13`.

## 2. Direct (`cast == 0`) messages are silently dropped

- `uads.py:409` — `if packet.packet_type == ... and packet.packet_cast:` only relays
  broadcast (`cast=1`). The C++ server routes `cast=0` to the target user by ID
  (`server.cpp:406-416`).
- Everything peers send directly — `UAMSG_PONG`, host→joiner `WELCOME`, `UAMSG_CRC`,
  `UAMSG_KICK` — dies at the server.
- **Fix:** look up the target player by `packet_to` and forward.

## 3. Relayed packets keep the sender's seq id → GARANT packets dropped / retransmitted forever

- The C++ server re-wraps each relayed packet with the *receiving* user's own per-target
  sequence number (`server.cpp:412`, `usr->GetSeq()`) and that user's channel.
- `uads.py:410-412` forwards the packet verbatim.
- Clients dedupe/confirm GARANT packets keyed by `(server-addr, seq)`; the server address is
  the same for everyone, so two different players' GARANT packets with colliding seqs are
  treated as duplicates by a receiver and **dropped**.
- Also, receivers send `SYS_MSG_DELIVERED` back to the server, which is ignored, so the
  original sender never gets confirmed and retransmits every GARANT broadcast for up to
  15 s (`TIMEOUT_GARANT`, `types.h:58`) → duplicate storms → "net info overkill" problems
  (`yw_net.cpp:3187-3196`).
- **Fix:** assign a fresh seq per receiving client; map DELIVERED confirmations back to the
  original sender.

## 4. `SYS_MSG_RETRY` (0x8) not handled

- `net_classes.py:data_to_class` raises on any unknown system message. When a multipart
  part is lost the C++ client sends RETRY (seq, from, upto — 12 bytes) after
  `TIMEOUT_PENDING_GARANT` ≈ 3.3 s (`inpacket.h:201`, `client.cpp:164-171`).
- Server throws `DataToClassException` → the packet never completes → desync for all large
  messages (`UAMSG_UPDATE`, `REORDER`, `VHCLDATA`).
- **Fix:** parse RETRY and re-request/re-send the missing range.

## 5. Multipart reassembly only works for in-order, lossless arrival

- `Part.__init__` (`net_classes.py:43`) allocates `bytearray(full_size)` from the
  *constructor argument* (0 when parsing from the wire), so `add_part_data` slice-assign
  appends at the end instead of writing at `offset` — out-of-order parts are concatenated
  in arrival order → corrupted reconstruction.
- `is_complete()` accumulates received byte count, so duplicate parts double-count →
  premature completion with holes.
- No timeout / no retry request: an incomplete packet sits in `multi_part_packets` forever.

## 6. Never sends `USR_MSG_SES_USERJOIN` (0x40)

- On join the C++ server broadcasts `NetUsrJoin` to the other session members
  (`server_session.cpp:154-158`) and sends the user list **only to the newcomer**
  (`server_session.cpp:172`).
- `windp.cpp:469-478` turns USERJOIN into `RECVMSG_CREATEPLAYER`, which is the trigger for
  existing peers to send `WELCOME` / `LOBBYINIT` / `CRC` to the joiner
  (`yw_net.cpp:3202-3235`) and for lobby bookkeeping.
- uads only sends a full `NetUsrSessionList` to everyone — that maps to `EVENT_USER_LIST`,
  which does **not** fire `RECVMSG_CREATEPLAYER`.
- Result: mid-game joiners are never welcomed/initialized by peers.

## 7. Timestamp units wrong for `UAMSG_REQPING`

- `uads.py:107-110` computes game time in **seconds**; the engine compares against
  `_timeStamp` in **milliseconds** (`yw_net.cpp:2977`; logs divide by 1000).
- Also the server's REQPING carries `owner=1`, which refreshes
  `netPlayers[1].LastMessageTime` on every client (`yw_net.cpp:1039-1042`) — masking
  dead-player detection for that slot.
- The engine's own peers already ping each other (`yw_net.cpp:4044-4058`); the server
  should probably not send REQPING at all, or must use ms.

## 8. Unhandled / ignored system opcodes

Parsed but never answered (all fall into `DataToClassException` noise or silence):

| opcode | meaning | note |
|---|---|---|
| `SYS_MSG_LIST_GAMES` 0x30 | client requests session list | needed if `has_lobby=1` |
| `SYS_MSG_SES_CREATE` 0x43 | create session | |
| `SYS_MSG_SES_JOIN` 0x40 (request) | join session by ID | |
| `SYS_MSG_SES_LEAVE` 0x41 | leave session | |
| `SYS_MSG_SES_SHOW` 0x44 | open/close session | |
| `SYS_MSG_SES_KICK` 0x45 | leader kicks user | |
| `SYS_MSG_RETRY` 0x8 | retransmit request | see §4 |

Never sent by uads:

- `SYS_MSG_SES_LEAD` (0x42) — irrelevant in this engine build (see §9), but `cLeader`
  stays false so clients can't Show/Close/Kick the session.
- `SYS_MSG_SES_ERR` (0x4F) / `SYS_MSG_CONNERR` (0x81) — no error reporting.
- Minor: server answers client `SYS_MSG_PING` with `DELIVERED`; the C++ client expects a
  PING echo (`client.cpp:142-153`). The stray DELIVERED can spuriously confirm an
  unrelated pending GARANT.
- `UAMSG_CD` (+42) doesn't exist in the C++ enum (commented out, no handler) — sending it
  is pointless; receiving it is harmless.

## Verified-correct (no action needed)

Packet header layout (flags/seq/channel at 0/1/5, data at 6, PART fsize/offset at 6/10/14),
`USR_MSG_DATA` framing (from u64 / cast u8 / to u64 / sz u32), SES_JOIN
`leader u8 | sesID u64 | szStr("level|host|date")`, CONNECTED (`has_lobby u8 | id u64 |
szStr name`), USERLEAVE (`id u64 | type u8`), USERLIST (count u32 + per-user
`id u64 | szStr name`), and the sizes of `uamessage_load`, `ready`, `fraction`,
`message`, `ping`, `syncgame`, `viewer`, `crc` payloads.

Faction bitmasks in `net_games.py` (1/2/4/8) match `World::OWNER_*_BIT`.
Session name `level|host|date` parsing matches `windp.cpp:1167-1179`.

---

## 9. THE "no real host" problem (lobby-less architecture)

### Symptom

Two users join the uads server fine, but the client eventually drops — there is no "real
host" because both clients "joined" instead of one "hosting" and one "joining".

### Root cause: every client ends up with `isHost == false`

The engine decides who may start/control the session entirely on the client-side flag
`UserData::isHost`. The only code paths that ever set it to `true`:

1. **Local hosting mode** — `SetMode(true)` creates `ZNDSingle` (a local server+client in
   one process); `yw.cpp:2166-2167` and `yw_func2.cpp:3678,3993` set `isHost = true`.
2. **Lobby session-select screen** — only reachable when the server answers
   `CONNECTED` with `has_lobby = 1` (`windp.cpp:164-167`, `yw_func2.cpp:2114-2121`).
   Then button 1201 ("create session") or Return-on-empty-list sets `isHost = true`
   (`yw_func2.cpp:3639, 3976`).
3. **`RECVMSG_HOST`** (`yw_net.cpp:3296-3297`) — **dead code** in this build:
   `NC_STACK_windp::Recv()` (`windp.cpp:441-525`) has no case for
   `EVENT_SESSION_LEAD`, so even a `SYS_MSG_SES_LEAD` packet from the server can never
   set `isHost`. Sending SES_LEAD from uads would be ignored.

The lobby-less flow (`has_lobby = 0`, no session list) goes straight to
`JoinLobbyLessGame()` (`yw_func2.cpp:2122-2124`), which unconditionally does
`isHost = false` for **every** client (`windp.cpp:1201`). Nobody can ever become host.

### What breaks without a host

- **Nobody can press START.** In the INSESSION screen the START button (1201) is only
  enabled for the host; non-hosts are locked into "WAIT" mode with 1201 disabled
  (`yw_func2.cpp:4380-4399, 4546-4582`). The host's START is what calls
  `sub_46DC1C()` (`yw_func2.cpp:3737-3753`), which broadcasts `UAMSG_LOAD` and sets
  `ACTION_NETPLAY` locally (`yw_func2.cpp:1128-1148`).
- uads works around this by sending `UAMSG_LOAD` itself from the server (`uads.py:245-266`
  via the chat `!start` command) — that's why two clients *can* get into the game at all.
- **But every host-only safety net is dead afterwards:**
  - Straggler kick after loading / force-start: `if (... && usr->isHost)` sends
    `UAMSG_KICK` and starts without them (`yw_net.cpp:3988-4010`); non-hosts just show
    **"WAITING FOR HOST"** forever (`yw_net.cpp:4022-4029`).
  - Latency problem resolution: on `netProblem == 1` (latency ≥ 7000 ms) only the host
    broadcasts `UAMSG_ENDPROBLEM` (`yw_net.cpp:2981-2993, 3787-3795`); without a host the
    problem never resolves (`netProblem=3` countdown → `STATE_ABORTED` → drop,
    `yw_net.cpp:3799-3806`).
  - Score broadcast: only `isHost` sends `UAMSG_SCORE` (`yw_net.cpp:3147-3163`).
  - Session lock/unlock (`blocked` / `LockSession`) is host-gated (`yw_func2.cpp:4109-4131`).
- **Interaction with §7:** uads' broken (seconds-based) REQPING timestamps make the engine
  compute absurd latencies and trigger `netProblem = 1` storms — and with no host there is
  no one to resolve them. This combination is a very likely cause of the observed drops.

### Possible fixes

1. **Make the first client go through the lobby path:** uads answers `CONNECTED` with
   `has_lobby = 1`, does not auto-join, and answers `SYS_MSG_LIST_GAMES` (0x30) with the
   list of open games. The first player then sees an empty list and the engine itself
   sets `isHost = true` (`yw_func2.cpp:3976`); later players pick the game from the list
   and join normally (`SYS_MSG_SES_JOIN`). Caveat: `windp.cpp`'s
   `JoinSession()`/`EnumSessions()` are stubs (`windp.cpp:241-268`), so this path needs
   testing; and `AfterMapChoose()` case 2 (`windp.cpp:756-758`) is an empty stub for
   mode-2 clients.
2. **Engine patch (cleanest):** wire `EVENT_SESSION_LEAD` into `NC_STACK_windp::Recv()` as
   `RECVMSG_HOST` (it already exists in `yw_net.cpp:3296`), then have uads send
   `SYS_MSG_SES_LEAD (0x42) { is_leader = 1 }` to the elected player. The engine will set
   `isHost` on that peer and all host-gated logic (START, kicks, problem resolution,
   scores) comes alive. Note the engine's own `LockSession`/`ShowSession` are stubs in
   this build, but those are optional.
3. **Server-side simulation of host duties:** keep `has_lobby = 0`, but have uads take
   over the host-only duties itself: send `UAMSG_KICK` for stragglers, resolve
   `netProblem` by broadcasting `UAMSG_ENDPROBLEM` when clients stall, keep timestamps in
   ms (§7), and stop triggering latency problems itself. Fragile, but requires no engine
   changes.

Recommended: option 2 (SES_LEAD + Recv patch) combined with fixes §1-§7.

## 10. Concatenated UA messages in one USR_MSG_DATA payload (engine commit 864f389)

The engine's broadcast path (windp.cpp QueueBroadcast/FlushBroadcastBuffer)
memcpy-concatenates several queued `uamessage_*` structs into one buffer and
sends it as a single GARANT datagram. Each client's receiver walk
(yw_net.cpp RECVMSG_NORMAL -> yw_handleNormMsg loop) steps through the stream
using `sizeof(uamessage_*)`.

Consequences for uads: `data_to_class()` parses only the FIRST message and
drops the rest, so e.g. a [VIEWER(28)+SYNCGM(52)] flush (host's post-load
"Sent a READY TO PLAY", yw_net.cpp ypaworld_func179) or a triple
UAMSG_FACTION stream (88-byte packet, real capture) loses everything after
the first message for the server's own bookkeeping.

Fix in uads:
- net_classes.UA_MSG_SIZES + net_classes.split_usr_data(raw): walk the
  payload by authoritative sizes (verified by compiling a sizeof-dump against
  the real yw_net.h: uamessage_base=16, load/newLeader? see table; welcome=20,
  logmsg=44, score=44, vhclData=24). Unknown/variable messages (VHCLDATA_I/E,
  UPDATE, REORDER) are not in the table -> walk stops, which is safe because
  the engine sends those as standalone broadcasts.
- sub-datagrams are rebuilt as: original 24-byte transport+USR header with
  adjusted sz, then parsed via data_to_class. Extra messages flow into
  packet_received(extra_messages=...) and are processed by handle_message()
  alongside the first message; relay still uses the original packet verbatim.

Note: the engine's own receiver uses the same sizeof table, so engine peers
walk these streams fine; only uads' old single-message parse was broken.

## 11. BUILDINGVHCL wire size is 528, not 272 (vec3d is double)
Root cause of the "Waiting for Player" black screen after !start: the VM
tarball carried `UAMSG_BUILDINGVHCL: 272` in UA_MSG_SIZES. yw_game.cpp
broadcasts sizeof(uamessage_bldVhcl): bldVhcl entry = id(u32) + base
vec3d(24, double) + pos vec3d(24) + protoID(i16) + bldp(2) = 56, padded to
64 (struct alignment 8 because of double); 8 entries -> 512 + base 16 =
528. With 272 the walk stopped mid-struct (msg_id=0 from the zeroed
entries 1..7) at payload offset 300 and silently dropped the remaining
256 bytes of BUILDINGVHCL plus the trailing SYNCGM(52) -- so clients never
got SYNCGM and stayed on "Waiting for Player".

Fixed alongside:
- UAMSG_IMPULSE stays 88 (NOT 80): vec3d forces 8-byte alignment, so there
  is 4 bytes padding after `id` and 4 after `dir_len`:
  16 + 4 + 4pad + 24 + 4 + 4 + 24 + 4 + 4pad = 88. An intermediate 80-byte
  guess caused real bad-splits (dumped datagrams 20261113_21*): the walk
  stopped 8 bytes short of the next message and dropped the SETSTATE /
  VHCLDATA messages that follow enemy impulse broadcasts (visible as enemy
  weapons not appearing on the peer). Verified all 4 dumps now walk cleanly:
  IMPULSE(88) + VHCLDATA_I/E(rest).
- UAMSG_VHCLDATA_I/E now consume the REST of the payload: the engine's
  receiver does `szmsg = msg->_data.size()` (yw_net.cpp:1473/1497), so
  VHCLDATA is always the last message in a datagram; trusting hdr.size
  (offset 18) was wrong.
- All other sizes re-verified against yw_net.h with vec3d=24B (OK).
- split_usr_data's leftover-report used `m.msg_id` (AttributeError,
  swallowed by the outer except -> returned [] silently); now
  `getattr(m, "message_id", None)`.
- Bad splits now dump the full raw datagram to `bad_splits/` (or
  $UADS_BADSPLIT_DIR) with _dump_bad_split for offline decoding via
  utils/decode_hex.py (also added: prints framing + UA ids + hex dump of
  the unaccounted tail; utils/make_flush_test.py builds the synthetic
  636B flush for tests).

Test: VIEWER(28) + BUILDINGVHCL(528) + SYNCGM(52) = 608-byte payload now
walks cleanly into 3 packets with no UADS-SPLIT warning.
