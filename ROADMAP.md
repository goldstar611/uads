# uads / UA_source fork roadmap

## 1. Migrate engine game-shell player tracking from names to user IDs

**Status:** proposed

**Problem:** The engine's netlib layer (`client.cpp` `cUsers`, `_rawUsers`) is
ID-based, but the game-shell layer (`yw_net.cpp`, `yw_func2.cpp`, `windp.cpp`)
is name-based everywhere. This breaks with uads because clients that connect
with identical profiles all handshake as the same name ("Unnamed") — uads
uniquifies the names server-side, but the clients never learn their unique
name, so every name comparison in the shell (`StriCmp(netPlayerName, ...)`)
is ambiguous or wrong:

- `yw_NetCheckPlayers` matches `netPlayers[]` by name for latency tracking
  ("Waiting for player X" / net-problem icon)
- `UAMSG_KICK` decides self-abort vs cleanup by comparing its text against
  the receiver's own `netPlayerName`
- `yw_cleanPlayer` / `yw_DestroyPlayer` / `GetPlayerIndex` find players by
  name
- WELCOME / READY / CRC / PONG handlers resolve the sender via
  `GetPlayerIndex(senderName)`
- DESTROYPLAYER resolves ID→name in the netlib, then cleans by name in the
  shell — an ID→name mismatch in the user table erases the wrong player

Observed consequences (2026-11-14 sessions): after one client leaves, the
remaining clients erase the *wrong* user row, keep tracking the departed
player, and show the net-problem icon until the 20 s timeout aborts them.

**Plan:**

1. Engine fork: add the netlib connection ID to `TNetPlayerData` /
   `TNetPlayerLobbyData`; thread the sender's ID through `windp_recvMsg`
   (alongside `senderName`).
2. Replace name comparisons with ID comparisons: `yw_NetCheckPlayers`,
   KICK handler (carry the target ID in the kick message — fork wire-format
   change, both peers must be fork builds), `yw_cleanPlayer`,
   `yw_DestroyPlayer`, `GetPlayerIndex`.
3. Keep names only for display (lobby rows, chat, voice feedback selection).
4. uads: stop relying on the kick-text self-name match; address players by
   ID everywhere it already can (USERLEAVE, SessionList already carry IDs).

**Notes / risks:**

- Vanilla (unpatched) clients become incompatible with an ID-based KICK —
  same constraint as the int32 VHCLDATA change; both peers must be fork
  builds. Considerable engine-side surface area: lobby UI, debrief, history
  and voice feedback all touch player names. Phase the work: first make the
  existing user-table IDs authoritative (debug the current ID mismatch
  between uads' SessionList and the engine's `cUsers`), then migrate the
  shell comparisons.
- Alternative (rejected): keep names but forbid duplicate handshake names in
  uads — hostile to players using the same install/profile, and the engine
  clients would still not know their unique names.
