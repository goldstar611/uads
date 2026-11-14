import binascii
import fcntl
import os
import socket

from net_classes import *
from net_messages import *

# Client code
upstream_server_ip = "127.0.0.1"
upstream_server_port = 61235
client_sockets = {}


def new_client_socket():
    new_client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.fcntl(new_client_sock, fcntl.F_SETFL, os.O_NONBLOCK)
    return new_client_sock


def inspect(prefix, cli_address, data, from_server=False):
    # Decode the whole walk (the engine concatenates UA messages in one
    # USR_MSG_DATA payload) and print one compact line per datagram.
    try:
        msgs = split_usr_data(data)
        if not msgs:
            msgs = [data_to_class(data)]
    except Exception:
        msgs = []
        print(f"{prefix}: UNDECODABLE {binascii.hexlify(data).decode()}")
        return

    parts = []
    for m in msgs:
        if isinstance(m, NetSysRetry):
            parts.append(f"RETRY(seq={m.sequence_id} from={m.from_off} upto={m.up_to})")
        elif isinstance(m, NetSysDelivered):
            parts.append(f"DELIVERED(seq={m.sequence_id})")
        elif isinstance(m, NetSysPing):
            parts.append(f"PING(seq={m.sequence_id})")
        elif getattr(m, "message_id", None) is not None:
            cast = getattr(m, "packet_cast", None)
            dst = getattr(m, "packet_to", None)
            parts.append(f"{type(m).__name__}/{m.message_id}"
                         + (f"(cast={cast} to={dst:#x})" if cast is not None else ""))
        else:
            parts.append(type(m).__name__)
    print(f"{prefix}: {' + '.join(parts)}")


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

        if inspect("FROM CLI {}".format(cli_address), cli_address, data) != -1:
            # Send the data upstream
            client_sockets[cli_address].sendto(data, (upstream_server_ip, upstream_server_port))
    except socket.error as e:
        pass

    for cli_address in client_sockets.keys():
        try:
            # Check for data from upstream server
            data, _ = client_sockets[cli_address].recvfrom(1500)

            if inspect("From SRV to CLI {}".format(cli_address), cli_address, data, from_server=True) == -1:
                continue

            # Send data to correct client
            fake_server_sock.sendto(data, cli_address)
        except socket.error as e:
            continue
