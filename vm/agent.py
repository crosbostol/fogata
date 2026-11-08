#!/usr/bin/env python3
"""Root-owned VM heartbeat agent; no public listener.

Container must be the existing Pelican server UUID, configured by the operator.
Wings starts/stops the server, respecting its intentional-stop/crash state.
"""
import hashlib
import hmac
import json
import logging
import os
import socket
import struct
import subprocess
import time
import urllib.request
from pathlib import Path
from wings import request_power

ENV_PATH = Path("/etc/fogata/agent.env")


def environment(path=ENV_PATH):
    result = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip("\"'")
    return result


def varint(value):
    data = bytearray()
    while True:
        byte = value & 127
        value >>= 7
        data.append(byte | (128 if value else 0))
        if not value:
            return bytes(data)


def exact(sock, length):
    if length > 1024 * 1024:
        raise ValueError("Packet too large")
    data = bytearray()
    while len(data) < length:
        part = sock.recv(length - len(data))
        if not part:
            raise EOFError("Server closed socket")
        data.extend(part)
    return bytes(data)


def read_varint(sock):
    value = 0
    for index in range(5):
        byte = exact(sock, 1)[0]
        value |= (byte & 127) << (7 * index)
        if not byte & 128:
            return value
    raise ValueError("Invalid VarInt")


def minecraft_status(host, port):
    address = host.encode()
    # Protocol -1 (0xffffffff) requests status regardless of selected game version.
    handshake = b"\x00" + varint(0xffffffff) + varint(len(address)) + address + struct.pack(">H", port) + b"\x01"
    with socket.create_connection((host, port), timeout=4) as sock:
        sock.sendall(varint(len(handshake)) + handshake + b"\x01\x00")
        packet_length = read_varint(sock)
        packet = exact(sock, packet_length)
    # Parse status payload from a bounded byte stream, never arbitrary server code.
    import io
    class Buffer:
        def __init__(self, data):
            self.buffer = io.BytesIO(data)
        def recv(self, count):
            return self.buffer.read(count)
    buffer = Buffer(packet)
    if read_varint(buffer) != 0:
        raise ValueError("Unexpected packet")
    status = json.loads(exact(buffer, read_varint(buffer)))
    players = status["players"]["online"]
    if not isinstance(players, int) or not 0 <= players <= 10000:
        raise ValueError("Invalid player count")
    return players


def docker(*args, timeout=15):
    return subprocess.run(["docker", *args], check=True, capture_output=True,
                          text=True, timeout=timeout).stdout.strip()


def container_status(container):
    return json.loads(docker("inspect", "--format", "{{json .State}}", container))


def panel_ready(url):
    try:
        with urllib.request.urlopen(url, timeout=4) as reply:
            return reply.status == 200 and "/installer" not in reply.url
    except Exception:
        return False


def heartbeat(config, payload):
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(config["HEARTBEAT_SECRET"].encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(config["API_BASE_URL"].rstrip("/") + "/api/heartbeat",
                                 data=body, headers={"Content-Type": "application/json",
                                 "X-Fogata-Signature": signature}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as reply:
        return json.load(reply)


def server_catalog(config):
    path = Path('/etc/fogata/servers.json')
    if path.exists():
        return json.loads(path.read_text())
    if not config.get('CONTAINER_NAME'):
        return []
    return [{'id': 'paper', 'container': config.get('CONTAINER_NAME', ''),
             'port': int(config.get('MC_PORT', '25565'))}]


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    selected = None
    started = False
    stopping = False
    sent = set()
    while True:
        try:
            config = environment()
            catalog = server_catalog(config)
            states = {item['id']: container_status(item['container']) for item in catalog}
            running = [item for item in catalog if states[item['id']].get('Running')]
            players, ready = 0, False
            for item in running:
                try:
                    count = minecraft_status('127.0.0.1', item['port'])
                    players += count
                    if item['id'] == selected: ready = True
                except (OSError, ValueError, EOFError, KeyError):
                    pass
            payload = dict(timestamp=int(time.time()), bootId=boot_id, players=players,
                           serverId=selected or '', mcReady=ready and len(running) == 1,
                           panelReady=panel_ready(config.get('PANEL_HEALTH_URL', 'http://127.0.0.1/')),
                           configured=bool(catalog), shutdownAck=stopping and not running,
                           shutdownStarted=stopping)
            instruction = heartbeat(config, payload)
            desired = instruction.get('selectedServer', 'paper')
            if desired not in {item['id'] for item in catalog}:
                raise ValueError('Selected server is not registered on this node')
            if instruction.get('action') == 'stop':
                if instruction.get('reasonCode') == 'idle' and players > 0:
                    continue
                if instruction.get('reasonCode') == 'idle':
                    # Recheck after the network round trip before committing a close.
                    if any(minecraft_status('127.0.0.1', item['port']) > 0 for item in running):
                        continue
                stopping = True
            if stopping:
                for item in running:
                    if item['id'] not in sent:
                        request_power(item['container'], 'stop')
                        sent.add(item['id'])
            elif not started:
                selected = desired
                target = next(item for item in catalog if item['id'] == selected)
                if not running:
                    request_power(target['container'], 'start')
                    started = True
                elif any(item['id'] == selected for item in running):
                    started = True
            # Never restart a server deliberately stopped in Pelican in a loop.
        except Exception as error:
            logging.warning('Agent retry: %s', type(error).__name__)
        time.sleep(15 if stopping else 20)


if __name__ == '__main__':
    main()
