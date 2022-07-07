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
    def __init__(self, sock, game_id, player_name, remote_addr, remote_port):
        self.socket = sock
        self.remote_addr = remote_addr
        self.remote_port = remote_port
        self.packet_sequence = 0  # The last packet number that we sent to the client
        self.last_ping_time = 0  # The time.time() when we last sent a ping to this client
        self.last_packet_time = 0  # The time.time() when we last received a packet from this client
        self.game_id = game_id

        self.player_name = player_name
        self.faction = net_games.faction_resistance
        self.crc = None  # The reported checksum of game files on disk
        self.ready = None  # If the player is ready or not
        self.cd = None  # If the player has a CD or not
        self.player_id = ((random.randrange(2**32) << 16) + 0xBBBB) | 0xAAAA000000000000

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
                                                    my_timestamp=time_stamp)
            self.send_packet(ping)

        # print("Sending NetSysPing")
        ping = net_classes.NetSysPing(sequence_id=self.packet_sequence)
        self.send_packet(ping)

    def next_pkt_seq(self):
        self.packet_sequence += 1
        return self.packet_sequence

    def inspect_packet(self, packet):
        self.last_packet_time = int(time.time())
        # Inspect the packet so we can update any instance variables
        # We might want to keep track of such as last_packet_time
        if isinstance(packet, net_classes.UAMessageFaction):
            print("{} is changing faction to number {} from {}".format(self.player_name, packet.new, packet.old))
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
                                           message=message)
        self.send_packet(pkt)


class UAMPGame:
    def __init__(self, sock):
        self.socket = sock
        self.game_id = uuid.uuid4().fields[5]
        self.level_number = 93
        self.game_started = False
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
        return len(self.players.keys()) == 0

    @property
    def max_players(self):
        if self.level_number in net_games.game_owners:
            return len(net_games.game_owners[self.level_number])
        return 4  # HACK for MD or custom levels

    def check_game(self):
        for player in self.players.copy().values():
            if player.should_kick():
                self.kick_player(player)
                self.message_all_players("{} has been kicked from game".format(player.player_name))

    def kick_player(self, player):
        player.send_packet(net_classes.NetSysDisconnected())
        self.players.pop((player.remote_addr, player.remote_port))

        player_left_message = net_classes.NetUsrDisconnect(player_id=player.player_id)
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
            temp_name = "{}-{}".format(player_name, i)

        return temp_name

    def add_player(self, player_name, player_addr_port):
        remote_addr, remote_port = player_addr_port
        new_player = UAMPClient(sock=self.socket, game_id=self.game_id, player_name=self.player_name_clean(player_name),
                                remote_addr=remote_addr, remote_port=remote_port)
        self.players[player_addr_port] = new_player

        new_player.send_packet(net_classes.NetSysConnected(client_name=new_player.player_name,
                                                           client_id=new_player.player_id))
        new_player.send_packet(net_classes.NetSysSessionJoin(game_id=self.game_id,
                                                             level_number=self.level_number,
                                                             hoster_name="uads"))

        players = {player.player_name: player.player_id for player in self.players.values()}
        for player in self.players.values():
            player.send_packet(net_classes.NetUsrSessionList(players))
            player.send_packet(net_classes.UAMessageWelcome(to_id=player.player_id,
                                                            from_id=new_player.player_id))
            player.send_packet(net_classes.UAMessageCRC(to_id=player.player_id,
                                                        from_id=new_player.player_id))
            player.send_packet(net_classes.UAMessageCD(to_id=player.player_id,
                                                       from_id=new_player.player_id))

    def change_level(self, game_level_id):
        max_players = len(net_games.game_owners.get(game_level_id, [1, 1, 1, 1]))
        self.level_number = game_level_id
        self.max_players = max_players
        for player in self.players.values():
            player.send_packet(net_classes.NetSysSessionJoin(game_id=self.game_id,
                                                             level_number=self.level_number,
                                                             hoster_name=player.player_name))
            player.send_message(message="Changing level to {} ({})".format(net_games.game_names.get(game_level_id,
                                                                                                    "???"),
                                                                           game_level_id))

    def has_conflicts(self):
        # Check for too many players in game for map
        if len(self.players.keys()) > self.max_players:
            return "Too many players for map!"

        # Check that all players have correct faction for map
        for player in self.players.values():
            game_factions = [net_games.owner_to_faction[x] for x in net_games.game_owners[self.level_number]]
            if player.faction not in game_factions:
                return "Player {} has selected invalid faction!".format(player.player_name)

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

        self.game_started = True
        self.game_start_time = int(time.time())

        for player in self.players.values():
            msg = net_classes.UAMessageLoadGame(to_id=player.player_id,
                                                from_id=self.game_id,
                                                level_number=self.level_number)
            msg.sequence_id = player.next_pkt_seq()
            player.send_packet(msg)

    def packet_received(self, packet, player_addr_port):
        # The dedicated server received a packet and determined that it was related to this UAMPGame
        # Most of the UAMPGame logic will go here
        # For example, we might get a player connect message, then we will call self.add_player()
        # Or the game might already be started and we will need to send the incoming packet to all of the other players
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
                             time_stamp=self.game_start_time)

        if isinstance(packet, net_classes.UAMessageMessage):
            print("New message: {}".format(packet.message))
            if packet.message == "!restart":
                print(f"{player.player_name} has restarted the server")
                raise RestartServer()

            if packet.message == "!start":
                print(f"{player.player_name} has started the game")
                self.start_game()
                return

            if packet.message.startswith("!level"):
                level_number = int(packet.message[6:])
                print(f"{player.player_name} wants to change level to {level_number}")

                try:
                    if level_number not in net_games.game_names.keys():
                        raise ValueError()
                    if level_number > 999:
                        raise ValueError()
                    self.change_level(level_number)
                except ValueError:
                    print("Couldn't change level to {}".format(level_number))
                    player.send_message("Couldn't change level to {}".format(level_number))
                return

        if isinstance(packet, net_classes.Generic):
            if packet.msg_type == "UAMSG_VHCLDATA_I":
                # return
                pass

        if isinstance(packet, net_classes.NetSysDisconnected):
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
                except Exception as e:
                    print("Multipart packet exception!")
                self.packet_received(pkt, player_addr_port)

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
        if self.game_started:
            return True

        # If we have filled all player positions, don't accept any new players
        return len(self.players.keys()) >= self.max_players


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
    print("Ignoring packet {} from {}".format(packet, player_addr_port))


def main():
    # Server code
    dedicated_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dedicated_server_socket.setblocking(False)
    dedicated_server_socket.bind(("0.0.0.0", 61234))

    # Game restart variables
    server_is_restarting = False
    server_restart_time = 0
    server_restart_msg_time = 0

    games = [UAMPGame(sock=dedicated_server_socket)]  # type: list[UAMPGame]

    while True:
        for game in games:  # Can be optimized later
            game.check_game()
            if game.game_started and game.game_finished:
                print("Purging game {} with no players".format(game.game_id))
                games.remove(game)
                continue
            if server_is_restarting:
                if int(time.time()) > server_restart_time:
                    game.kick_all_players()
                    raise Exception("Time to restart the server")

                if int(time.time()) - server_restart_msg_time >= 1:
                    server_restart_msg_time = int(time.time())
                    game.message_all_players(message="Server is restarting in {} seconds".format(server_restart_time -
                                                                                                 int(time.time())))

        try:
            time.sleep(0.001)  # sleep 1 ms
            # Receive data from players
            data, player_addr_port = dedicated_server_socket.recvfrom(1500)
            # Convert the raw data to an object
            packet = net_classes.data_to_class(data)
            if packet:
                switch_packet(packet=packet, player_addr_port=player_addr_port, games=games, sock=dedicated_server_socket)
        except BlockingIOError:
            pass
        except RestartServer:
            server_is_restarting = True
            server_restart_time = int(time.time()) + 5
            pass
        except net_classes.DataToClassException:
            print("Error parsing packet with data:\n{}".format(binascii.hexlify(data)))
            pass


if __name__ == "__main__":
    main()
