import binascii
import random
import socket
import time
import uuid

import net_classes
import net_games
import net_messages


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
        self.is_host = False
        self.faction = net_games.faction_resistance
        self.crc = None  # The reported checksum of game files on disk
        self.ready = None  # If the player is ready
        self.player_id = player_id or ((random.randrange(2 ** 32) << 16) + 0xBBBB) | 0xAAAA000000000000

    def should_ping(self):
        if int(time.time()) - self.last_ping_time > 2:
            return True
        return False

    def should_kick(self):
        if int(time.time()) - self.last_packet_time > 10:
            return True
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
        self.socket.sendto(packet.data, (self.remote_addr, self.remote_port))
        pass

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
            if player.should_kick():
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

    def kick_player(self, player, reconnecting=False):
        player.send_message(message="You have been kicked from the server.")
        if not reconnecting:
            player.send_packet(net_classes.NetSysDisconnected())
        self.players.pop((player.remote_addr, player.remote_port))

        if player.is_host and self.num_players > 0:
            next_host = next(iter(self.players.values()))
            next_host.make_host()

        player_left_message = net_classes.NetUsrDisconnect(player_id=player.player_id,
                                                           sequence_id=player.next_pkt_seq())
        for player in self.players.values():
            player.send_packet(player_left_message)

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
        self.players[player_addr_port] = new_player

        new_player.send_packet(net_classes.NetSysConnected(client_name=new_player.player_name,
                                                           client_id=new_player.player_id))
        new_player.send_packet(net_classes.NetSysSessionJoin(game_id=self.game_id,
                                                             level_number=self.level_number,
                                                             hoster_name="uads"))
        if self.num_players == 1:
            new_player.make_host()

        players = {player.player_name: player.player_id for player in self.players.values()}
        for player in self.players.values():
            player.send_packet(net_classes.NetUsrSessionList(users=players,
                                                             sequence_id=player.next_pkt_seq()))
            player.send_packet(net_classes.UAMessageWelcome(to_id=player.player_id,
                                                            from_id=new_player.player_id,
                                                            sequence_id=player.next_pkt_seq()))
            new_player.send_packet(net_classes.UAMessageWelcome(to_id=new_player.player_id,
                                                                from_id=player.player_id,
                                                                sequence_id=new_player.next_pkt_seq()))
            # player.send_packet(net_classes.UAMessageCRC(to_id=player.player_id,
            #                                            from_id=new_player.player_id,
            #                                            sequence_id=player.next_pkt_seq()))
            # player.send_packet(net_classes.UAMessageCD(to_id=self.game_id,
            #                                           from_id=new_player.player_id,
            #                                           sequence_id=player.next_pkt_seq()))

        return new_player

    def change_level(self, game_level_id):
        self.level_number = game_level_id
        for player in self.players.values():
            player.send_packet(net_classes.NetSysSessionJoin(game_id=self.game_id,
                                                             level_number=self.level_number,
                                                             hoster_name=player.player_name))
            player.send_message(message="Changing level to "
                                        f"{net_games.game_names.get(game_level_id, '???')} ({game_level_id})")

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

    def packet_received(self, packet, player_addr_port):
        # The dedicated server received a packet and determined that it was related to this UAMPGame
        # Most of the UAMPGame logic will go here
        # For example, we might get a player connect message, then we will call self.add_player()
        # Or the game might already be started, and we will need to send the incoming packet to all other players
        # Inspect the data and send the appropriate response(s)
        player = self.players[player_addr_port]
        player.inspect_packet(packet)

        if isinstance(packet, net_classes.NetSysPing):
            player.send_packet(net_classes.NetSysDelivered(sequence_id=packet.sequence_id))
            return

        if packet.packet_flags & net_messages.PKT_FLAG_GARANT:
            player.send_packet(net_classes.NetSysDelivered(sequence_id=packet.sequence_id))

        if player.should_ping():
            player.send_ping(game_started=self.game_started,
                             time_stamp=self.time_stamp)

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
                return

            if player.is_host and packet.message == ("!gameid"):
                player.send_message(f"Game ID: {self.game_id}")
                return

            if player.is_host and packet.message == ("!lock"):
                self.game_locked = True
                player.send_message(f"Game locked. No new players can join.")
                return

            if packet.message.startswith("!connect"):
                global all_games
                player_name = player.player_name
                player_id = player.player_id
                try:
                    game_id = int(packet.message[8:])
                except ValueError:
                    return

                # Ensure game_id is valid
                for game in all_games:
                    if game.game_id == game_id:
                        # Check if game is_full
                        if game.is_full():
                            player.send_message(message="Game is full or started.")
                            return

                        # Pop player from game
                        # Send disconnect message to everyone left in the game
                        self.kick_player(player, reconnecting=True)

                        # Add player to specified game
                        new_player = game.add_player(player_name, player_addr_port, player_id)
                return

            if player.is_host and packet.message.startswith("!unlock"):
                self.game_locked = False
                player.send_message(f"Game unlocked. Allowing new players.")
                return

            if player.is_host and packet.message.startswith("!kick"):
                print(f"{player.player_name} wants to kick player index {packet.message[5:]}")
                try:
                    i = int(packet.message[5:])
                except ValueError:
                    return
                kicked = self.kick_player_by_index(i)
                if kicked:
                    player.send_message(message=f"Kicked player {kicked}")
                else:
                    player.send_message(message=f"Couldn't kick player {i}!")
                return

            if player.is_host and packet.message.startswith("!level"):
                print(f"{player.player_name} wants to change level to {packet.message[6:]}")
                try:
                    level_number = int(packet.message[6:])
                except ValueError:
                    return

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
                return

        if isinstance(packet, net_classes.Generic):
            if packet.msg_type == "UAMSG_VHCLDATA_I":
                # return
                pass

        if isinstance(packet, net_classes.NetSysDisconnected):
            print(f"{player.player_name} has left")
            self.kick_player(player)
            return

        if isinstance(packet, net_classes.Part):
            if packet.sequence_id not in self.multi_part_packets:
                self.multi_part_packets[packet.sequence_id] = packet
            else:
                self.multi_part_packets[packet.sequence_id].add_part_data(packet.offset, packet.part_data)

            if self.multi_part_packets[packet.sequence_id].is_complete():
                # Queue packet
                reconstructed_packet = self.multi_part_packets[packet.sequence_id].reconstructed_packet()
                try:
                    pkt = net_classes.data_to_class(reconstructed_packet)
                    self.packet_received(pkt, player_addr_port)
                except Exception as e:
                    print(f"Multipart packet exception! {e}")

                # Remove from dictionary
                del self.multi_part_packets[packet.sequence_id]
            return

        if packet.packet_type == net_messages.USR_MSG_DATA and packet.packet_cast:
            for addr_port, p in self.players.items():
                if addr_port != player_addr_port:
                    p.send_packet(packet)

    def is_full(self):
        # Can we add in more players to this game?

        # If the game has started, don't accept any new players
        if self.game_started or self.game_locked:
            return True

        # If we have filled all player positions, don't accept any new players
        return self.num_players >= self.max_players()


def switch_packet(packet, player_addr_port, games, sock):
    for game in games:  # Can be optimized later
        if player_addr_port in game:
            # print("Found game that player is in")
            game.packet_received(packet, player_addr_port)
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
    dedicated_server_socket.bind(("0.0.0.0", 61234))

    # Game restart variables
    server_is_restarting = False
    server_restart_time = 0
    server_restart_msg_time = 0

    global all_games

    while True:
        for game in all_games:  # Can be optimized later
            game.check_game()
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
            # Convert the raw data to an object
            packet = net_classes.data_to_class(data)
            if packet:
                switch_packet(packet=packet, player_addr_port=player_addr_port,
                              games=all_games, sock=dedicated_server_socket)
        except BlockingIOError:
            pass
        except RestartServer:
            server_is_restarting = True
            server_restart_time = int(time.time()) + 5
            pass
        except net_classes.DataToClassException:
            print(f"Error parsing packet with data:\n{binascii.hexlify(data)}")
            pass


if __name__ == "__main__":
    main()
