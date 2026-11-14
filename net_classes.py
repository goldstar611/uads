import os
import struct

import net_messages


class Generic:
    def __init__(self, msg_type=None, data=None):
        self._data = b""
        self.msg_type = msg_type
        
        if data:
            self.data = data

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value

        if len(value) > 36:
            self.packet_flags, self.sequence_id, self.channel, self.packet_type = struct.unpack_from("<BIBB", value, 0)
            self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
            self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
            self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)


class Part:
    def __init__(self, sequence_id=0, channel=0, full_size=0, offset=0, part_data=b'', data=None):
        # data=b"01 9d000000 01 a6050000 00000000 ..."
        self.packet_flags = net_messages.PKT_FLAG_PART
        self.sequence_id = sequence_id
        self.channel = channel
        self.full_size = full_size
        self.offset = offset
        self.part_data = part_data
        if data:
            self.data = data
            # print(f"seq: {self.sequence_id}, ch: {self.channel}, size: {self.full_size}, "
            #      f"offset: {self.offset}, data_len: {len(self.part_data)}")
    
        self._reconstructed_packet = bytearray(full_size)
        self._reconstructed_size = 0
        self.add_part_data(self.offset, self.part_data)
    
    @property
    def data(self):
        ret = struct.pack("<BIBII", self.packet_flags, self.sequence_id, self.channel, self.full_size, self.offset)
        ret += self.part_data
        return ret
    
    @data.setter
    def data(self, value):
        self.sequence_id, self.channel, self.full_size, self.offset = struct.unpack_from("<IBII", value, 1)
        self.part_data = bytearray(value[14:])
    
    def add_part_data(self, offset, part_data):
        start = offset
        end = start + len(part_data)
        self._reconstructed_packet[start:end] = part_data
        self._reconstructed_size += len(part_data)
        
    def is_complete(self):
        return self._reconstructed_size >= self.full_size

    def reconstructed_packet(self):
        # Set flags to PKT_FLAG_MASK_NORMAL and append reconstructed packet
        header = struct.pack("<BIB", net_messages.PKT_FLAG_GARANT, self.sequence_id, self.channel)
        return header + self._reconstructed_packet


class NetSysHandshake:
    def __init__(self, client_name, data=None):
        # data=b"80 01 16 07 UA:SOURCE TEST NETWORKUnnamed"
        self.packet_flags = net_messages.PKT_FLAG_SYSTEM
        self.packet_type = net_messages.SYS_MSG_HANDSHAKE
        self.network_name = "UA:SOURCE TEST NETWORK"
        self.client_name = client_name
        if data:
            self.data = data

    def __repr__(self):
        return f'<NetSysHandshake(network_name="{self.network_name}", client_name="{self.client_name}")>'

    @property
    def data(self):
        ret = struct.pack("<BBBB", self.packet_flags, self.packet_type, len(self.network_name), len(self.client_name))
        ret += self.network_name.encode() + self.client_name.encode()
        return ret

    @data.setter
    def data(self, value):
        offset = 2
        network_name_length, client_name_length = struct.unpack_from("<BB", value, offset)
        self.network_name = value[4: 4 + network_name_length].decode()
        self.client_name = value[4 + network_name_length: 4 + network_name_length + client_name_length].decode()


class NetSysConnected:
    def __init__(self, client_name, client_id, data=None):
        # data=b"80 02 00 57a58b042c000000 0c Unnamed.8319"
        self.packet_flags = net_messages.PKT_FLAG_SYSTEM
        self.packet_type = net_messages.SYS_MSG_CONNECTED
        self.has_lobby = 0
        self.user_id = client_id
        self.user_name = client_name
        if data:
            self.data = data

    def __repr__(self):
        return f'<NetSysConnected(client_name="{self.user_name}", client_id="{self.user_id}")>'

    @property
    def data(self):
        ret = struct.pack("<BBB", self.packet_flags, self.packet_type, self.has_lobby)
        ret += struct.pack("<QB", self.user_id, len(self.user_name))
        ret += self.user_name.encode()
        return ret

    @data.setter
    def data(self, value):
        has_lobby, user_id, user_name_len = struct.unpack_from("<BQB", value, 2)
        self.has_lobby = has_lobby
        self.user_id = user_id
        self.user_name = value[12:].decode()


class NetSysDisconnected:
    def __init__(self, data=None):
        # data=b"80 03"
        self.packet_flags = net_messages.PKT_FLAG_SYSTEM
        self.packet_type = net_messages.SYS_MSG_DISCONNECT
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BB", self.packet_flags, self.packet_type)
        return ret

    @data.setter
    def data(self, value):
        pass  # Nothing to do here


class NetSysRetry:
    def __init__(self, sequence_id=0, from_off=0, up_to=0, data=None):
        # data=b"80 08 0c000000 40000000 80000000"
        self.packet_flags = net_messages.PKT_FLAG_SYSTEM
        self.packet_type = net_messages.SYS_MSG_RETRY
        self.sequence_id = sequence_id
        self.from_off = from_off
        self.up_to = up_to
        if data:
            self.data = data

    def __repr__(self):
        return f'<NetSysRetry(sequence_id="{self.sequence_id}", from="{self.from_off}", upto="{self.up_to}")>'

    @property
    def data(self):
        ret = struct.pack("<BBIII", self.packet_flags, self.packet_type,
                          self.sequence_id, self.from_off, self.up_to)
        return ret

    @data.setter
    def data(self, value):
        self.sequence_id, self.from_off, self.up_to = struct.unpack_from("<III", value, 2)


class NetSysPing:
    def __init__(self, sequence_id=0, data=None):
        # data=b"80 05 01000000"
        self.packet_flags = net_messages.PKT_FLAG_SYSTEM
        self.packet_type = net_messages.SYS_MSG_PING
        self.sequence_id = sequence_id
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BBI", self.packet_flags, self.packet_type, self.sequence_id)
        return ret

    @data.setter
    def data(self, value):
        self.sequence_id = struct.unpack_from("<I", value, 2)[0]


class NetSysDelivered(NetSysPing):
    def __init__(self, sequence_id=0, data=None):
        # data=b"80 07 01000000"
        super().__init__(sequence_id=sequence_id, data=data)
        self.packet_type = net_messages.SYS_MSG_DELIVERED

    # This class inherits .data() from NetSysPing


class NetSysSessionJoin:
    def __init__(self, game_id, level_number, hoster_name, data=None):
        # data=b"80 40 01 b820cc1129000000 20 93|Unnamed|JUL 09 1988  23:52:47"
        self.packet_flags = net_messages.PKT_FLAG_SYSTEM
        self.packet_type = net_messages.SYS_MSG_SES_JOIN
        self.leader = 0
        self.game_id = game_id
        # TODO Keep an eye on password being used here
        # https://github.com/Marisa-Chan/UA_source/blob/9b205a639b1043b230e1ed8fc81f567bb06c7eb7/src/netlib/server.cpp#L228
        self.level_number = level_number
        self.server_name = hoster_name
        self.build_date = "JUL 09 1998  23:52:47"
        if data:
            self.data = data

    def __repr__(self):
        return f'<NetSysSessionJoin(leader="{self.leader}", game_id="{self.game_id}, ' \
               f'level_number={self.level_number}, server_name={self.server_name}, build_date={self.build_date}")>'

    @property
    def data(self):
        ret = struct.pack("<BBB", self.packet_flags, self.packet_type, self.leader)
        id_server_name_build_date = f"{self.level_number}|{self.server_name}|{self.build_date}"
        ret += struct.pack("<QB", self.game_id, len(id_server_name_build_date))
        ret += id_server_name_build_date.encode()
        return ret

    @data.setter
    def data(self, value):
        self.leader, self.game_id = struct.unpack_from("<BQ", value, 2)
        id_server_name_build_date = value[12:].decode()
        level_id, self.server_name, self.build_date = id_server_name_build_date.split("|")
        self.level_number = int(level_id)


class NetSysSessionClose:
    def __init__(self, data=None):
        # data=b"80 46 00000000"
        self.packet_flags = net_messages.PKT_FLAG_SYSTEM
        self.packet_type = net_messages.SYS_MSG_SES_CLOSE
        self.close_time = 0
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BBI", self.packet_flags, self.packet_type, self.close_time)
        return ret

    @data.setter
    def data(self, value):
        self.close_time = struct.unpack_from("<I", value, 2)[0]


class NetSysSessionLead:
    def __init__(self, data=None):
        # data=b"80 42 01"
        self.packet_flags = net_messages.PKT_FLAG_SYSTEM
        self.packet_type = net_messages.SYS_MSG_SES_LEAD
        self.is_leader = 1
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BBB", self.packet_flags, self.packet_type, self.is_leader)
        return ret

    @data.setter
    def data(self, value):
        self.is_leader,  = struct.unpack_from("<B", value, 2)[0]


class NetUsrSessionList:
    def __init__(self, users, sequence_id=1, data=None):
        # data=b"00 01000000 00 42 02000000 691ecc1129000000 07 Unnamed 57a58b042c000000 0c Unnamed.1883"
        self.packet_flags = net_messages.PKT_FLAG_NONE
        self.sequence_id = sequence_id
        self.channel = 0
        self.packet_type = net_messages.USR_MSG_SES_USERLIST

        self.users = users  # {client_name: client_id, ...}
        if data:
            self.data = data

    def __repr__(self):
        return f'<NetUsrSessionList(users="{self.users}")>'

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<I", len(self.users.keys()))
        for user in self.users:
            ret += struct.pack("<QB", self.users[user], len(user))
            ret += user.encode()
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel, num_users = struct.unpack_from("<BIBxI", value, 0)
        self.users = {}

        offset = 11
        for i in range(num_users):
            user_id, user_len = struct.unpack_from("<QB", value, offset)
            offset += 9
            user_name = value[offset:offset + user_len].decode()
            offset += user_len
            self.users[user_name] = user_id


class NetUsrDisconnect:
    def __init__(self, player_id, sequence_id=0, data=None):
        # data=b"00 0c000000 00 41 a08e5ddd0a030000 01"
        self.packet_flags = net_messages.PKT_FLAG_NONE
        self.sequence_id = sequence_id
        self.channel = 0
        self.packet_type = net_messages.USR_MSG_SES_USERLEAVE

        self.player_id = player_id
        self.cast = 1
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QB", self.player_id, self.cast)

        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel, self.packet_type = struct.unpack_from("<BIBB", value, 0)
        self.player_id, self.cast = struct.unpack_from("<QB", value, 7)


class NetUsrJoin:
    def __init__(self, client_name, client_id, sequence_id=0, data=None):
        # data=b"00 04000000 00 40 48b80105da4a0200 08 556e6e616d656433"
        #                                              U n n a m e d 3
        self.packet_flags = net_messages.PKT_FLAG_NONE
        self.sequence_id = sequence_id
        self.channel = 0
        self.packet_type = net_messages.USR_MSG_SES_USERJOIN

        self.user_id = client_id
        self.user_name = client_name

        if data:
            self.data = data

    def __repr__(self):
        return f'<NetUsrJoin(user_id="{self.user_id}", user_name="{self.user_name}")>'

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QB", self.user_id, len(self.user_name))
        ret += self.user_name.encode()
        return ret

    @data.setter
    def data(self, value):
        sequence_id, channel, packet_type, user_id, username_len = struct.unpack_from("<IBBQB", value, 1)
        self.sequence_id = sequence_id
        self.channel = channel
        self.user_id = user_id
        self.user_name = value[16:].decode()


class UAMessageWelcome:
    def __init__(self, to_id, from_id, sequence_id=2, faction=0, data=None):
        # UA_source >= 330eb51 (2022-11-07): uamessage_welcome is fraction(i16) + rdy(u8),
        # payload = 19 bytes (0x13). The old trailing "cd" byte was removed from the engine.
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = sequence_id
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 0
        self.packet_to = to_id
        self.packet_payload_length = 0x13
        self.message_id = net_messages.UAMSG_WELCOME
        self.message_count = 0
        self.my_timestamp = 0
        self.owner = 0
        self.p0 = 0
        self.p1 = 0
        self.p2 = 0

        self.faction = faction
        self.ready = 0
        if data:
            self.data = data

    def __repr__(self):
        return f'<UAMessageWelcome(packet_from="{self.packet_from}", packet_cast="{self.packet_cast}", ' \
               f'packet_to="{self.packet_to}", message_count="{self.message_count}", ' \
               f'my_timestamp="{self.my_timestamp}", owner="{self.owner}", p0="{self.p0}", ' \
               f'p1="{self.p1}", p2="{self.p2}", faction="{self.faction}", ' \
               f'ready="{self.ready}")>'

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<HB", self.faction, self.ready)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.faction, self.ready = struct.unpack_from("<HB", value, 44)


class UAMessageSetLevel:
    def __init__(self, to_id, from_id, sequence_id=2, level_number=0, host_name="uads", data=None):
        # uamessage_setLevel / uamessage_lobbyInit (yw_net.h:376): base(16) +
        # hostName char[64] + lvlID u32 + fractions[4] = 88 bytes. The engine
        # lobby learns the level ONLY from this message (yw_net.cpp:2659
        # SETLEVEL handler and the LOBBYINIT handler sent to joiners) - the
        # level inside the SES_JOIN session name is not enough on reconnect.
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = sequence_id
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 0
        self.packet_to = to_id
        self.packet_payload_length = 88
        self.message_id = net_messages.UAMSG_SETLEVEL
        self.message_count = 0
        self.my_timestamp = 0
        self.owner = 0
        self.p0 = 0
        self.p1 = 0
        self.p2 = 0

        self.host_name = host_name
        self.level_number = level_number
        if data:
            self.data = data

    def __repr__(self):
        return f'<UAMessageSetLevel(packet_from="{self.packet_from}", packet_to="{self.packet_to}", ' \
               f'level_number="{self.level_number}", host_name="{self.host_name}")>'

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += self.host_name.encode()[:64].ljust(64, b"\x00")
        ret += struct.pack("<I", self.level_number)
        ret += b"\x00" * 4
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.host_name = value[44:108].split(b"\x00")[0].decode()
        self.level_number = struct.unpack_from("<I", value, 108)[0]


class UAMessageReady:
    def __init__(self, to_id, from_id, sequence_id=3, data=None):
        # data=b'02 16000000 01 10 bbbbfd37c8a3aaaa 01 c9ec98ee6be20000 14000000 ff030000 20420200 01000000 00 00 00 00 00 00 00 00'
        # data=b'02 15000000 01 10 bbbbfd37c8a3aaaa 01 c9ec98ee6be20000 14000000 ff030000 20420200 00000000 00 00 00 00 01 00 00 00'

        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = sequence_id
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 1
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_READY

        self.message_count = 0
        self.my_timestamp = 0
        self.owner = 0
        self.p0 = 0
        self.p1 = 0
        self.p2 = 0

        self.ready = 0
        self.rp0 = 0
        self.rp1 = 0
        self.rp2 = 0
        if data:
            self.data = data

    def __repr__(self):
        return f'<UAMessageReady(packet_from="{self.packet_from}", packet_cast="{self.packet_cast}", ' \
               f'packet_to="{self.packet_to}", message_count="{self.message_count}", ' \
               f'my_timestamp="{self.my_timestamp}", owner="{self.owner}", p0="{self.p0}", ' \
               f'p1="{self.p1}", p2="{self.p2}", ready="{self.ready}", ' \
               f'rp0="{self.rp0}", rp1="{self.rp1}", rp2="{self.rp2}")>'

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<BBBB", self.ready, self.rp0, self.rp1, self.rp2)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.ready, self.rp0, self.rp1, self.rp2 = struct.unpack_from("<BBBB", value, 44)


class UAMessageCRC:
    def __init__(self, to_id, from_id, sequence_id=3, data=None):
        # data=b"02 02000000 01 10 691ecc1129000000 00 b820cc1129000000 14000000 0d040000 00000000 b0a187d5 00 55 00 00 2ab4c182"
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = sequence_id
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 1
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_CRC
        self.message_count = 0
        self.my_timestamp = 0
        self.owner = 0
        self.p0 = 0
        self.p1 = 0
        self.p2 = 0

        self.checksum = struct.unpack("<I", b"\x2a\xb4\xc1\x82")[0]
        if data:
            self.data = data

    def __repr__(self):
        return f'<UAMessageCRC(packet_from="{self.packet_from}", packet_cast="{self.packet_cast}", ' \
               f'packet_to="{self.packet_to}", message_count="{self.message_count}", ' \
               f'my_timestamp="{self.my_timestamp}", owner="{self.owner}", p0="{self.p0}", ' \
               f'p1="{self.p1}", p2="{self.p2}", checksum="{self.checksum}")>'

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<I", self.checksum)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.checksum = struct.unpack_from("<I", value, 44)[0]


class UAMessageCD:
    def __init__(self, to_id, from_id, sequence_id=0, data=None):
        # data=b"02 02000000 01 10 691ecc1129000000 00 b820cc1129000000 14000000 12040000 00000000 a04b1000 00 61 00 00 01 ff 00 00"
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = sequence_id
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 1
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_CD
        self.message_count = 0
        self.my_timestamp = 0
        self.owner = 0
        self.p0 = 0x61
        self.p1 = 0
        self.p2 = 0

        self.cd = 1
        self.ready = 255
        self.cd_p0 = 1
        self.cd_p1 = 1
        if data:
            self.data = data

    def __repr__(self):
        return f'<UAMessageCD(user_id="{self.packet_from}", packet_cast="{self.packet_cast}", ' \
               f'packet_to="{self.packet_to}", message_count="{self.message_count}", ' \
               f'my_timestamp="{self.my_timestamp}", owner="{self.owner}", p0="{self.p0}", ' \
               f'p1="{self.p1}", p2="{self.p2}", ready="{self.ready}", cd="{self.cd}", ' \
               f'cd_p0="{self.cd_p0}", cd_p1="{self.cd_p1}")>'

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<BBBB", self.cd, self.ready, self.cd_p0, self.cd_p1)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.cd, self.ready, self.cd_p0, self.cd_p1 = struct.unpack_from("<BBBB", value, 44)


class UAMessageFaction:
    def __init__(self, to_id, from_id, data=None):
        # data=b"02 02000000 01 10 691ecc1129000000 00 b820cc1129000000 14000000 fd030000 00000000 20754s48 00 7f 00 00 0000 0200"
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = 0
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 0
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_FACTION
        self.message_count = 0
        self.my_timestamp = 0
        self.owner = 0
        self.p0 = 0x7f
        self.p1 = 0
        self.p2 = 0

        self.new = 1
        self.old = 1
        if data:
            self.data = data

    def __repr__(self):
        return f'<UAMessageFaction(user_id="{self.packet_from}", packet_cast="{self.packet_cast}", ' \
               f'packet_to="{self.packet_to}", message_count="{self.message_count}", ' \
               f'my_timestamp="{self.my_timestamp}", owner="{self.owner}", p0="{self.p0}", ' \
               f'p1="{self.p1}", p2="{self.p2}", new="{self.new}", old="{self.old}")>'

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<HH", self.old, self.new)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.old, self.new = struct.unpack_from("<HH", value, 44)


class UAMessageLoadGame:
    def __init__(self, to_id, from_id, level_number, sequence_id=0, my_timestamp=0, data=None):
        # data=b"02 06000000 01 10 691ecc1129000000 00 b820cc1129000000 14000000 e8030000 00000000 00640000 00 61 00 00 5d000000"
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = sequence_id
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 0
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_LOAD
        self.message_count = 0
        self.my_timestamp = my_timestamp
        self.owner = 0
        self.p0 = 0x61
        self.p1 = 0
        self.p2 = 0

        self.level_number = level_number
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<I", self.level_number)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.level_number = struct.unpack_from("<I", value, 44)[0]


class UAMessageMessage:
    def __init__(self, to_id, from_id, sequence_id=0, message="", my_timestamp=0, data=None):
        # data=b'02 02000000 01 10 57a58b042c000000 01 b820cc1129000000 50000000 fa030000 00000000 02000000 00 00 00 00 64000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = sequence_id
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 1
        self.packet_to = to_id
        self.packet_payload_length = 0x50
        self.message_id = net_messages.UAMSG_MESSAGE
        self.message_count = 0
        self.my_timestamp = my_timestamp
        self.owner = 0
        self.p0 = 0x0
        self.p1 = 0
        self.p2 = 0

        self.message = message
        if data:
            self.data = data

    @property
    def data(self):
        msg = bytearray(64)
        msg_len = min(len(self.message), 64)
        msg[:msg_len] = self.message[:msg_len].encode()

        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += msg
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.message = value[44:].decode()
        self.message = self.message[:self.message.index("\x00")]


class UAMessageSyncGame:
    def __init__(self, to_id, from_id, my_timestamp=0, data=None):
        # data=b"02 0c000000 01 10 CCCCCCCCCCCCCCCC 01 BBBBBBBBBBBBBBBB 34000000 f7030000 00000000 00000000 01 62 00 00
        #        00000101 04000101 03000101 02000101 01000101 ff0f0000 1b5392e8 6f7f0000 e009d1c9"
        #        host_id  gun0     gun1     gun2     gun3     gun4     gun5     gun6     gun7
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = 0
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 1
        self.packet_to = to_id
        self.packet_payload_length = 0x34
        self.message_id = net_messages.UAMSG_SYNCGM
        self.message_count = 0
        self.my_timestamp = my_timestamp
        self.owner = 1
        self.p0 = 0x61
        self.p1 = 0
        self.p2 = 0

        self.host_id = struct.unpack("<I", b"\x00\x00\x01\x01")[0]
        self.gun0 = struct.unpack("<I", b"\x04\x00\x01\x01")[0]
        self.gun1 = struct.unpack("<I", b"\x03\x00\x01\x01")[0]
        self.gun2 = struct.unpack("<I", b"\x02\x00\x01\x01")[0]
        self.gun3 = struct.unpack("<I", b"\x01\x00\x01\x01")[0]
        self.gun4 = struct.unpack("<I", b"\xff\x0f\x00\x00")[0]
        self.gun5 = struct.unpack("<I", b"\x1b\x53\x92\xe8")[0]
        self.gun6 = struct.unpack("<I", b"\x6f\x7f\x00\x00")[0]
        self.gun7 = struct.unpack("<I", b"\xe0\x09\xd1\xc9")[0]
        if data:
            self.data = data

    def __repr__(self):
        return f"<UAMessageSyncGame(host_id={self.host_id}, " \
               f"gun0={self.gun0}, gun1={self.gun1}, gun2={self.gun2}, gun3={self.gun3}, " \
               f"gun4={self.gun4}, gun5={self.gun5}, gun6={self.gun6}, gun7={self.gun7}"

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<IIIIIIIII", self.host_id, self.gun0, self.gun1, self.gun2, self.gun3, self.gun4,
                           self.gun5, self.gun6, self.gun7)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.host_id, self.gun0, self.gun1, self.gun2, self.gun3, self.gun4, self.gun5, self.gun6, self.gun7 = struct.unpack_from("<IIIIIIIII", value, 44)


class UAMessageViewer:
    def __init__(self, to_id, from_id, my_timestamp=0, data=None):
        # data=b"02 07000000 01 10 691ecc1129000000 01 b820cc1129000000
        #        1c000000 f6030000 00000000 0077450d 01 ce 3e 93 00000101 fd7f0000 03 01 da 15"
        #                                                        id       launcher
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = 0
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 1
        self.packet_to = to_id
        self.packet_payload_length = 0x1c
        self.message_id = net_messages.UAMSG_VIEWER
        self.message_count = 0
        self.my_timestamp = my_timestamp
        self.owner = 1
        self.p0 = 0x61
        self.p1 = 0
        self.p2 = 0

        self.host_id = struct.unpack("<I", b"\x00\x00\x01\x01")[0]
        self.launcher = struct.unpack("<I", b"\xfd\x7f\x00\x00")[0]
        self.class_id = 3
        self.view = 1
        self.vp0 = 0xda
        self.vp1 = 0x15
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<IIBBBB", self.host_id, self.launcher, self.class_id, self.view, self.vp0, self.vp1)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.host_id, self.launcher, self.class_id, self.view, self.vp0, self.vp1 = struct.unpack_from("<IIBBBB", value, 44)


class UAMessageRequestPing:
    def __init__(self, to_id, from_id, sequence_id=0, timestamp=0, my_timestamp=0, data=None):
        # data=b"02 07000000 01 10 691ecc1129000000 01 b820cc1129000000
        #        14000000 f6030000 00000000 0077450d 01 55 00 00 00000101"
        #                                                        timestamp
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = sequence_id
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 1
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_REQPING
        self.message_count = 0
        self.my_timestamp = my_timestamp
        self.owner = 1
        self.p0 = 0x55
        self.p1 = 0
        self.p2 = 0

        self.timestamp = timestamp
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<I", self.timestamp)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.message_count, self.my_timestamp = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.timestamp = struct.unpack_from("<I", value, 44)[0]


class UAMessagePong(UAMessageRequestPing):
    def __init__(self, to_id=0, from_id=0, timestamp=0, my_timestamp=0, data=None):
        super(UAMessagePong, self).__init__(to_id=to_id, from_id=from_id,
                                            timestamp=timestamp, my_timestamp=my_timestamp, data=data)
        self.message_id = net_messages.UAMSG_PONG


class DataToClassException(Exception):
    pass


def _dprint(msg):
    # Decode-path noise: only shown with UADS_DEBUG set. Drop diagnostics
    # (UADS-SPLIT ...) stay unconditional.
    if os.environ.get("UADS_DEBUG"):
        print(msg)


def data_to_class(data):
    try:
        # Every message has packet flags
        flags = data[0]

        #
        # Multipart messages
        #
        if flags & net_messages.PKT_FLAG_PART:
            _dprint("PKT_FLAG_PART")
            return Part(data=data)

        #
        # System messages
        #
        if flags & net_messages.PKT_FLAG_MASK_SYSTEM:
            system_message = data[1]

            if system_message == net_messages.SYS_MSG_HANDSHAKE:
                _dprint("SYS_MSG_HANDSHAKE")
                return NetSysHandshake(client_name=None, data=data)

            if system_message == net_messages.SYS_MSG_CONNECTED:
                _dprint("SYS_MSG_CONNECTED")
                return NetSysConnected(client_id=None, client_name=None, data=data)

            if system_message == net_messages.SYS_MSG_DISCONNECT:
                _dprint("SYS_MSG_DISCONNECT")
                return NetSysDisconnected(data=data)

            if system_message == net_messages.SYS_MSG_PING:
                # print("SYS_MSG_PING\n")
                return NetSysPing(data=data)

            if system_message == net_messages.SYS_MSG_DELIVERED:
                # print("SYS_MSG_DELIVERED\n")
                return NetSysDelivered(data=data)

            if system_message == net_messages.SYS_MSG_RETRY:
                _dprint("SYS_MSG_RETRY")
                return NetSysRetry(data=data)

            if system_message == net_messages.SYS_MSG_SES_JOIN:
                _dprint("SYS_MSG_SES_JOIN")
                return NetSysSessionJoin(game_id=None, hoster_name=None, level_number=0, data=data)

            if system_message == net_messages.SYS_MSG_SES_CLOSE:  # Host sends this message when it closes the server
                _dprint("SYS_MSG_SES_CLOSE")
                return NetSysSessionClose(data=data)

            raise ValueError("Unknown system message!\n")

        #
        # User messages
        #
        sequence_id = data[1:5]
        channel = data[5]
        user_message = data[6]

        if user_message == net_messages.USR_MSG_SES_USERLIST:
            _dprint("USR_MSG_SES_USERLIST")
            return NetUsrSessionList(users=None, data=data)

        if user_message == net_messages.USR_MSG_DATA:
            source = struct.unpack_from("<Q", data, 7)[0]
            cast = struct.unpack_from("<B", data, 15)[0]
            destination = struct.unpack_from("<Q", data, 16)[0]
            data_size = struct.unpack_from("<I", data, 24)[0]
            ua_message = struct.unpack_from("<I", data, 28)[0]

            if ua_message == net_messages.UAMSG_LOAD:
                _dprint("UAMSG_LOAD")
                return UAMessageLoadGame(to_id=None, level_number=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_NEWVHCL:
                _dprint("UAMSG_NEWVHCL")
                return Generic(msg_type="UAMSG_NEWVHCL", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_DESTROYVHCL:
                _dprint("UAMSG_DESTROYVHCL")
                return Generic(msg_type="UAMSG_DESTROYVHCL", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_NEWWEAPON:
                _dprint("UAMSG_NEWWEAPON")
                return Generic(msg_type="UAMSG_NEWWEAPON", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_SETSTATE:
                _dprint("UAMSG_SETSTATE")
                return Generic(msg_type="UAMSG_SETSTATE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_VHCLDATA_I:
                # send vehicle data updates such as location
                # print("UAMSG_VHCLDATA_I\n")
                return Generic(msg_type="UAMSG_VHCLDATA_I", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_DEAD:
                _dprint("UAMSG_DEAD")
                return Generic(msg_type="UAMSG_DEAD", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_VHCLENERGY:
                _dprint("UAMSG_VHCLENERGY")
                return Generic(msg_type="UAMSG_VHCLENERGY", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_SECTORENERGY:
                # conquer sector
                _dprint("UAMSG_SECTORENERGY")
                return Generic(msg_type="UAMSG_SECTORENERGY", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_STARTBUILD:
                # conquer sector
                _dprint("UAMSG_STARTBUILD")
                return Generic(msg_type="UAMSG_STARTBUILD", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_VIEWER:
                _dprint("UAMSG_VIEWER")
                return UAMessageViewer(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_SYNCGM:
                _dprint("UAMSG_SYNCGM")
                return UAMessageSyncGame(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_HOSTDIE:
                _dprint("UAMSG_HOSTDIE")
                return Generic(msg_type="UAMSG_HOSTDIE", data=data)

            if ua_message == net_messages.UAMSG_MESSAGE:  # When someone sends a message
                _dprint("UAMSG_MESSAGE")
                return UAMessageMessage(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_FACTION:
                _dprint("UAMSG_FACTION")
                return UAMessageFaction(to_id=None, from_id=None, data=data)

            if ua_message in (net_messages.UAMSG_SETLEVEL, net_messages.UAMSG_LOBBYINIT):
                return UAMessageSetLevel(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_UPGRADE:
                _dprint("UAMSG_UPGRADE")
                return Generic(msg_type="UAMSG_UPGRADE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_WELCOME:
                _dprint("UAMSG_WELCOME")
                return UAMessageWelcome(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_READY:
                _dprint("UAMSG_READY")
                return UAMessageReady(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_REQUPDATE:
                _dprint("UAMSG_REQUPDATE")
                return Generic(msg_type="UAMSG_REQUPDATE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_UPDATE:
                _dprint("UAMSG_UPDATE")
                return Generic(msg_type="UAMSG_UPDATE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_IMPULSE:
                _dprint("UAMSG_IMPULSE")
                return Generic(msg_type="UAMSG_IMPULSE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_LOGMSG:
                _dprint("UAMSG_LOGMSG")
                return Generic(msg_type="UAMSG_LOGMSG", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_REORDER:
                _dprint("UAMSG_REORDER")
                return Generic(msg_type="UAMSG_REORDER", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_STARTPLASMA:
                _dprint("UAMSG_STARTPLASMA")
                return Generic(msg_type="UAMSG_STARTPLASMA", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_ENDPLASMA:
                _dprint("UAMSG_ENDPLASMA")
                return Generic(msg_type="UAMSG_ENDPLASMA", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_STARTBEAM:
                _dprint("UAMSG_STARTBEAM")
                return Generic(msg_type="UAMSG_STARTBEAM", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_ENDBEAM:
                _dprint("UAMSG_ENDBEAM")
                return Generic(msg_type="UAMSG_ENDBEAM", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_EXIT:
                _dprint("UAMSG_EXIT")  # Ghorkovs have left the game
                return Generic(msg_type="UAMSG_EXIT", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_CRC:
                _dprint("UAMSG_CRC")
                return UAMessageCRC(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_REQPING:
                _dprint("UAMSG_REQPING")
                return Generic(msg_type="UAMSG_REQPING", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_PONG:
                _dprint("UAMSG_PONG")
                return Generic(msg_type="UAMSG_PONG", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_CD:
                # print("UAMSG_CD\n")
                return UAMessageCD(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_SCORE:
                _dprint("UAMSG_SCORE")
                return Generic(msg_type="UAMSG_SCORE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_BUILDINGVHCL:
                _dprint("UAMSG_BUILDINGVHCL")
                return Generic(msg_type="UAMSG_BUILDINGVHCL", data=data)  # TODO FIXME

            _dprint(f"seq:{sequence_id}, ch: {channel}, usr_msg: {user_message}\n"
                  f"src: {source} cast: {cast}, dst: {destination}, data_size: {data_size}\n"
                  f"ua_message: {ua_message}")
            raise ValueError(f"Unknown UA message! {ua_message}\n")

        _dprint(f"seq:{sequence_id}, ch: {channel}, usr_msg: {user_message}")
        raise ValueError(f"Unknown message! {data}\n")
    except Exception:
        raise DataToClassException()


# Fixed sizeof(uamessage_*) per UA message id (yw_net.h), for walking
# concatenated UA messages inside one USR_MSG_DATA payload. The engine
# buffers broadcasts (windp.cpp QueueBroadcast, 864f389) so several messages
# often arrive as one stream; clients parse them back-to-back using these
# sizes (yw_net.cpp:3346). Sizes verified by compiling a sizeof-dump against
# the real yw_net.h (uamessage_base=16; logmsg=44, score=44, welcome=20,
# vhclData=24 differ from the old hand-counted table).
UA_MSG_SIZES = {
    net_messages.UAMSG_LOAD: 20,
    net_messages.UAMSG_NEWVHCL: 56,     # vec3d pos = 3 doubles (24B, align 8)
    net_messages.UAMSG_DESTROYVHCL: 24,
    net_messages.UAMSG_NEWLEADER: 24,
    net_messages.UAMSG_NEWWEAPON: 104,  # 3 vec3d
    net_messages.UAMSG_SETSTATE: 32,
    net_messages.UAMSG_DEAD: 32,
    net_messages.UAMSG_VHCLENERGY: 32,
    net_messages.UAMSG_SECTORENERGY: 56,  # vec3d pos + energy + whoHit + u8 + 3 pad (align 8)
    net_messages.UAMSG_STARTBUILD: 24,
    net_messages.UAMSG_BUILDINGVHCL: 528,  # base 16 + 8 x 64 (id + 2 x vec3d(24) + i16 + 2 pad, 8-aligned)
    net_messages.UAMSG_VIEWER: 28,
    net_messages.UAMSG_SYNCGM: 52,
    net_messages.UAMSG_HOSTDIE: 24,
    net_messages.UAMSG_MESSAGE: 80,
    net_messages.UAMSG_KICK: 80,
    net_messages.UAMSG_UPGRADE: 20,
    net_messages.UAMSG_FACTION: 20,
    net_messages.UAMSG_WELCOME: 20,
    net_messages.UAMSG_READY: 20,
    net_messages.UAMSG_REQUPDATE: 16,
    net_messages.UAMSG_IMPULSE: 88,     # id(4)+pad(4) + vec3d + i32 + f32 + vec3d + f32 + pad(4)
    net_messages.UAMSG_LOGMSG: 44,
    net_messages.UAMSG_LOBBYINIT: 88,
    net_messages.UAMSG_SETLEVEL: 88,
    net_messages.UAMSG_STARTPLASMA: 128,  # vec3d + mat3x3 (9 doubles)
    net_messages.UAMSG_ENDPLASMA: 20,
    net_messages.UAMSG_STARTBEAM: 48,   # vec3d pos
    net_messages.UAMSG_ENDBEAM: 20,
    net_messages.UAMSG_EXIT: 20,
    net_messages.UAMSG_CRC: 20,
    net_messages.UAMSG_REQPING: 20,
    net_messages.UAMSG_PONG: 20,
    net_messages.UAMSG_STARTPROBLEM: 20,
    net_messages.UAMSG_ENDPROBLEM: 20,
    net_messages.UAMSG_CD: 20,
    net_messages.UAMSG_SCORE: 240,      # 8 x TPlayerStatus (7 x int32 = 28)
}

# Variable-size messages: the sender writes its total wire size into the
# message itself; the engine receiver uses it to advance the walk
# (yw_handleNormMsg: VHCLDATA consumes the rest of the datagram via
# msg->_data.size(), UPDATE/REORDER use their sz field). Reading the size
# lets the walk continue PAST these instead of silently dropping every
# message concatenated after them (which ate NEWVHCL and broke mid-game
# vehicle creation/damage).


def _ua_msg_size(msg_id, payload, offset):
    size = UA_MSG_SIZES.get(msg_id)
    if size is not None:
        return size

    if msg_id in (net_messages.UAMSG_VHCLDATA_I, net_messages.UAMSG_VHCLDATA_E):
        # Engine receiver consumes the ENTIRE remaining datagram for VHCLDATA
        # (yw_handleNormMsg: szmsg = msg->_data.size()), so VHCLDATA is always
        # the last message in a USR_MSG_DATA payload. Match that instead of
        # trusting hdr.size (offset 18), which may be stale/zero.
        return len(payload) - offset

    if msg_id == net_messages.UAMSG_UPDATE:
        size = struct.unpack_from("<I", payload, offset + 16)[0]
        return size if 24 <= size <= len(payload) - offset else None

    if msg_id == net_messages.UAMSG_REORDER:
        # base(16) + mode,comm,commID,num(4 each) + sz(u32) at offset 32
        size = struct.unpack_from("<I", payload, offset + 32)[0]
        return size if 24 <= size <= len(payload) - offset else None

    return None  # unknown -> stop the walk


def split_usr_data(raw):
    """Split a USR_MSG_DATA datagram containing several concatenated UA
    messages into one parsed packet object per message.

    Returns a list; every element carries its own sub-datagram in .data.
    Unknown message types stop the walk (they are sent standalone)."""
    try:
        packet_type = struct.unpack_from("<B", raw, 6)[0]
        if packet_type != net_messages.USR_MSG_DATA:
            return []

        payload = raw[28:28 + struct.unpack_from("<I", raw, 24)[0]]

        packets = []
        offset = 0
        while offset + 16 <= len(payload):
            msg_id = struct.unpack_from("<I", payload, offset)[0]
            size = _ua_msg_size(msg_id, payload, offset)
            if size is None:
                print("UADS-SPLIT: unknown msg_id=%d at payload offset %d "
                      "(%d bytes from here to end)" % (msg_id, offset, len(payload) - offset))
                break
            if offset + size > len(payload):
                print("UADS-SPLIT: msg_id=%d at offset %d claims size %d > "
                      "%d remaining" % (msg_id, offset, size, len(payload) - offset))
                break

            sub = raw[:24] + struct.pack("<I", size) + payload[offset:offset + size]
            try:
                pkt = data_to_class(sub)
            except Exception as e:
                msg_id = struct.unpack_from("<I", payload, offset)[0]
                print("UADS-SPLIT: dropping undecodable msg_id=%d at payload "
                      "offset %d (size %d): %s" % (msg_id, offset, size, e))
                pkt = None
            if pkt:
                pkt.data = sub  # each message carries its own datagram, so
                                # relay_packet() can re-frame it separately
                packets.append(pkt)
            offset += size

        consumed = offset
        if consumed != len(payload):
            rest = payload[offset:]
            ids = [getattr(m, "message_id", None) for m in packets]
            print("UADS-SPLIT: walk consumed %d of %d payload bytes after "
                  "messages %s; %d bytes left unaccounted: %r"
                  % (consumed, len(payload), ids, len(rest), rest[:120]))
            _dump_bad_split(raw, offset)
        return packets
    except Exception:
        return []


def _dump_bad_split(raw, walk_offset):
    """Persist the full raw datagram of a bad split for offline analysis."""
    import os
    import time
    d = os.environ.get("UADS_BADSPLIT_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "bad_splits")
    try:
        os.makedirs(d, exist_ok=True)
        name = time.strftime("split_%Y%m%d_%H%M%S") + ".dat"
        with open(os.path.join(d, name), "wb") as f:
            f.write(raw)
        print("UADS-SPLIT: raw datagram saved to %s (walk stopped at "
              "payload offset %d)" % (os.path.join(d, name), walk_offset))
    except OSError as e:
        print("UADS-SPLIT: could not save datagram: %s" % e)
