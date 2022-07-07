import binascii
import socket
import fcntl
import os

from net_messages import *
from net_classes import *

# Client code
upstream_server_ip = "127.0.0.1"
upstream_server_port = 61235
client_sockets = {}


def new_client_socket():
    new_client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.fcntl(new_client_sock, fcntl.F_SETFL, os.O_NONBLOCK)
    return new_client_sock


def inspect(prefix, cli_address, data, from_server=False):
    print(prefix)
    print(binascii.hexlify(data))

    # Every message has packet flags
    flags = data[0]

    #
    # short messages (System)
    #
    if flags & PKT_FLAG_MASK_SYSTEM:
        system_message = data[1]

        if system_message == SYS_MSG_HANDSHAKE:
            cls = NetSysHandshake(data)
            print("SYS_MSG_HANDSHAKE: Client join request\n")
            return

        if system_message == SYS_MSG_CONNECTED:
            cls = NetSysConnected(client_id=None, client_name=None, data=data)
            print("SYS_MSG_CONNECTED: Client join\n")
            return

        if system_message == SYS_MSG_DISCONNECT:
            cls = NetSysDisconnected(data)
            print("SYS_MSG_DISCONNECT: Client leave\n")
            return

        if system_message == SYS_MSG_PING:
            cls = NetSysPing(data)
            print("SYS_MSG_PING\n")
            return

        if system_message == SYS_MSG_DELIVERED:
            cls = NetSysDelivered(data)
            print("SYS_MSG_DELIVERED\n")
            return

        if system_message == SYS_MSG_SES_JOIN:
            cls = NetSysSessionJoin(game_id=None, hoster_name=None, level_number=None, data=data)
            print("SYS_MSG_SES_JOIN: Level Select Message\n")
            return

        if system_message == SYS_MSG_SES_CLOSE:  # Host sends this message when it closes the server
            cls = NetSysSessionClose(data)
            print("SYS_MSG_SES_CLOSE: Socket closed\n")
            return

        print("Unimplemented system message!\n")

    #
    # Long messages (User)
    #
    sequence_id = data[1:5]
    channel = data[5]
    user_message = data[6]

    if user_message == USR_MSG_SES_USERJOIN:
        print("USR_MSG_SES_USERJOIN\n")
        return

    if user_message == USR_MSG_SES_USERLIST:
        print("USR_MSG_SES_USERLIST: Who is in game\n")
        return

    if user_message == USR_MSG_DATA:
        source = struct.unpack_from("<Q", data, 7)[0]
        cast = struct.unpack_from("<B", data, 15)[0]
        destination = struct.unpack_from("<Q", data, 16)[0]
        data_size = struct.unpack_from("<I", data, 24)[0]
        ua_message = struct.unpack_from("<I", data, 28)[0]
        # print("usr msg src: {} cast: {}, dst: {}, data_size: {}".format(source, cast, destination, data_size))

        if ua_message == UAMSG_LOAD:
            print("UAMSG_LOAD: Start game Message\n")
            return
    
        if ua_message == UAMSG_NEWVHCL:
            print("UAMSG_NEWVHCL New vehicle genesis yo\n")
            return
    
        if ua_message == UAMSG_DESTROYVHCL:
            print("UAMSG_DESTROYVHCL\n")
            return
    
        if ua_message == UAMSG_NEWWEAPON:
            print("UAMSG_NEWWEAPON someone fired something!\n")
            return
    
        if ua_message == UAMSG_SETSTATE:
            print("UAMSG_SETSTATE vehicle genesis -> complete or died or sector captured\n")
            return
    
        if ua_message == UAMSG_VHCLDATA_I:
            # send vehicle data updates such as location
            print("UAMSG_VHCLDATA_I\n")
            return
    
        if ua_message == UAMSG_DEAD:
            print("UAMSG_DEAD wah wah\n")
            return
    
        if ua_message == UAMSG_VHCLENERGY:
            print("UAMSG_VHCLENERGY\n")
            return
    
        if ua_message == UAMSG_SECTORENERGY:
            # conquer sector
            print("UAMSG_SECTORENERGY\n")
            return
    
        if ua_message == UAMSG_VIEWER:
            print("UAMSG_VIEWER\n")
            return
    
        if ua_message == UAMSG_SYNCGM:
            cls = UAMessageSyncGame(to_id=None, from_id=None, data=data)
            print("UAMSG_SYNCGM: {}\n".format(cls))
            return

        if ua_message == UAMSG_HOSTDIE:
            print("UAMSG_HOSTDIE:\n")
            return

        if ua_message == UAMSG_MESSAGE:  # When someone sends a message
            print("UAMSG_MESSAGE\n")
            return
    
        if ua_message == UAMSG_FACTION:
            print("UAMSG_FACTION\n")
            return
    
        if ua_message == UAMSG_WELCOME:
            print("UAMSG_WELCOME\n")
            return
    
        if ua_message == UAMSG_READY:
            print("UAMSG_READY\n")
            return
    
        if ua_message == UAMSG_REQUPDATE:
            print("UAMSG_REQUPDATE\n")
            return
    
        if ua_message == UAMSG_UPDATE:
            print("UAMSG_UPDATE\n")
            return
    
        if ua_message == UAMSG_IMPULSE:
            print("UAMSG_IMPULSE\n")
            return
    
        if ua_message == UAMSG_LOGMSG:
            print("UAMSG_LOGMSG\n")
            return
    
        if ua_message == UAMSG_REORDER:
            print("UAMSG_REORDER\n")
            return
    
        if ua_message == UAMSG_STARTPLASMA:
            print("UAMSG_STARTPLASMA\n")
            return
    
        if ua_message == UAMSG_ENDPLASMA:
            print("UAMSG_ENDPLASMA\n")
            return
    
        if ua_message == UAMSG_STARTBEAM:
            print("UAMSG_STARTBEAM\n")
            return
    
        if ua_message == UAMSG_ENDBEAM:
            print("UAMSG_ENDBEAM\n")
            return
    
        if ua_message == UAMSG_EXIT:
            print("UAMSG_EXIT\n")  # Ghorkovs have left the game
            return
    
        if ua_message == UAMSG_CRC:
            print("UAMSG_CRC\n")
            return
    
        if ua_message == UAMSG_REQPING:
            # spammy
            print("UAMSG_REQPING\n")
            return
    
        if ua_message == UAMSG_PONG:
            # spammy
            print("UAMSG_PONG\n")
            return
    
        if ua_message == UAMSG_CD:
            # spammy
            print("UAMSG_CD\n")
            return
    
        if ua_message == UAMSG_SCORE:
            # spammy
            print("UAMSG_SCORE\n")
            return

    print("Unknown command!\n")


# Server code
fake_server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
fcntl.fcntl(fake_server_sock, fcntl.F_SETFL, os.O_NONBLOCK)
fake_server_sock.bind(("127.0.0.1", 61234))
while True:
    try:
        # Receive data from clients
        data, cli_address = fake_server_sock.recvfrom(1500)

        # TODO Inspect data from client

        if cli_address not in client_sockets:
            # Got a new client to keep track of
            print("New client {}".format(cli_address))
            client_sockets[cli_address] = new_client_socket()

        if inspect("CLI {} Message".format(cli_address), cli_address, data) != -1:
            # Send the data upstream
            client_sockets[cli_address].sendto(data, (upstream_server_ip, upstream_server_port))
    except socket.error as e:
        pass

    for cli_address in client_sockets.keys():
        try:
            # Check for data from upstream server
            data, _ = client_sockets[cli_address].recvfrom(1500)

            if inspect("SRV Message for CLI {}".format(cli_address), cli_address, data, from_server=True) == -1:
                continue

            # Send data to correct client
            fake_server_sock.sendto(data, cli_address)
        except socket.error as e:
            continue
