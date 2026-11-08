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


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    stopping, stop_sent_at, did_start, finished = False, None, False, False
    while True:
        try:
            config = environment()
            container = config.get("CONTAINER_NAME", "")
            configured = bool(container)
            running = False
            inspect_ok = False
            if configured:
                state = container_status(container)
                inspect_ok = True
                running = state.get("Running", False)
                if not stopping and not did_start:
                    if not running:
                        request_power(container, "start")
                        running = True
                    did_start = True
            players, mc_ready = 0, False
            if running and not stopping:
                try:
                    players = minecraft_status(config.get("MC_HOST", "127.0.0.1"),
                                               int(config.get("MC_PORT", "25565")))
                    mc_ready = True
                except (OSError, ValueError, EOFError, KeyError):
                    pass
            # Ack requires a successfully inspected stopped container, or no configured game.
            ack = stopping and (not configured or (inspect_ok and not running))
            payload = {"timestamp": int(time.time()), "bootId": boot_id, "players": players,
                       "mcReady": mc_ready, "panelReady": panel_ready(
                           config.get("PANEL_HEALTH_URL", "http://127.0.0.1/")),
                       "configured": configured, "shutdownAck": ack, "shutdownStarted": stopping}
            instruction = heartbeat(config, payload)
            if instruction.get("action") == "stop" and not stopping:
                if instruction.get("reasonCode") == "idle" and configured and running:
                    # Recheck after the API round trip; player may have just joined.
                    try:
                        if minecraft_status(config.get("MC_HOST", "127.0.0.1"),
                                            int(config.get("MC_PORT", "25565"))) > 0:
                            continue
                    except (OSError, ValueError, EOFError, KeyError):
                        pass
                stopping = True
            if stopping and configured and running and stop_sent_at is None:
                request_power(container, "stop")
                stop_sent_at = time.time()
                logging.info("Graceful Minecraft stop requested through Wings")
            if stopping and stop_sent_at and time.time() - stop_sent_at > 180 and running:
                logging.error("Minecraft still running; no forced container kill. Controller may deallocate after its emergency deadline.")
            if ack and not finished:
                logging.info("Minecraft stopped; waiting for Azure deallocation")
                finished = True
        except Exception as error:
            # Never log config/body/signature or HTTP response body containing credentials.
            logging.warning("Agent retry: %s", type(error).__name__)
        time.sleep(15 if stopping else 30)


if __name__ == "__main__":
    main()
