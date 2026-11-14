# uads vs UA_source — network implementation findings

Comparison of the Python dedicated server (`net_classes.py`, `net_messages.py`, `uads.py`,
`net_games.py`) against the C++ engine (`src/netlib/*`, `src/windp.cpp`, `src/yw_net.cpp`,
`src/yw_net.h`, `src/yw_func2.cpp`).

All wire formats verified byte-for-byte unless noted below.

Engine-side findings (engine bugs/quirks, engine instrumentation) now live in
`CLIENT-CHANGES.md`.

---

## Open uads issues

### A. `SYS_MSG_RETRY` (0x8): parsed but no retransmit logic

`net_classes.py:data_to_class` parses RETRY (seq, from, upto), so the packet no longer
throws `DataToClassException`. But uads does not act on it: when a multipart part is
lost the client keeps waiting (engine sends RETRY after `TIMEOUT_PENDING_GARANT`
≈ 3.3 s, `inpacket.h:201`). Large messages (`UAMSG_UPDATE`, `REORDER`, `VHCLDATA`)
can stall for the rest of a lossy session. Fix: on RETRY re-broadcast the missing
byte range from the reassembly buffer.

### B. Multipart reassembly residuals

`Part` writes parts at their offsets now (bytearray(full_size)), but:

- `is_complete()` counts received bytes — duplicate parts double-count → premature
  completion with holes. Track per-offset coverage instead.
- No timeout / no retry request: an incomplete packet sits in `multi_part_packets`
  forever (client will send RETRY — see A).

### C. `UAMSG_REQPING` timestamp units

`uads.py send_ping` sends game time in **seconds**; the engine compares against
`_timeStamp` in **milliseconds** (`yw_net.cpp:2977`). Also `owner=1` refreshes
`netPlayers[1].LastMessageTime` on every client, masking dead-player detection for
that slot. The engine's peers ping each other already (`yw_net.cpp:4044-4058`) —
uads should probably not send REQPING at all, or use ms.

### D. Unanswered system opcodes

Parsed but never answered:

| opcode | meaning | note |
|---|---|---|
| `SYS_MSG_LIST_GAMES` 0x30 | client requests session list | needed only if `has_lobby=1` |
| `SYS_MSG_SES_CREATE` 0x43 | create session | |
| `SYS_MSG_SES_JOIN` 0x40 (request) | join session by ID | |
| `SYS_MSG_SES_LEAVE` 0x41 | leave session | |
| `SYS_MSG_SES_SHOW` 0x44 | open/close session | |
| `SYS_MSG_SES_KICK` 0x45 | leader kicks user | |
| `SYS_MSG_RETRY` 0x8 | retransmit request | see A |

Never sent by uads:

- `SYS_MSG_SES_LEAD` (0x42) — see "no real host" below; sending it is ignored by
  this engine build (`NC_STACK_windp::Recv()` has no `EVENT_SESSION_LEAD` case).
- `SYS_MSG_SES_ERR` (0x4F) / `SYS_MSG_CONNERR` (0x81) — no error reporting.
- Minor: server answers client `SYS_MSG_PING` with `DELIVERED`; the C++ client
  expects a PING echo (`client.cpp:142-153`). The stray DELIVERED can spuriously
  confirm an unrelated pending GARANT.
- `UAMSG_CD` (+42) doesn't exist in the C++ enum (commented out, no handler).

### E. THE "no real host" problem (lobby-less architecture)

Every client ends up with `isHost == false`: the lobby-less flow
(`has_lobby = 0`) goes straight to `JoinLobbyLessGame()` which unconditionally does
`isHost = false` (`windp.cpp:1201`). `RECVMSG_HOST` (`yw_net.cpp:3296`) is dead code —
`NC_STACK_windp::Recv()` (`windp.cpp:441-525`) has no case for `EVENT_SESSION_LEAD`.

Consequences: nobody can press START (uads works around it with `!start` →
`UAMSG_LOAD`), and all host-only safety nets are dead afterwards: straggler kick /
"WAITING FOR HOST" (`yw_net.cpp:3988-4029`), latency-problem resolution
(`netProblem=1` needs a host to broadcast `UAMSG_ENDPROBLEM`,
`yw_net.cpp:2981-2993` — interacts badly with issue C), score broadcast
(`UAMSG_SCORE`), session lock/unlock.

Possible fixes:

1. **Lobby path:** answer `CONNECTED` with `has_lobby = 1` and implement
   `SYS_MSG_LIST_GAMES`; the first player then "creates" a session and gets
   `isHost = true` (`yw_func2.cpp:3976`), joiners pick the game from the list.
   Caveat: `JoinSession()`/`EnumSessions()` are stubs in `windp.cpp:241-268` —
   needs testing.
2. **Engine patch (cleanest):** wire `EVENT_SESSION_LEAD` into
   `NC_STACK_windp::Recv()` as `RECVMSG_HOST`, then have uads send
   `SYS_MSG_SES_LEAD (0x42) { is_leader = 1 }` to the elected player. See
   CLIENT-CHANGES.md.
3. **Server-side simulation:** uads takes over the host-only duties itself
   (kick stragglers, resolve `netProblem`, ms timestamps, no self-triggered
   latency problems). Fragile.

---

## Resolved (for the record)

- **WELCOME payload 19 bytes** (`net_classes.py`): engine commit `330eb51`
  (2022-11-07) removed the `cd` byte; uads now sends payload `0x13`
  (`faction(H) + rdy(B)`). Was 20 → message-walk desync on every join.
- **Direct (`cast == 0`) routing** (`uads.py packet_received`): cast=0 packets are
  routed by `packet_to`; previously only broadcasts were relayed, killing
  host→joiner WELCOME / CRC / KICK / PONG.
- **Fresh seq per relayed packet** (`uads.py relay_packet`): each relayed message is
  re-framed with the *receiving* client's own seq (fixes GARANT dedup collisions)
  and the server answers inbound GARANT with `SYS_MSG_DELIVERED` so senders stop
  retransmitting (fixes duplicate storms / "info overkill").
- **Concatenated UA messages** (engine commit `864f389`): `split_usr_data` +
  `UA_MSG_SIZES` walk multi-message payloads; extras reach `handle_message` via
  `packet_received(extra_messages=...)`. Sizes verified against `yw_net.h`
  (BUILDINGVHCL=528 not 272, IMPULSE=88 not 80, VHCLDATA_I/E consume the rest,
  vec3d = 24 B doubles with 8-byte alignment). Root cause of the "Waiting for
  Player" black screen and of "enemy weapons not appearing". Bad splits dump raw
  datagrams to `bad_splits/` (`$UADS_BADSPLIT_DIR`), decode with
  `utils/decode_hex.py`; `utils/make_flush_test.py` builds a synthetic flush.
- **Multipart offsets**: `Part` now allocates `bytearray(full_size)` and
  `add_part_data` writes at `offset` (was: append in arrival order). Residuals
  tracked as issue B.
- **Stats/visibility**: per-player RX/TX counts by message id (with names) print
  every 10 s; undecodable datagrams and dropped messages are logged and dumped
  without needing `UADS_DEBUG`.

## Lobby faction sync (uads ↔ engine state mirror)

The engine's `UAMSG_SETLEVEL` handler (yw_net.cpp:2676) **silently reassigns lobby
factions** on level change: RESIST → GHOR → MYKO → TAER order over the map's
allowed owners, indexed by join order, without broadcasting UAMSG_FRACTION. uads
mirrors this exactly in `change_level()` and then runs
`broadcast_faction_state()`, which syncs clients using two forged packets:

- forged `UAMSG_WELCOME` — displaces duplicate claimants: the target re-picks the
  first free faction and broadcasts a *real* UAMSG_FRACTION (self-syncing, changes
  the client's actual selection);
- forged `UAMSG_FRACTION` (from each player's own id, `freefrac=0`, `newfrac=faction`)
  — updates every client's lobby row display (does NOT change that client's own
  `SelectedFraction`).

This fixed "players have invalid faction selected" after `!level` to a
2-faction map. If the engine's assignment logic ever changes, uads' mirror must be
updated too (see the engine mechanics in CLIENT-CHANGES.md).

## Verified-correct (no action needed)

Packet header layout (flags/seq/channel at 0/1/5, data at 6, PART fsize/offset at 6/10/14),
`USR_MSG_DATA` framing (from u64 / cast u8 / to u64 / sz u32), SES_JOIN
`leader u8 | sesID u64 | szStr("level|host|date")`, CONNECTED (`has_lobby u8 | id u64 |
szStr name`), USERLEAVE (`id u64 | type u8`), USERLIST (count u32 + per-user
`id u64 | szStr name`), and the sizes of `uamessage_load`, `ready`, `fraction`,
`message`, `ping`, `syncgame`, `viewer`, `crc` payloads.

Faction values (owner bits 2/8/16/64 for Resistance/Mykonian/Taerkasten/Ghorkov)
match `World::OWNER_*_BIT` in the current engine. Session name `level|host|date`
parsing matches `windp.cpp:1167-1179`.

## 15. VHCLDATA wire format changed: 32-bit positions (fork-only)

The vanilla `vhcldata` struct carried positions as `int16_t` with a ÷2
encode/×2 decode scale, which silently truncated for `|pos| > 65534`
(≈54 sectors at CVSectorLength=1200) — units teleported on long maps.
An upstream interim fix (`(int16_t)(pos/4)` / ×4) was also reverted.

Fork change (UA_source `f6bf350`): `pos_x/pos_y/pos_z` are now `int32_t`,
encoded exactly (`(int32_t)pos`), decoded exactly (no scale). New entry
sizes: `vhcldata` = 28 B (2 pad bytes before `ident`), `vhcldataE` = 56 B.
`uamessage_vhclData` base stays 24 B; `vhcldatahdr.size` (sender-computed)
still describes the full message.

- Both engine peers must run the fork build (wire format change; vanilla
  peers would render positions wrong — they are already broken on long
  maps anyway).
- uads needs NO change: the splitter reads the declared `hdr.size`
  (see section 12), verified with synthetic 28-byte-entry datagrams.
- `static_assert`s in yw_net.h now guard the wire sizes at compile time.
