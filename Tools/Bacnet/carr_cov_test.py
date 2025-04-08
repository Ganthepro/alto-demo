from bacpypes.pdu import PDU, Address
from bacpypes.bvll import BVLPDU, bvl_pdu_types
from bacpypes.npdu import NPDU
from bacpypes.apdu import APDU, apdu_types, unconfirmed_request_types
from socket import socket, AF_INET, SOCK_DGRAM

try:
    s = socket(AF_INET, SOCK_DGRAM)
    s.bind(("", 0xBAC0))
except:
    print(
        "Could not start COV thread. Is another program listeneing on 0xbac0?"
    )

_broadcat_ip = "192.168.2.255"
daddr = Address((_broadcat_ip, 47808))
while True:
    msg, addr = s.recvfrom(1024)
    try:
        print("Got COV", msg, addr)

        sa = Address(addr)
        pdu = PDU(msg, source=sa, destination=daddr)
        pdu.pduExpectingReply = False
        pdu.pduNetworkPriority = 1
        if pdu.pduData[0] != 0x81:
            raise Exception
        xpdu = BVLPDU()
        xpdu.decode(pdu)
        pdu = xpdu
        atype = bvl_pdu_types.get(pdu.bvlciFunction)
        xpdu = pdu
        bpdu = atype()
        bpdu.decode(pdu)
        pdu = bpdu
        if pdu.pduData[0] != 0x01:
            raise Exception
        npdu = NPDU()
        npdu.decode(pdu)
        assert npdu.npduNetMessage is None
        xpdu = APDU()
        xpdu.decode(npdu)
        apdu = xpdu
        apdu.pduSource = npdu.pduSource
        apdu.pduDestination = npdu.pduDestination
        atype = apdu_types.get(apdu.apduType)
        xpdu = apdu
        apdu = atype()
        apdu.decode(xpdu)
        atype = unconfirmed_request_types.get(apdu.apduService)
        xpdu = apdu
        apdu = atype()
        apdu.decode(xpdu)
        cov = apdu.apdu_contents()
        print(f"COV is {cov}")
    except Exception as e:
        print(f"Problem in COV thread: {e}")
