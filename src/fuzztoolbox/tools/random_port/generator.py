"""Generate random non-privileged TCP/UDP port numbers."""
from __future__ import annotations

import secrets

MIN_PORT = 1024
MAX_PORT = 65535
PORT_COUNT = MAX_PORT - MIN_PORT + 1


def generate_random_port(previous: int | None = None) -> int:
    """Return a random port in 1024..65535, avoiding the prior value when possible."""
    while True:
        port = MIN_PORT + secrets.randbelow(PORT_COUNT)
        if port != previous:
            return port
