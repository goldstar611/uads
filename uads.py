import socket
import time
import hashlib
import uuid

import net_classes


class UAMPClient:
    def __init__(self):
        self.remote_addr = None  # Assigned by UAMPGame()
        self.remote_port = None  # Assigned by UAMPGame()
        self.packet_sequence = 0  # The last packet number that we sent to the client
        self.last_ping_time = 0  # The time.time() when we last sent a ping to this client
        self.last_packet_time = 0  # The time.time() when we last received a packet from this client

        self.player_name = "Unnamed"
        self.faction = None  # This should be an enum
        self.crc = None  # The reported checksum of game files on disk
        self.ready = None  # If the player is ready or not
        self.cd = None  # If the player has a CD or not

    @property
    def player_id(self):
        # This is not globally unique across all UAMPGames() so to find a player use remote_addr and remote_port
        return hashlib.blake2s(self.player_name.encode(), digest_size=8).hexdigest()

    def needs_ping(self):
        if time.time() - self.last_ping_time > 5:
            return True
        return False

    def should_kick_player(self):
        if time.time() - self.last_packet_time > 10:
            return True
        return False

    def send_pint(self):
        raise NotImplemented

    def next_pkt_seq(self):
        self.packet_sequence += 1
        return self.packet_sequence

    def inspect_packet(self, packet):
        self.last_packet_time = time.time()
        # Inspect the packet so we can update any instance variables
        # We might want to keep track of such as last_packet_time
        raise NotImplemented

    def send_packet(self, packet):
        # We need to send something to this client
        raise NotImplemented


class UAMPGame:
    def __init__(self):
        self.game_id = uuid.uuid4().fields[5]
        self.game_level_id = 93
        self.game_started = False
        self.game_start_time = 0
        self.players = {}

    @property
    def time_stamp(self):
        if self.game_started:
            return time.time() - self.game_start_time
        return 0

    def player_join(self, client):
        # Update self.players
        # For each player, send UAMessageWelcome()
        raise NotImplemented

    def player_leave(self, client):
        # Update self.players
        # For each player, send ???
        raise NotImplemented

    def change_level(self, level_id):
        self.game_level_id = level_id
        # For each player, send NetSysSessionJoin()
        raise NotImplemented

    def start_game(self):
        # For each player, send UAMessageLoadGame()
        self.game_started = True
        self.game_start_time = time.time()

        for player in self.players.values():
            msg = net_classes.UAMessageLoadGame()
            msg.level_id = self.game_level_id
            msg.my_timestamp = self.time_stamp
            msg.packet_to = self.game_id
            # msg.packet_from = ????  # TODO FIXME
            msg.sequence_id = player.next_pkt_seq()
            player.send_packet(msg)
        raise NotImplemented

    def packet_received(self, packet):
        # The dedicated server received a packet and determined that it was related to this UAMPGame
        # Most of the UAMPGame logic will go here
        # For example, we might get a player connect message, then we will call self.player_join()
        # Or the game might already be started and we will need to send the incoming packet to all of the other players
        raise NotImplemented

    def is_full(self):
        # Can we add in more players to this game?

        # If the game has started, don't accept any new players
        if self.game_started:
            return False

        # If we have 4 or more players, don't accept any new players
        return len(self.players.keys()) >= 4


client_sockets = {}

# Server code
dedicated_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
dedicated_server_socket.setblocking(False)
dedicated_server_socket.bind(("127.0.0.1", 61234))
while True:
    try:
        time.sleep(0.001)  # sleep 1 ms
        # Receive data from players
        data, cli_address = dedicated_server_socket.recvfrom(1024)

        # Check if this is a new players or not
        if cli_address not in client_sockets:
            # Got a new player to keep track of
            print("New player on port {}".format(cli_address))
            client_sockets[cli_address] = True

        # Inspect the data and send the appropriate response(s)
        cls = net_classes.data_to_class(data)
        for response in net_classes.respond(cls):
            print("Responding with {}".format(response))
            dedicated_server_socket.sendto(response.data, cli_address)
    except BlockingIOError:
        pass
