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
            self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count = struct.unpack_from("<IIII", value, 24)
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
    def __init__(self, sequence_id=None, data=None):
        # data=b"80 07 01000000"
        super().__init__(sequence_id=sequence_id, data=data)
        self.packet_type = net_messages.SYS_MSG_DELIVERED

    # This class inherits .data() from NetSysPing


class NetSysSessionJoin:
    def __init__(self, game_id, level_number, hoster_name, data=None):
        # data=b"80 40 01 b820cc1129000000 20 93|Unnamed|JUL 09 1988  23:52:47"
        self.packet_flags = net_messages.PKT_FLAG_SYSTEM
        self.packet_type = net_messages.SYS_MSG_SES_JOIN
        self.always_one = 1
        self.game_id = game_id
        self.level_number = level_number
        self.server_name = hoster_name
        self.build_date = "JUL 09 1998  23:52:47"
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BBB", self.packet_flags, self.packet_type, self.always_one)
        id_server_name_build_date = f"{self.level_number}|{self.server_name}|{self.build_date}"
        ret += struct.pack("<QB", self.game_id, len(id_server_name_build_date))
        ret += id_server_name_build_date.encode()
        return ret

    @data.setter
    def data(self, value):
        self.always_one, self.game_id, self.level_number = struct.unpack_from("<BBQ", value, 2)
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
        self.close_time,  = struct.unpack_from("<I", value, 2)[0]


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
    def __init__(self, users, data=None):
        # data=b"00 01000000 00 42 02000000 691ecc1129000000 07 Unnamed 57a58b042c000000 0c Unnamed.1883"
        self.packet_flags = net_messages.PKT_FLAG_NONE
        self.sequence_id = 0
        self.channel = 0
        self.packet_type = net_messages.USR_MSG_SES_USERLIST

        self.users = users  # {client_name: client_id, ...}
        if data:
            self.data = data

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
    def __init__(self, player_id, data=None):
        # data=b"00 0c000000 00 41 a08e5ddd0a030000 01"
        self.packet_flags = net_messages.PKT_FLAG_NONE
        self.sequence_id = 0
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


class UAMessageWelcome:
    def __init__(self, to_id, from_id, faction=0, data=None):
        # data = b"02 02000000 01 10 691ecc1129000000 00 57a58b042c000000 14000000 fe030000 00000000 3a59bba2 00 0f 00 00 0100 01 01"
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = 0
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 0
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_WELCOME
        self.my_timestamp = 0
        self.message_count = 0
        self.owner = 0
        self.p0 = 0x0f
        self.p1 = 0
        self.p2 = 0

        self.faction = faction
        self.ready = 1
        self.cd = 1
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<HBB", self.faction, self.ready, self.cd)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.faction, self.ready, self.cd = struct.unpack_from("<HBB", value, 44)


class UAMessageCRC:
    def __init__(self, to_id, from_id, data=None):
        # data=b"02 02000000 01 10 691ecc1129000000 00 b820cc1129000000 14000000 0d040000 00000000 b0a187d5 00 55 00 00 2ab4c182"
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = 0
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 0
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_CRC
        self.my_timestamp = 0
        self.message_count = 0
        self.owner = 0
        self.p0 = 0x55
        self.p1 = 0
        self.p2 = 0

        self.checksum = struct.unpack("<I", b"\x2a\xb4\xc1\x82")[0]
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<I", self.checksum)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.checksum = struct.unpack_from("<I", value, 44)[0]


class UAMessageCD:
    def __init__(self, to_id, from_id, data=None):
        # data=b"02 02000000 01 10 691ecc1129000000 00 b820cc1129000000 14000000 12040000 00000000 a04b1000 00 61 00 00 01 ff 00 00"
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = 0
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 0
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_CD
        self.my_timestamp = 0
        self.message_count = 0
        self.owner = 0
        self.p0 = 0x61
        self.p1 = 0
        self.p2 = 0

        self.cd = 1
        self.ready = 1
        self.cd_p0 = 1
        self.cd_p1 = 1
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<BBBB", self.cd, self.ready, self.cd_p0, self.cd_p1)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count = struct.unpack_from("<IIII", value, 24)
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
        self.my_timestamp = 0
        self.message_count = 0
        self.owner = 0
        self.p0 = 0x7f
        self.p1 = 0
        self.p2 = 0

        self.new = 1
        self.old = 1
        if data:
            self.data = data

    @property
    def data(self):
        ret = struct.pack("<BIBB", self.packet_flags, self.sequence_id, self.channel, self.packet_type)
        ret += struct.pack("<QBQ", self.packet_from, self.packet_cast, self.packet_to)
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<HH", self.old, self.new)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.old, self.new = struct.unpack_from("<HH", value, 44)


class UAMessageLoadGame:
    def __init__(self, to_id, from_id, level_number, my_timestamp=0, data=None):
        # data=b"02 06000000 01 10 691ecc1129000000 00 b820cc1129000000 14000000 e8030000 00000000 00640000 00 61 00 00 5d000000"
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = 0
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 0
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_LOAD
        self.my_timestamp = my_timestamp
        self.message_count = 0
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
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<I", self.level_number)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.level_number = struct.unpack_from("<I", value, 44)[0]


class UAMessageMessage:
    def __init__(self, to_id, from_id, message="", my_timestamp=0, data=None):
        # data=b'02 02000000 01 10 57a58b042c000000 01 b820cc1129000000 50000000 fa030000 00000000 02000000 00 00 00 00 64000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = 0
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 1
        self.packet_to = to_id
        self.packet_payload_length = 0x50
        self.message_id = net_messages.UAMSG_MESSAGE
        self.my_timestamp = my_timestamp
        self.message_count = 0
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
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += msg
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count = struct.unpack_from("<IIII", value, 24)
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
        self.my_timestamp = my_timestamp
        self.message_count = 0
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
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<IIIIIIIII", self.host_id, self.gun0, self.gun1, self.gun2, self.gun3, self.gun4,
                           self.gun5, self.gun6, self.gun7)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count = struct.unpack_from("<IIII", value, 24)
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
        self.my_timestamp = my_timestamp
        self.message_count = 0
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
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<IIBBBB", self.host_id, self.launcher, self.class_id, self.view, self.vp0, self.vp1)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.host_id, self.launcher, self.class_id, self.view, self.vp0, self.vp1 = struct.unpack_from("<IIBBBB", value, 44)


class UAMessageRequestPing:
    def __init__(self, to_id, from_id, timestamp=0, my_timestamp=0, data=None):
        # data=b"02 07000000 01 10 691ecc1129000000 01 b820cc1129000000
        #        14000000 f6030000 00000000 0077450d 01 55 00 00 00000101"
        #                                                        timestamp
        self.packet_flags = net_messages.PKT_FLAG_GARANT
        self.sequence_id = 0
        self.channel = 1
        self.packet_type = net_messages.USR_MSG_DATA

        self.packet_from = from_id
        self.packet_cast = 1
        self.packet_to = to_id
        self.packet_payload_length = 0x14
        self.message_id = net_messages.UAMSG_REQPING
        self.my_timestamp = my_timestamp
        self.message_count = 0
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
        ret += struct.pack("<IIII", self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count)
        ret += struct.pack("<BBBB", self.owner, self.p0, self.p1, self.p2)
        ret += struct.pack("<I", self.timestamp)
        return ret

    @data.setter
    def data(self, value):
        self.packet_flags, self.sequence_id, self.channel = struct.unpack_from("<BIBx", value, 0)
        self.packet_from, self.packet_cast, self.packet_to = struct.unpack_from("<QBQ", value, 7)
        self.packet_payload_length, self.message_id, self.my_timestamp, self.message_count = struct.unpack_from("<IIII", value, 24)
        self.owner, self.p0, self.p1, self.p2 = struct.unpack_from("<BBBB", value, 40)
        self.timestamp = struct.unpack_from("<I", value, 44)[0]


class UAMessagePong(UAMessageRequestPing):
    def __init__(self, to_id=0, from_id=0, timestamp=0, my_timestamp=0, data=None):
        super(UAMessagePong, self).__init__(to_id=to_id, from_id=from_id,
                                            timestamp=timestamp, my_timestamp=my_timestamp, data=data)
        self.message_id = net_messages.UAMSG_PONG


class DataToClassException(Exception):
    pass


def data_to_class(data):
    try:
        # Every message has packet flags
        flags = data[0]

        #
        # Multipart messages
        #
        if flags & net_messages.PKT_FLAG_PART:
            print("PKT_FLAG_PART")
            return Part(data=data)

        #
        # System messages
        #
        if flags & net_messages.PKT_FLAG_MASK_SYSTEM:
            system_message = data[1]

            if system_message == net_messages.SYS_MSG_HANDSHAKE:
                print("SYS_MSG_HANDSHAKE\n")
                return NetSysHandshake(client_name=None, data=data)

            if system_message == net_messages.SYS_MSG_CONNECTED:
                print("SYS_MSG_CONNECTED\n")
                return NetSysConnected(client_id=None, client_name=None, data=data)

            if system_message == net_messages.SYS_MSG_DISCONNECT:
                print("SYS_MSG_DISCONNECT\n")
                return NetSysDisconnected(data=data)

            if system_message == net_messages.SYS_MSG_PING:
                # print("SYS_MSG_PING\n")
                return NetSysPing(data=data)

            if system_message == net_messages.SYS_MSG_DELIVERED:
                # print("SYS_MSG_DELIVERED\n")
                return NetSysDelivered(data=data)

            if system_message == net_messages.SYS_MSG_SES_JOIN:
                print("SYS_MSG_SES_JOIN\n")
                return NetSysSessionJoin(game_id=None, hoster_name=None, level_number=0, data=data)

            if system_message == net_messages.SYS_MSG_SES_CLOSE:  # Host sends this message when it closes the server
                print("SYS_MSG_SES_CLOSE\n")
                return NetSysSessionClose(data=data)

            raise ValueError("Unknown system message!\n")

        #
        # User messages
        #
        sequence_id = data[1:5]
        channel = data[5]
        user_message = data[6]

        if user_message == net_messages.USR_MSG_SES_USERLIST:
            print("USR_MSG_SES_USERLIST\n")
            return NetUsrSessionList(users=None, data=data)

        if user_message == net_messages.USR_MSG_DATA:
            source = struct.unpack_from("<Q", data, 7)[0]
            cast = struct.unpack_from("<B", data, 15)[0]
            destination = struct.unpack_from("<Q", data, 16)[0]
            data_size = struct.unpack_from("<I", data, 24)[0]
            ua_message = struct.unpack_from("<I", data, 28)[0]

            if ua_message == net_messages.UAMSG_LOAD:
                print("UAMSG_LOAD\n")
                return UAMessageLoadGame(to_id=None, level_number=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_NEWVHCL:
                print("UAMSG_NEWVHCL\n")
                return Generic(msg_type="UAMSG_NEWVHCL", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_DESTROYVHCL:
                print("UAMSG_DESTROYVHCL\n")
                return Generic(msg_type="UAMSG_DESTROYVHCL", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_NEWWEAPON:
                print("UAMSG_NEWWEAPON\n")
                return Generic(msg_type="UAMSG_NEWWEAPON", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_SETSTATE:
                print("UAMSG_SETSTATE\n")
                return Generic(msg_type="UAMSG_SETSTATE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_VHCLDATA_I:
                # send vehicle data updates such as location
                # print("UAMSG_VHCLDATA_I\n")
                return Generic(msg_type="UAMSG_VHCLDATA_I", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_DEAD:
                print("UAMSG_DEAD\n")
                return Generic(msg_type="UAMSG_DEAD", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_VHCLENERGY:
                print("UAMSG_VHCLENERGY\n")
                return Generic(msg_type="UAMSG_VHCLENERGY", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_SECTORENERGY:
                # conquer sector
                print("UAMSG_SECTORENERGY\n")
                return Generic(msg_type="UAMSG_SECTORENERGY", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_STARTBUILD:
                # conquer sector
                print("UAMSG_STARTBUILD\n")
                return Generic(msg_type="UAMSG_STARTBUILD", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_VIEWER:
                print("UAMSG_VIEWER\n")
                return UAMessageViewer(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_SYNCGM:
                print("UAMSG_SYNCGM\n")
                return UAMessageSyncGame(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_HOSTDIE:
                print("UAMSG_HOSTDIE\n")
                return Generic(msg_type="UAMSG_HOSTDIE", data=data)

            if ua_message == net_messages.UAMSG_MESSAGE:  # When someone sends a message
                print("UAMSG_MESSAGE\n")
                return UAMessageMessage(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_FACTION:
                print("UAMSG_FACTION\n")
                return UAMessageFaction(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_UPGRADE:
                print("UAMSG_UPGRADE\n")
                return Generic(msg_type="UAMSG_UPGRADE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_WELCOME:
                print("UAMSG_WELCOME\n")
                return UAMessageWelcome(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_READY:
                print("UAMSG_READY\n")
                return Generic(msg_type="UAMSG_READY", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_REQUPDATE:
                print("UAMSG_REQUPDATE\n")
                return Generic(msg_type="UAMSG_REQUPDATE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_UPDATE:
                print("UAMSG_UPDATE\n")
                return Generic(msg_type="UAMSG_UPDATE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_IMPULSE:
                print("UAMSG_IMPULSE\n")
                return Generic(msg_type="UAMSG_IMPULSE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_LOGMSG:
                print("UAMSG_LOGMSG\n")
                return Generic(msg_type="UAMSG_LOGMSG", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_REORDER:
                print("UAMSG_REORDER\n")
                return Generic(msg_type="UAMSG_REORDER", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_STARTPLASMA:
                print("UAMSG_STARTPLASMA\n")
                return Generic(msg_type="UAMSG_STARTPLASMA", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_ENDPLASMA:
                print("UAMSG_ENDPLASMA\n")
                return Generic(msg_type="UAMSG_ENDPLASMA", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_STARTBEAM:
                print("UAMSG_STARTBEAM\n")
                return Generic(msg_type="UAMSG_STARTBEAM", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_ENDBEAM:
                print("UAMSG_ENDBEAM\n")
                return Generic(msg_type="UAMSG_ENDBEAM", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_EXIT:
                print("UAMSG_EXIT\n")  # Ghorkovs have left the game
                return Generic(msg_type="UAMSG_EXIT", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_CRC:
                print("UAMSG_CRC\n")
                return UAMessageCRC(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_REQPING:
                print("UAMSG_REQPING\n")
                return Generic(msg_type="UAMSG_REQPING", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_PONG:
                print("UAMSG_PONG\n")
                return Generic(msg_type="UAMSG_PONG", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_CD:
                # print("UAMSG_CD\n")
                return UAMessageCD(to_id=None, from_id=None, data=data)

            if ua_message == net_messages.UAMSG_SCORE:
                print("UAMSG_SCORE\n")
                return Generic(msg_type="UAMSG_SCORE", data=data)  # TODO FIXME

            if ua_message == net_messages.UAMSG_BUILDINGVHCL:
                print("UAMSG_BUILDINGVHCL\n")
                return Generic(msg_type="UAMSG_BUILDINGVHCL", data=data)  # TODO FIXME

            print(f"seq:{sequence_id}, ch: {channel}, usr_msg: {user_message}\n"
                  f"src: {source} cast: {cast}, dst: {destination}, data_size: {data_size}\n"
                  f"ua_message: {ua_message}")
            raise ValueError(f"Unknown UA message! {ua_message}\n")

        print(f"seq:{sequence_id}, ch: {channel}, usr_msg: {user_message}")
        raise ValueError(f"Unknown message! {data}\n")
    except Exception:
        raise DataToClassException()
