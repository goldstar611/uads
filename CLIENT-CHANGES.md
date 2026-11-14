# Did the UA_source client change since uads was last used?

Short answer: **yes — and one specific engine commit is almost certainly the regression you
hit.** uads was last modified 2022-07-23 (`f3e6294 "Update uads.py"`). The engine build it
was developed against was roughly the July-2022 state of `UA_source` (≈ `4dd5052`, 2022-07-31).
The engine has had significant multiplayer-side changes since November 2022.

## The smoking gun: `uamessage_welcome` lost its `cd` byte

**Commit `330eb51` — 2022-11-07 — "Massive changes in world structure and in another"**
(authored by Marisa-Chan) changed `src/yw_net.h`:

```diff
 struct uamessage_welcome : uamessage_base
 {
     int16_t fraction;
     uint8_t rdy;
-    uint8_t cd;
+    //uint8_t cd;
 };
```

The same commit also commented out `UAMSG_CD = UAMSG_BASE + 42` in the message enum, and
removed the send-side `wlcmMsg.cd = usr->cd;` from the `RECVMSG_CREATEPLAYER` handler in
`yw_net.cpp`.

### Why this breaks uads

- In July 2022 the engine's own WELCOME was **20 bytes** (`fraction(2) + rdy(1) + cd(1)`
  on top of the 16-byte base) and the engine itself sent `cd` on the wire. uads'
  `UAMessageWelcome` (`net_classes.py:357,385` — payload_length `0x14`, writes
  `faction(H) + ready(B) + cd(B)`) matched the engine **byte-for-byte**. That's the
  "player-to-player with swapped IDs" exchange you remember: in `uads.py:189-204`
  (`add_player`) the server sends the WELCOME crosswise — *to* each existing player
  *from* the new player's ID, and *to* the new player *from* each existing player's ID —
  so every client's `lobbyPlayers[]` gets the correct sender name via
  `GetUserName(packet_from)` and marks the peer `Welcomed`.
- After `330eb51`, the engine's WELCOME is **19 bytes**. Clients walk UA messages
  back-to-back inside one `USR_MSG_DATA` payload using `sizeof(struct)`
  (`yw_net.cpp:3346-3351`). uads' 20-byte welcome now leaves one leftover byte, so the
  walk re-parses garbage as the "next message" (`msgSizes(19) < data.size()(20)` →
  `recvMsg.data += 19` → reads out-of-bounds bytes as a msgID). Consequences:
  - "unknown message was number N" log spam on every join,
  - and if the garbage bytes happen to form a valid msgID (out-of-bounds read — UB), the
    engine processes a fabricated message with bogus fields, e.g. a fake
    `UAMSG_KICK`/`UAMSG_UPDATE`, which *can* cascade into player destruction or state
    corruption → the disconnects you observed.

### Fix

Drop the `cd` byte from `UAMessageWelcome.data` and change
`self.packet_payload_length` from `0x14` to `0x13`. (Note the engine's *sender* no longer
emits `cd` either, so uads' receiver-side parser in `UAMessageWelcome.data.setter`
should expect the 19-byte layout as well.)

## Other engine changes since July 2022 that touch this code path

| commit | date | change | impact on uads |
|---|---|---|---|
| `d568ab3` | 2022-11-30 | "First working version with IP dialog" | enter-IP connect flow reworked |
| `69d6869` | 2023-01-10 | post-merge fixes (yw_func2/UI) | indirect |
| `396fbc0` | 2023-01-13 | "Fix MP menu Enter bug / Fix chat on clients" | chat/menu behavior in the INSESSION screen |
| `864f389` | 2023-01-14 | "Implement net buffering like in vanilla" | broadcasts are now queued and concatenated into one GARANT `USR_MSG_DATA` payload (`QueueBroadcast`/`FlushBroadcastBuffer`, `windp.cpp:400-539`) — makes the message-walk desync worse, and interacts with uads' never-confirmed GARANT relays (see FINDINGS.md §3) |
| `4b60687` | 2023-02-13 | "Simplify net users ids" | renames only (`NET_FRACTION_*` → `World::OWNER_*_BIT`, values unchanged, `OWNER_X_BIT = 1 << OWNER_X`) — uads' faction numbers 1/2/4/8 still match |
| `f1edccd` | 2023-02-13 | "Fix net select fraction" | fraction-selection flow |
| `315fa65`, `9986a6f` | 2023 | const / draw-seq | cosmetic |

`src/netlib/` itself (packet framing, ZNDServer/ZNDClient) has not been touched since
2020-12 (`939641b "Ready for early alpha MP"`) — the wire protocol server↔client is
unchanged. All the regressions are engine-side (`windp.cpp`, `yw_net.cpp`,
`yw_func2.cpp`).

## What did *not* change (for the record)

I diffed `windp.cpp` / `yw_net.cpp` between the July-2022 tree and HEAD specifically for
the host-election paths:

- `JoinLobbyLessGame()` still hard-sets `isHost = false` (`windp.cpp:1201`) — identical in
  both trees.
- `RECVMSG_HOST` was already dead code in 2022 (`windp.cpp` `Recv()` had no
  `EVENT_SESSION_LEAD` case then, either).
- The host-gated logic (START button, straggler kick, `ENDPROBLEM` resolution, score
  broadcast, "WAITING FOR HOST") is structurally identical in 2022 and HEAD.

So the "no real host" problem existed in the engine back then too — it did **not** appear
because of recent engine changes. If two clients "did not disconnect" several years ago,
the likely explanation is that the crosswise WELCOME exchange kept the lobby state healthy
(`Welcomed` flags set, fractions exchanged) and the session limped along in
"WAITING FOR HOST", whereas today the 1-byte welcome desync (plus the vanilla-style
broadcast buffering added in `864f389`) corrupts the message stream early enough to
trigger the abort paths (`netProblem` countdown → `STATE_ABORTED` → client drop).

## Timeline summary

```
2022-07-08/23   uads last commits (f3e6294)      — everything works (engine ≈ 4dd5052)
2022-11-07      UA_source 330eb51               — uamessage_welcome loses `cd` (20 → 19 bytes)
2022-11-30      d568ab3                          — IP dialog flow reworked
2023-01-13/14   396fbc0, 864f389                 — chat fixes, vanilla-style net buffering
2023-02-13      4b60687, f1edccd                 — id/fraction renames + fraction fix
⇒ uads' 20-byte WELCOME no longer matches the engine → message-walk desync on every join
```

## Recommended next steps

1. Apply the protocol fixes from `FINDINGS.md` — most urgently §1 (19-byte welcome),
   §2 (route `cast=0`), §3 (per-target seq + DELIVERED forwarding), §4 (handle
   `SYS_MSG_RETRY`).
2. Re-test the two-client lobby-less flow against current UA_source HEAD.
3. If drops persist, implement the host-election fix (FINDINGS.md §9, option 2:
   wire `EVENT_SESSION_LEAD` → `RECVMSG_HOST` in `windp.cpp` + uads sends
   `SYS_MSG_SES_LEAD`), since that path has been dead in every engine version.
