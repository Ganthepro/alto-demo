# socket_echo_client_dgram.py
import socket
import sys

# Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

server_address = ('104.43.16.81', 7001)

message = b"""
{
    "fb_or_az": 1,
    "gateway_id": "betaevbike001",
    "device_id": "869405031202485",
    "volt": 49.2,
    "current": 0.0,
    "rpm": 20.0,
    "lat": 13.637437402298652,
    "lon": 100.60352319568933,
    "altitude": 0.0
}
"""

try:
    # Send data
    print('sending {!r}'.format(message))
    sent = sock.sendto(message, server_address)

    # Receive response
    print('waiting to receive')
    data, server = sock.recvfrom(4096)
    print('received {!r}'.format(data))

finally:
    print('closing socket')
    sock.close()