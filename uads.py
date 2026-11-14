import binascii
import os
import random
import socket
import struct
import time
import uuid

import net_classes
import net_games
import net_messages

UADS_DEBUG = os.environ.get("UADS_DEBUG")


def debug_print(msg):
    if UADS_DEBUG:
        print(msg)


class RestartServer(Exception):
    pass


class UAMPClient:
    def __init__(self, sock, game_id, player_name, remote_addr, remote_port, player_id=None):
        self.socket = sock
        self.remote_addr = remote_addr
        self.remote_port = remote_port
        self.packet_sequence = 0  # The last packet number that we sent to the client
        self.last_ping_time = 0  # The time.time() when we last sent a ping to this client
        self.last_packet_time = time.time()  # The time.time() when we last received a packet from this client
        self.game_id = game_id

        self.player_name = player_name
        self.orig_name = player_name  # handshake name as the client knows itself
        self.is_host = False
        self.faction = net_games.faction_resistance
        self.crc = None  # The reported checksum of game files on disk
        self.ready = None  # If the player is ready
        self.player_id = player_id or ((random.randrange(2 ** 32) << 16) + 0xBBBB) | 0xAAAA000000000000

    def should_ping(self):
        if int(time.time()) - self.last_ping_time > 2:
            return True
        return False

    def should_kick(self, game_started=False):
        if int(time.time()) - self.last_packet_time > 10:
            # A client that has entered a running game always streams
            # VHCLDATA, so 10s of silence means it is gone. But a client
            # that is still LOADING is legitimately silent for a long time
            # (the engine waits up to ~150s for slow loaders) - kicking it
            # mid-load would yank it out of the game and leave the others
            # staring at a net-problem icon.
            return game_started
        return False

    def send_ping(self, game_started, time_stamp):
        self.last_ping_time = int(time.time())
        if game_started:
            # print("Sending UAMessageRequestPing")
            ping = net_classes.UAMessageRequestPing(to_id=self.player_id,
                                                    from_id=self.game_id,
                                                    sequence_id=self.next_pkt_seq(),
                                                    my_timestamp=time_stamp)
            self.send_packet(ping)

        # print("Sending NetSysPing")
        ping = net_classes.NetSysPing(sequence_id=self.next_pkt_seq())
        self.send_packet(ping)

    def next_pkt_seq(self):
        self.packet_sequence += 1
        return self.packet_sequence

    def inspect_packet(self, packet):
        self.last_packet_time = int(time.time())
        # Inspect the packet to update any instance variables
        # We might want to keep track of such as last_packet_time
        if isinstance(packet, net_classes.UAMessageFaction):
            print(f"{self.player_name} is changing faction to number {packet.new} from {packet.old}")
            self.faction = packet.new

    def send_packet(self, packet):
        # We need to send something to this client
        debug_print(f"TX to {self.player_name}: {packet!r:.200s}")
        self.socket.sendto(packet.data, (self.remote_addr, self.remote_port))
        pass

    def relay_packet(self, packet):
        # Relay a (sub-)packet to this client with a fresh sequence number of
        # our own. Blindly forwarding the original datagram would reuse the
        # sender's seq (and concatenated multi-message payloads); the engine
        # processes messages one datagram at a time, so we re-frame each
        # message individually. The UA message bytes themselves stay verbatim.
        raw = bytearray(packet.data)
        struct.pack_into("<I", raw, 1, self.next_pkt_seq())
        self.socket.sendto(bytes(raw), (self.remote_addr, self.remote_port))

    def send_message(self, message):
        message = "> SERVER: " + message
        print(message)
        pkt = net_classes.UAMessageMessage(from_id=self.player_id,
                                           to_id=self.game_id,
                                           sequence_id=self.next_pkt_seq(),
                                           message=message)
        self.send_packet(pkt)

    def make_host(self):
        self.is_host = True
        self.send_message("You are the host.")
        self.send_message("Type !level100 to change levels.")
        self.send_message("Type !start to start the game.")


class UAMPGame:
    def __init__(self, sock):
        self.socket = sock
        self.game_id = uuid.uuid4().fields[5]
        self.level_number = 93
        self.game_started = False
        self.game_locked = False
        self.game_start_time = 0
        self.players = {}  # type: dict[tuple, UAMPClient]
        self.multi_part_packets = {}
        self.rx_counts = {}  # msg_id -> RX count (per player, for loss debugging)
        self.tx_counts = {}
        self.stats_time = time.time()

    def __iter__(self):
        # This lets us do cool stuff like `if player in game`
        for player in self.players.keys():
            yield player

    @property
    def time_stamp(self):
        if self.game_started:
            return int(time.time()) - self.game_start_time
        return 0

    @property
    def game_finished(self):
        # The game is finished when no one is connected :)
        return self.num_players == 0

    @property
    def num_players(self):
        return len(self.players.keys())

    def max_players(self, level_number=None):
        if level_number is None:
            level_number = self.level_number

        if level_number in net_games.game_owners:
            return len(net_games.game_owners[level_number])

        return 4  # HACK for MD or custom levels

    def check_game(self):
        for player in self.players.copy().values():
            # Proactively ping players: the engine client sends nothing on its own
            # in the lobby, and only replies to our SYS_MSG_PING (netlib client.cpp:142).
            # Without this the player looks idle for 10s and gets kicked.
            if player.should_ping():
                player.send_ping(game_started=self.game_started,
                                 time_stamp=self.time_stamp)
            if player.should_kick(game_started=self.game_started):
                self.kick_player(player)
                self.message_all_players(f"{player.player_name} has been kicked from game")

    def kick_player_by_index(self, i):
        player_list = list(self.players.values())
        if i > len(player_list):
            return False

        player = player_list[i - 1]
        player_name = player.player_name
        self.kick_player(player)
        return player_name

    def _owner_index(self, player):
        # Engine owner index (1/3/4/6) from the faction owner bit
        # (2/8/16/64 = 1 << owner).
        return player.faction.bit_length() - 1 if player.faction else 0

    def kick_player(self, player, reconnecting=False):
        leaver_name = player.player_name
        leaver_owner = self._owner_index(player)

        if not reconnecting:
            # UAMSG_KICK with the player's own name is the engine's game-end
            # signal: yw_net.cpp aborts the running game (netProblem=3 with
            # a status message, 10s countdown) when the text matches the
            # receiver's own netPlayerName. A bare SYS_MSG_DISCONNECT only
            # stops the net thread - the game would keep running. The text
            # must be the client's HANDSHAKE name (all clients may connect
            # as "Unnamed"), not uads' uniquified name.
            player.send_packet(net_classes.UAMessageKick(
                to_id=player.player_id, from_id=self.game_id,
                text=player.orig_name))
            player.send_packet(net_classes.NetSysDisconnected())
        self.players.pop((player.remote_addr, player.remote_port))

        if player.is_host and self.num_players > 0:
            next_host = next(iter(self.players.values()))
            next_host.make_host()

        # Vanilla's "Ghorkovs have left the game": when a player's robo
        # dies (any cause, incl. quitting a net game) the engine broadcasts
        # UAMSG_HOSTDIE (yparobo.cpp Die); every remaining client then kills
        # the leaver's units, cleans targeting and plays the per-faction
        # "have left the game" voice feedback (yw_net.cpp MsgID 87/88/89/90).
        # A quitting client does not reliably broadcast this itself, and
        # uads games have no real engine host, so uads synthesizes it here.
        if self.game_started:
            print(f"Broadcasting hostDie for {leaver_name} (owner {leaver_owner}) "
                  f"to {self.num_players} remaining players")
            for p in self.players.values():
                p.send_packet(net_classes.UAMessageHostDie(
                    to_id=p.player_id, from_id=self.game_id,
                    owner=leaver_owner))

        # A started game that is down to its last client is over: kick the
        # last standing player so they don't keep playing alone. Do this
        # after the HOSTDIE broadcast above - after the recursive kick the
        # remaining set is empty and there is nobody left to notify.
        if self.game_started and self.num_players == 1:
            last = next(iter(self.players.values()))
            print(f"{last.player_name} is the last player left - ending the game")
            self.kick_player(last)
            return

        # NOTE: `player` is the leaver here - do not shadow it with the
        # broadcast loops below (that sent the wrong player's ID and the
        # peers erased the wrong user from their tracking tables).
        player_left_message = net_classes.NetUsrDisconnect(player_id=player.player_id,
                                                           sequence_id=player.next_pkt_seq())
        print(f"USERLEAVE: {leaver_name} (orig {player.orig_name}) id={player.player_id:#x}")
        for p in self.players.values():
            p.send_packet(player_left_message)

    def kick_all_players(self):
        for player in self.players.copy().values():
            self.kick_player(player)

    def player_name_clean(self, player_name):
        temp_name = player_name
        i = 0
        current_player_names = [player.player_name for player in self.players.values()]
        while temp_name in current_player_names:
            i += 1
            temp_name = f"{player_name}-{i}"

        return temp_name

    def add_player(self, player_name, player_addr_port, player_id=None):
        remote_addr, remote_port = player_addr_port
        new_player = UAMPClient(sock=self.socket, game_id=self.game_id, player_name=self.player_name_clean(player_name),
                                remote_addr=remote_addr, remote_port=remote_port, player_id=player_id)
        # The engine clients compare UAMSG_KICK text against their OWN
        # netPlayerName - the name they sent in the handshake, NOT the
        # uniquified name uads displays. Keep the original for that.
        new_player.orig_name = player_name
        self.players[player_addr_port] = new_player

        new_player.send_packet(net_classes.NetSysConnected(client_name=new_player.player_name,
                                                           client_id=new_player.player_id))
        new_player.send_packet(net_classes.NetSysSessionJoin(game_id=self.game_id,
                                                             level_number=self.level_number,
                                                             hoster_name="uads"))
        # The engine lobby learns the level from UAMSG_SETLEVEL/LOBBYINIT,
        # not from the session name - without this a client that reconnects
        # (e.g. after a level change) keeps its stale netLevelID and loads
        # the wrong level.
        new_player.send_packet(net_classes.UAMessageSetLevel(to_id=new_player.player_id,
                                                             from_id=self.game_id,
                                                             sequence_id=new_player.next_pkt_seq(),
                                                             level_number=self.level_number,
                                                             host_name="uads"))
        if self.num_players == 1:
            new_player.make_host()

        players = {player.player_name: player.player_id for player in self.players.values()}
        print(f"SessionList: " + ", ".join(f"{n}={i:#x}" for n, i in players.items()))
        for player in self.players.values():
            player.send_packet(net_classes.NetUsrSessionList(users=players,
                                                             sequence_id=player.next_pkt_seq()))
            player.send_packet(net_classes.UAMessageWelcome(to_id=player.player_id,
                                                            from_id=new_player.player_id,
                                                            sequence_id=player.next_pkt_seq(),
                                                            faction=new_player.faction))
            new_player.send_packet(net_classes.UAMessageWelcome(to_id=new_player.player_id,
                                                                from_id=player.player_id,
                                                                sequence_id=new_player.next_pkt_seq(),
                                                                faction=player.faction))
            # player.send_packet(net_classes.UAMessageCRC(to_id=player.player_id,
            #                                            from_id=new_player.player_id,
            #                                            sequence_id=player.next_pkt_seq()))
            # player.send_packet(net_classes.UAMessageCD(to_id=self.game_id,
            #                                           from_id=new_player.player_id,
            #                                           sequence_id=player.next_pkt_seq()))

        return new_player

    def broadcast_faction_state(self):
        # Forge faction packets so every client's lobby display matches
        # uads' stored state, as if each player had changed faction in the
        # UI. Two complementary primitives:
        #
        # - Forged UAMSG_WELCOME (uw_net.cpp:2340): if the target's
        #   SelectedFraction equals the welcome's faction, the engine
        #   re-picks the first free faction and broadcasts a REAL
        #   UAMSG_FRACTION, which comes back here and updates our stored
        #   state. Used to displace duplicate claimants (changes a
        #   client's actual selection, not just the display).
        # - Forged UAMSG_FRACTION (yw_net.cpp:2320): the receiving engine
        #   updates lobbyPlayers[indx].NetFraction (row index resolved
        #   from the senderName of packet_from) for every client,
        #   including the affected player's own row. It does NOT change
        #   that client's own SelectedFraction -- display-only sync.
        # Duplicate claimants are displaced first, then every player's
        # row is broadcast (the displaced client's real FRACTION packet
        # fixes its row afterwards).
        seen = {}
        for player in self.players.values():
            claimant = seen.get(player.faction)
            if player.faction and claimant is not None:
                player.send_packet(net_classes.UAMessageWelcome(
                    to_id=player.player_id,
                    from_id=claimant.player_id,
                    sequence_id=player.next_pkt_seq(),
                    faction=player.faction))
            seen[player.faction] = player
        for player in self.players.values():
            for p in self.players.values():
                pkt = net_classes.UAMessageFaction(
                    to_id=p.player_id,
                    from_id=player.player_id)
                # freefrac (old) = 0: only claim the faction bit, free
                # nothing -- the displaced faction's bit is freed by the
                # SETLEVEL handler or the displaced client's re-pick.
                pkt.old = 0
                pkt.new = player.faction
                p.send_packet(pkt)

    def change_level(self, game_level_id):
        self.level_number = game_level_id
        # Mirror the engine's UAMSG_SETLEVEL handler (yw_net.cpp:2676): it
        # silently reassigns lobby factions for the new map in RESIST, GHOR,
        # MYKO, TAER order over the map's allowed owners, indexed by join
        # order, without broadcasting UAMSG_FRACTION. uads' stored factions
        # must be recomputed the same way or has_conflicts() fails with
        # "invalid faction" even though the clients already display the
        # reassigned (valid) factions.
        allowed = [owner for owner in (net_games.owner_resistance,
                                       net_games.owner_ghorkov,
                                       net_games.owner_mykonian,
                                       net_games.owner_taerkasten)
                   if owner in net_games.game_owners[game_level_id]]
        for i, player in enumerate(self.players.values()):
            if i < len(allowed):
                player.faction = net_games.owner_to_faction[allowed[i]]
        for player in self.players.values():
            player.send_packet(net_classes.NetSysSessionJoin(game_id=self.game_id,
                                                             level_number=self.level_number,
                                                             hoster_name=player.player_name))
            player.send_packet(net_classes.UAMessageSetLevel(to_id=player.player_id,
                                                             from_id=self.game_id,
                                                             sequence_id=player.next_pkt_seq(),
                                                             level_number=self.level_number,
                                                             host_name=player.player_name))
            player.send_message(message="Changing level to "
                                        f"{net_games.game_names.get(game_level_id, '???')} ({game_level_id})")
        self.broadcast_faction_state()

    def has_conflicts(self):
        # Check for too many players in game for map
        if self.num_players > self.max_players():
            return "Too many players for map!"

        # Check that all players have correct faction for map
        for player in self.players.values():
            game_factions = [net_games.owner_to_faction[x] for x in net_games.game_owners[self.level_number]]
            if player.faction not in game_factions:
                return f"Player {player.player_name} has selected invalid faction!"

        # Check for players with same faction
        factions_seen = {}
        has_conflict = False
        for player in self.players.values():
            if player.faction not in factions_seen:
                factions_seen[player.faction] = [player]
            else:
                has_conflict = "Multiple players have same faction!"
                factions_seen[player.faction].append(player)

        return has_conflict

    def message_all_players(self, message):
        for player in self.players.values():
            player.send_message(message=message)
        return

    def start_game(self):
        # For each player, send UAMessageLoadGame()
        if self.game_started:
            return False

        conflicts = self.has_conflicts()
        if conflicts:
            self.message_all_players(message="Can't start game with conflicts!")
            self.message_all_players(message=conflicts)
            return False

        # Check that all players are ready
        if not all([player.ready for player in self.players.values()]):
            self.message_all_players(message="All players ready up to start game!")
            return False

        self.game_started = True
        self.game_start_time = int(time.time())

        for player in self.players.values():
            msg = net_classes.UAMessageLoadGame(to_id=player.player_id,
                                                from_id=self.game_id,
                                                level_number=self.level_number,
                                                sequence_id=player.next_pkt_seq())
            player.send_packet(msg)

    def packet_received(self, packet, player_addr_port, extra_messages=None):
        # The dedicated server received a packet and determined that it was related to this UAMPGame
        # Most of the UAMPGame logic will go here
        # For example, we might get a player connect message, then we will call self.add_player()
        # Or the game might already be started, and we will need to send the incoming packet to all other players
        # Inspect the data and send the appropriate response(s)
        # extra_messages: additional UA messages parsed out of the same datagram -
        # the engine concatenates several UA messages into one USR_MSG_DATA
        # payload (windp.cpp QueueBroadcast), and every one of them matters to us.
        player = self.players[player_addr_port]
        messages = [packet] + list(extra_messages or ())
        for msg in messages:
            player.inspect_packet(msg)
            self.rx_counts[(player.player_name, getattr(msg, "message_id", None))] = \
                self.rx_counts.get((player.player_name, getattr(msg, "message_id", None)), 0) + 1
            debug_print(f"RX from {player.player_name}: {msg!r:.160s}")

        if isinstance(packet, net_classes.NetSysPing):
            player.send_packet(net_classes.NetSysDelivered(sequence_id=packet.sequence_id))
            return

        if packet.packet_flags & net_messages.PKT_FLAG_GARANT:
            player.send_packet(net_classes.NetSysDelivered(sequence_id=packet.sequence_id))

        if player.should_ping():
            player.send_ping(game_started=self.game_started,
                             time_stamp=self.time_stamp)

        if isinstance(packet, net_classes.Part):
            if packet.sequence_id not in self.multi_part_packets:
                self.multi_part_packets[packet.sequence_id] = packet
            else:
                self.multi_part_packets[packet.sequence_id].add_part_data(packet.offset, packet.part_data)

            if self.multi_part_packets[packet.sequence_id].is_complete():
                # Queue packet
                reconstructed_packet = self.multi_part_packets[packet.sequence_id].reconstructed_packet()
                try:
                    msgs = net_classes.split_usr_data(reconstructed_packet)
                    pkt = msgs[0] if msgs else net_classes.data_to_class(reconstructed_packet)
                    self.packet_received(pkt, player_addr_port, msgs[1:])
                except Exception as e:
                    print(f"Multipart packet exception! {e}")

                # Remove from dictionary
                del self.multi_part_packets[packet.sequence_id]
            return

        for msg in messages:
            if not self.handle_message(player, msg, player_addr_port):
                return

        if packet.packet_type == net_messages.USR_MSG_DATA and not packet.packet_cast:
            # cast == 0: message addressed to a single player, route it by player_id
            for addr_port, p in self.players.items():
                if addr_port != player_addr_port and p.player_id == packet.packet_to:
                    for msg in messages:
                        debug_print(f"TX direct to {p.player_name}: msg_id={msg.message_id}")
                        self.tx_counts[(p.player_name, getattr(msg, "message_id", None))] = \
                            self.tx_counts.get((p.player_name, getattr(msg, "message_id", None)), 0) + 1
                        p.relay_packet(msg)

        if packet.packet_type == net_messages.USR_MSG_DATA and packet.packet_cast:
            for addr_port, p in self.players.items():
                if addr_port != player_addr_port:
                    for msg in messages:
                        debug_print(f"TX broadcast to {p.player_name}: msg_id={msg.message_id}")
                        self.tx_counts[(p.player_name, getattr(msg, "message_id", None))] = \
                            self.tx_counts.get((p.player_name, getattr(msg, "message_id", None)), 0) + 1
                        p.relay_packet(msg)

    def handle_message(self, player, packet, player_addr_port):
        # Process a single UA message. Returns False when the original
        # packet_received() logic would have returned early (skipping relay).
        if isinstance(packet, net_classes.UAMessageFaction):
            # Resolve duplicate-faction conflicts in the lobby: with no real
            # host, nobody arbitrates, and both clients then map themselves
            # onto the same robo owner at level load (client desync).
            # The engine's welcome handler auto-re-picks a free faction when
            # it receives a welcome whose faction equals its own selection,
            # so poke the other claimant with exactly that.
            for other in self.players.values():
                if other is not player and other.faction == player.faction and player.faction:
                    other.send_packet(net_classes.UAMessageWelcome(
                        to_id=other.player_id,
                        from_id=player.player_id,
                        sequence_id=other.next_pkt_seq(),
                        faction=player.faction))
            # noreturn

        if isinstance(packet, net_classes.UAMessageReady):
            player.ready = packet.ready
            # noreturn

        if isinstance(packet, net_classes.UAMessageMessage):
            print(f"New message: {packet.message}")
            if packet.message == "!restart":
                print(f"{player.player_name} has restarted the server")
                raise RestartServer()

            if player.is_host and packet.message == "!start":
                print(f"{player.player_name} has started the game")
                self.start_game()
                return False

            if player.is_host and packet.message == ("!gameid"):
                player.send_message(f"Game ID: {self.game_id}")
                return False

            if player.is_host and packet.message == ("!lock"):
                self.game_locked = True
                player.send_message(f"Game locked. No new players can join.")
                return False

            if packet.message.startswith("!connect"):
                global all_games
                player_name = player.player_name
                player_id = player.player_id
                try:
                    game_id = int(packet.message[8:])
                except ValueError:
                    return False

                # Ensure game_id is valid
                for game in all_games:
                    if game.game_id == game_id:
                        # Check if game is_full
                        if game.is_full():
                            player.send_message(message="Game is full or started.")
                            return False

                        # Pop player from game
                        # Send disconnect message to everyone left in the game
                        self.kick_player(player, reconnecting=True)

                        # Add player to specified game
                        new_player = game.add_player(player_name, player_addr_port, player_id)
                return False

            if player.is_host and packet.message.startswith("!unlock"):
                self.game_locked = False
                player.send_message(f"Game unlocked. Allowing new players.")
                return False

            if player.is_host and packet.message.startswith("!kick"):
                print(f"{player.player_name} wants to kick player index {packet.message[5:]}")
                try:
                    i = int(packet.message[5:])
                except ValueError:
                    return False
                kicked = self.kick_player_by_index(i)
                if kicked:
                    player.send_message(message=f"Kicked player {kicked}")
                else:
                    player.send_message(message=f"Couldn't kick player {i}!")
                return False

            if player.is_host and packet.message.startswith("!level"):
                print(f"{player.player_name} wants to change level to {packet.message[6:]}")
                try:
                    level_number = int(packet.message[6:])
                except ValueError:
                    return False

                try:
                    if level_number not in net_games.game_names.keys():
                        raise ValueError()
                    if level_number > 999:
                        raise ValueError()
                    if self.num_players > self.max_players(level_number=level_number):
                        player.send_message(message="Too many players for map!")
                        raise ValueError()

                    self.change_level(level_number)
                    conflicts = self.has_conflicts()
                    if conflicts:
                        self.message_all_players(message=conflicts)
                except ValueError:
                    print(f"Couldn't change level to {level_number}")
                    player.send_message(f"Couldn't change level to {level_number}")
                return False

        if isinstance(packet, net_classes.Generic):
            if packet.msg_type == "UAMSG_VHCLDATA_I":
                # return
                pass

        if isinstance(packet, net_classes.NetSysDisconnected):
            print(f"{player.player_name} has left")
            self.kick_player(player)
            return False

        return True

    def is_full(self):
        # Can we add in more players to this game?

        # If the game has started, don't accept any new players
        if self.game_started or self.game_locked:
            return True

        # If we have filled all player positions, don't accept any new players
        return self.num_players >= self.max_players()


def switch_packet(packet, player_addr_port, games, sock, extra_messages=None):
    for game in games:  # Can be optimized later
        if player_addr_port in game:
            # print("Found game that player is in")
            game.packet_received(packet, player_addr_port, extra_messages)
            return  # Packet was sent to the correct game so let's get more packets

    # Ok so the packet came from a player who wasn't in a game, is it a join request packet?
    if isinstance(packet, net_classes.NetSysHandshake):
        for game in games:
            if not game.is_full():
                # print("Adding player to game")
                game.add_player(packet.client_name, player_addr_port)
                game.packet_received(packet, player_addr_port)
                return

        print("Creating a new game")
        game = UAMPGame(sock=sock)
        games.append(game)
        game.add_player(packet.client_name, player_addr_port)
        game.packet_received(packet, player_addr_port)
        return

    # Either we got an invalid packet from someone who got dropped from the game or
    # someone is messing with us.
    # Or we restarted the dedicated server while games were running.
    print(f"Ignoring packet {packet} from {player_addr_port}")


all_games = []  # type: list[UAMPGame]


def main():
    # Server code
    dedicated_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dedicated_server_socket.setblocking(False)
    dedicated_server_socket.bind(("0.0.0.0", int(os.environ.get("UADS_PORT", 61234))))

    # Game restart variables
    server_is_restarting = False
    server_restart_time = 0
    server_restart_msg_time = 0

    global all_games

    while True:
        for game in all_games:  # Can be optimized later
            game.check_game()
            if time.time() - game.stats_time >= 10:
                game.stats_time = time.time()
                if game.rx_counts or game.tx_counts:
                    def mid_name(mid):
                        if mid is None:
                            return "sys"
                        for attr in dir(net_messages):
                            if attr.startswith("UAMSG_") and getattr(net_messages, attr) == mid:
                                return f"{attr}({mid})"
                        return str(mid)
                    for (pname, mid), n in sorted(game.rx_counts.items(),
                                                  key=lambda kv: (kv[0][1] is None, kv[0][1], kv[0][0])):
                        print(f"STATS game={hex(game.game_id)[-4:]} RX {pname} "
                              f"{mid_name(mid)}: {n}")
                    for (pname, mid), n in sorted(game.tx_counts.items(),
                                                  key=lambda kv: (kv[0][1] is None, kv[0][1], kv[0][0])):
                        print(f"STATS game={hex(game.game_id)[-4:]} TX {pname} "
                              f"{mid_name(mid)}: {n}")
                    game.rx_counts.clear()
                    game.tx_counts.clear()
                    print("---")
            if game.game_started and game.game_finished:
                print(f"Purging game {game.game_id} with no players")
                all_games.remove(game)
                continue
            if server_is_restarting:
                if int(time.time()) > server_restart_time:
                    game.kick_all_players()
                    raise Exception("Time to restart the server")

                if int(time.time()) - server_restart_msg_time >= 1:
                    server_restart_msg_time = int(time.time())
                    game.message_all_players(message="Server is restarting in "
                                                     f"{server_restart_time - int(time.time())} seconds")

        try:
            time.sleep(0.001)  # sleep 1 ms
            # Receive data from players
            data, player_addr_port = dedicated_server_socket.recvfrom(1500)
            debug_print(f"RAW {len(data)} bytes from {player_addr_port}: {binascii.hexlify(data).decode()}")
            # The engine concatenates several UA messages into one
            # USR_MSG_DATA payload (windp.cpp QueueBroadcast); split them so
            # none gets lost, and so each can be relayed/re-framed separately.
            msgs = net_classes.split_usr_data(data)
            packet = msgs[0] if msgs else net_classes.data_to_class(data)
            if packet:
                switch_packet(packet=packet, player_addr_port=player_addr_port,
                              games=all_games, sock=dedicated_server_socket,
                              extra_messages=msgs[1:])
        except BlockingIOError:
            pass
        except RestartServer:
            server_is_restarting = True
            server_restart_time = int(time.time()) + 5
            pass
        except net_classes.DataToClassException:
            print(f"Error parsing packet with data:\n{binascii.hexlify(data)}")
            net_classes._dump_bad_split(data, -1)  # undecodable datagram


if __name__ == "__main__":
    main()
