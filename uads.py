import socket
import time
import hashlib
import uuid

import net_classes
import net_messages


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
        self.faction = None  # This should be an enum
        self.crc = None  # The reported checksum of game files on disk
        self.ready = None  # If the player is ready or not
        self.cd = None  # If the player has a CD or not

    @property
    def player_id(self):
        # This is not globally unique across all UAMPGames() so to find a player use remote_addr and remote_port
        return int(hashlib.blake2s(self.player_name.encode(), digest_size=8).hexdigest(), 16)

    def should_ping(self):
        if int(time.time()) - self.last_ping_time > 2:
            return True
        return False

    def should_kick_player(self):
        if int(time.time()) - self.last_packet_time > 10:
            return True
        return False

    def send_ping(self, game_started, time_stamp):
        self.last_ping_time = int(time.time())
        if game_started:
            print("Sending UAMessageRequestPing")
            ping = net_classes.UAMessageRequestPing(to_id=self.game_id,
                                                    from_id=self.game_id,
                                                    my_timestamp=time_stamp)
            ping.packet_to = self.player_id
            self.send_packet(ping)

        print("Sending NetSysPing")
        ping = net_classes.NetSysPing(sequence_id=self.packet_sequence)
        self.send_packet(ping)

    def next_pkt_seq(self):
        self.packet_sequence += 1
        return self.packet_sequence

    def inspect_packet(self, packet):
        self.last_packet_time = int(time.time())
        # Inspect the packet so we can update any instance variables
        # We might want to keep track of such as last_packet_time
        pass  # TODO FIX ME

    def send_packet(self, packet):
        # We need to send something to this client
        self.socket.sendto(packet.data, (self.remote_addr, self.remote_port))
        pass


class UAMPGame:
    def __init__(self, sock):
        self.socket = sock
        self.game_id = uuid.uuid4().fields[5]
        self.level_number = 93
        self.game_started = False
        self.game_start_time = 0
        self.players = {}

    def __iter__(self):
        # This lets us do cool stuff like `if player in game`
        for player in self.players.keys():
            yield player

    @property
    def time_stamp(self):
        if self.game_started:
            return int(time.time()) - self.game_start_time
        return 0

    def player_join(self, client):
        # Update self.players
        # For each player, send UAMessageWelcome()
        raise NotImplemented

    def player_leave(self, client):
        # Update self.players
        # For each player, send ???
        raise NotImplemented

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
        player = UAMPClient(sock=self.socket, game_id=self.game_id, player_name=self.player_name_clean(player_name),
                            remote_addr=remote_addr, remote_port=remote_port)
        self.players[player_addr_port] = player

        player.send_packet(net_classes.NetSysConnected(client_name=player.player_name,
                                                       client_id=player.player_id))
        player.send_packet(net_classes.NetSysSessionJoin(game_id=self.game_id,
                                                         level_number=self.level_number,
                                                         hoster_name=player.player_name))

        for player in self.players.values():
            players = {player.player_name: player.player_id for player in self.players.values()}
            player.send_packet(net_classes.NetUsrSessionList(players))
            player.send_packet(net_classes.UAMessageWelcome(to_id=player.player_id,
                                                            from_id=self.game_id))
            player.send_packet(net_classes.UAMessageCRC(to_id=player.player_id,
                                                        from_id=self.game_id))
            player.send_packet(net_classes.UAMessageCD(to_id=player.player_id,
                                                       from_id=self.game_id))

    def change_level(self, game_level_id=88):
        self.level_number = game_level_id
        for player in self.players.values():
            player.send_packet(net_classes.NetSysSessionJoin(game_id=self.game_id,
                                                             level_number=self.level_number,
                                                             hoster_name=player.player_name))

    def start_game(self):
        # For each player, send UAMessageLoadGame()
        self.game_started = True
        self.game_start_time = int(time.time())

        for player in self.players.values():
            msg = net_classes.UAMessageLoadGame(to_id=player.player_id,
                                                from_id=self.game_id,
                                                level_number=self.level_number)
            msg.level_number = self.level_number
            msg.my_timestamp = self.time_stamp
            msg.sequence_id = player.next_pkt_seq()
            player.send_packet(msg)

    def packet_received(self, packet, player_addr_port):
        # The dedicated server received a packet and determined that it was related to this UAMPGame
        # Most of the UAMPGame logic will go here
        # For example, we might get a player connect message, then we will call self.player_join()
        # Or the game might already be started and we will need to send the incoming packet to all of the other players
        # Inspect the data and send the appropriate response(s)
        player = self.players[player_addr_port]  # type: UAMPClient
        player.inspect_packet(packet)

        if isinstance(packet, net_classes.NetSysDelivered) or isinstance(packet, net_classes.UAMessagePong):
            return

        if packet.packet_flags & net_messages.PKT_FLAG_GARANT:
            player.send_packet(net_classes.NetSysDelivered(sequence_id=packet.sequence_id))

        if player.should_ping():
            player.send_ping(game_started=self.game_started,
                             time_stamp=self.game_start_time)

        if isinstance(packet, net_classes.UAMessageMessage):
            print("New message: {}".format(packet.message))
            if packet.message == "!start":
                self.start_game()
                return
            if packet.message == "!level":
                self.change_level()
                return

        if isinstance(packet, net_classes.Generic):
            if packet.msg_type == "UAMSG_VHCLDATA_I":
                #return
                pass

        if isinstance(packet, net_classes.NetSysDisconnected):
            player.send_packet(net_classes.NetSysDisconnected())
            self.players.pop(player_addr_port)
            return

        if isinstance(packet, net_classes.UAMessageRequestPing):
            player.send_packet(net_classes.UAMessagePong(timestamp=packet.timestamp))
            return

        if packet.packet_type == net_messages.USR_MSG_DATA and packet.packet_cast:
            for addr_port, p in self.players.items():
                if addr_port != player_addr_port:
                    p.send_packet(packet)

    def is_full(self):
        # Can we add in more players to this game?

        # If the game has started, don't accept any new players
        if self.game_started:
            return False

        # If we have 4 or more players, don't accept any new players
        return len(self.players.keys()) >= 4


def switch_packet(packet, player, games):
    for game in games:  # Can be optimized later
        if player in game:
            # print("Found game that player is in")
            game.packet_received(packet, player)
            return  # Packet was sent to the correct game so let's get more packets

    # Ok so the packet came from a player who wasn't in a game, is it a join request packet?
    if isinstance(packet, net_classes.NetSysHandshake):
        for game in games:
            if not game.is_full():
                # print("Adding player to game")
                game.add_player(packet.client_name, player)
                game.packet_received(packet, player)
                return

    # Either we got an invalid packet from someone who got dropped from the game or
    # someone is messing with us.
    # Or we restarted the dedicated server while games were running.
    raise RuntimeError("How did you end up here?")


def main():
    # Server code
    dedicated_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dedicated_server_socket.setblocking(False)
    dedicated_server_socket.bind(("127.0.0.1", 61234))

    games = [UAMPGame(sock=dedicated_server_socket)]  # Start the server with one game

    while True:
        try:
            time.sleep(0.001)  # sleep 1 ms
            # Receive data from players
            data, player = dedicated_server_socket.recvfrom(1024)  # player is a tuple (remote_addr, remote_port)
            # Convert the raw data to an object
            packet = net_classes.data_to_class(data)

            switch_packet(packet, player, games)
        except BlockingIOError:
            pass


if __name__ == "__main__":
    main()
