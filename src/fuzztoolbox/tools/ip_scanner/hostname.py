import socket
import struct
from typing import List, Optional, Tuple


def reverse_dns(ip: str) -> Optional[str]:
    """Resolve a PTR name through the operating system's configured resolver."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, socket.herror, socket.gaierror):
        return None


def multicast_dns(ip: str, source_ip: Optional[str], timeout: float = 0.8) -> Optional[str]:
    """Request the reverse PTR record directly over multicast DNS."""
    reverse_name = ".".join(reversed(ip.split("."))) + ".in-addr.arpa"
    query = _dns_query(reverse_name, transaction_id=0, unicast_response=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.settimeout(timeout)
        if source_ip:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(source_ip))
        sock.sendto(query, ("224.0.0.251", 5353))
        while True:
            packet, _ = sock.recvfrom(9000)
            hostname = parse_dns_ptr(packet, reverse_name)
            if hostname:
                return hostname
    except (OSError, socket.timeout):
        return None
    finally:
        sock.close()


def netbios_name(ip: str, source_ip: Optional[str], timeout: float = 0.8) -> Optional[str]:
    """Request a Windows machine's registered unique name with NBSTAT."""
    transaction_id = int.from_bytes(socket.inet_aton(ip)[-2:], "big") ^ 0xA51C
    query = build_nbstat_query(transaction_id)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        if source_ip:
            sock.bind((source_ip, 0))
        sock.sendto(query, (ip, 137))
        packet, _ = sock.recvfrom(4096)
        return parse_nbstat_response(packet, transaction_id)
    except (OSError, socket.timeout):
        return None
    finally:
        sock.close()


def _encode_dns_name(name: str) -> bytes:
    labels = (bytes([len(label)]) + label.encode("ascii") for label in name.split("."))
    return b"".join(labels) + b"\0"


def _dns_query(name: str, transaction_id: int, unicast_response: bool = False) -> bytes:
    query_class = 0x8001 if unicast_response else 1
    header = struct.pack("!HHHHHH", transaction_id, 0, 1, 0, 0, 0)
    return header + _encode_dns_name(name) + struct.pack("!HH", 12, query_class)


def _read_dns_name(packet: bytes, offset: int) -> Tuple[str, int]:
    labels: List[str] = []
    next_offset = offset
    jumped = False
    visited = set()
    while True:
        if offset >= len(packet) or offset in visited:
            raise ValueError("invalid compressed DNS name")
        visited.add(offset)
        length = packet[offset]
        if length == 0:
            if not jumped:
                next_offset = offset + 1
            break
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise ValueError("truncated DNS pointer")
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            if not jumped:
                next_offset = offset + 2
                jumped = True
            offset = pointer
            continue
        if length & 0xC0 or offset + 1 + length > len(packet):
            raise ValueError("invalid DNS label")
        labels.append(packet[offset + 1 : offset + 1 + length].decode("utf-8"))
        offset += 1 + length
        if not jumped:
            next_offset = offset
    return ".".join(labels), next_offset


def parse_dns_ptr(packet: bytes, expected_name: str) -> Optional[str]:
    try:
        if len(packet) < 12:
            return None
        header = struct.unpack_from("!HHHHHH", packet)
        _, flags, questions, answers, authorities, additionals = header
        if not flags & 0x8000:
            return None
        offset = 12
        for _ in range(questions):
            _, offset = _read_dns_name(packet, offset)
            offset += 4
        for _ in range(answers + authorities + additionals):
            owner, offset = _read_dns_name(packet, offset)
            record_type, _, _, data_length = struct.unpack_from("!HHIH", packet, offset)
            offset += 10
            data_offset = offset
            offset += data_length
            if offset > len(packet):
                return None
            if record_type == 12 and owner.casefold() == expected_name.casefold():
                value, _ = _read_dns_name(packet, data_offset)
                return value.rstrip(".") or None
    except (UnicodeDecodeError, ValueError, struct.error):
        return None
    return None


def build_nbstat_query(transaction_id: int) -> bytes:
    wildcard = b"*" + (b"\0" * 15)
    encoded = bytes(65 + nibble for byte in wildcard for nibble in (byte >> 4, byte & 0x0F))
    name = bytes([len(encoded)]) + encoded + b"\0"
    header = struct.pack("!HHHHHH", transaction_id, 0, 1, 0, 0, 0)
    return header + name + struct.pack("!HH", 0x21, 1)


def parse_nbstat_response(packet: bytes, transaction_id: int) -> Optional[str]:
    try:
        if len(packet) < 12:
            return None
        response_id, flags, questions, answers, _, _ = struct.unpack_from("!HHHHHH", packet)
        if response_id != transaction_id or not flags & 0x8000:
            return None
        offset = 12
        for _ in range(questions):
            _, offset = _read_dns_name(packet, offset)
            offset += 4
        for _ in range(answers):
            _, offset = _read_dns_name(packet, offset)
            record_type, _, _, data_length = struct.unpack_from("!HHIH", packet, offset)
            offset += 10
            data = packet[offset : offset + data_length]
            offset += data_length
            if record_type != 0x21 or not data:
                continue
            count = data[0]
            for index in range(count):
                entry = data[1 + index * 18 : 1 + (index + 1) * 18]
                if len(entry) != 18:
                    break
                suffix = entry[15]
                name_flags = struct.unpack_from("!H", entry, 16)[0]
                if suffix == 0x00 and not name_flags & 0x8000:
                    return entry[:15].decode("cp437", errors="replace").rstrip() or None
    except (UnicodeDecodeError, ValueError, struct.error):
        return None
    return None
