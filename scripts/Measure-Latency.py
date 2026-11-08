#!/usr/bin/env python3
"""Measure Minecraft Java status ping from a player's network. Does not log in.

Use existing, authorized servers; this script never provisions cloud resources.
"""
import argparse
import json
import socket
import statistics
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vm"))
from agent import exact, read_varint, varint


def probe(host, port):
    address = host.encode()
    hello = b"\x00" + varint(0xffffffff) + varint(len(address)) + address + struct.pack(">H", port) + b"\x01"
    with socket.create_connection((host, port), timeout=4) as connection:
        connection.sendall(varint(len(hello)) + hello + b"\x01\x00")
        # Complete the status exchange before timing a protocol ping/pong.
        exact(connection, read_varint(connection))
        ping = b"\x01" + struct.pack(">q", time.time_ns() // 1000000)
        start = time.perf_counter()
        connection.sendall(varint(len(ping)) + ping)
        pong = exact(connection, read_varint(connection))
        elapsed = (time.perf_counter() - start) * 1000
        if pong != ping:
            raise ValueError("Respuesta pong inválida")
    return elapsed


def main():
    parser = argparse.ArgumentParser(description="Ping de Minecraft Java sin iniciar sesión")
    parser.add_argument("servers", nargs="+", help="Servidores autorizados, HOST:PUERTO")
    parser.add_argument("--samples", type=int, default=5, choices=range(1, 11), metavar="1-10")
    args = parser.parse_args()
    failed = False
    for endpoint in args.servers:
        try:
            host, port_text = endpoint.rsplit(":", 1)
            host, port = host.strip("[]"), int(port_text)
            if not host or not 1 <= port <= 65535:
                raise ValueError("Usa HOST:PUERTO")
            times = [probe(host, port) for _ in range(args.samples)]
            print(json.dumps({"server": endpoint, "samples": len(times),
                              "medianMs": round(statistics.median(times), 1),
                              "minMs": round(min(times), 1), "maxMs": round(max(times), 1)}))
        except (OSError, ValueError, EOFError) as error:
            failed = True
            print(json.dumps({"server": endpoint, "error": type(error).__name__}))
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
