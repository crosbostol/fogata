"""Protocol and Wings integration contracts, without opening ports or using Docker."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vm"))
import agent
import wings


class Socket:
    def __init__(self, data):
        self.buffer = io.BytesIO(data)
        self.sent = b""
    def recv(self, length):
        return self.buffer.read(min(length, 3))  # Exercise fragmented TCP reads.
    def sendall(self, data):
        self.sent += data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class VmTests(unittest.TestCase):
    def test_agent_starts_only_selected_container(self):
        catalog = [{'id':'paper','container':'a','port':25565},{'id':'deceasedcraft','container':'b','port':25566}]
        with patch.object(agent, 'environment', return_value={}), patch.object(agent, 'server_catalog', return_value=catalog), patch.object(agent, 'container_status', return_value={'Running':False}), patch.object(agent, 'panel_ready', return_value=True), patch.object(agent, 'heartbeat', return_value={'selectedServer':'deceasedcraft','action':'none'}), patch.object(agent, 'request_power') as power, patch.object(agent.Path, 'read_text', return_value='boot'), patch.object(agent.time, 'sleep', side_effect=StopIteration):
            with self.assertRaises(StopIteration):agent.main()
            power.assert_called_once_with('b','start')

    def test_agent_shutdown_counts_and_closes_every_running_server(self):
        catalog = [{'id':'paper','container':'a','port':25565},{'id':'deceasedcraft','container':'b','port':25566}]
        with patch.object(agent, 'environment', return_value={}), patch.object(agent, 'server_catalog', return_value=catalog), patch.object(agent, 'container_status', return_value={'Running':True}), patch.object(agent, 'minecraft_status', return_value=2), patch.object(agent, 'panel_ready', return_value=True), patch.object(agent, 'heartbeat', return_value={'selectedServer':'paper','action':'stop'}) as hb, patch.object(agent, 'request_power') as power, patch.object(agent.Path, 'read_text', return_value='boot'), patch.object(agent.time, 'sleep', side_effect=StopIteration):
            with self.assertRaises(StopIteration):agent.main()
            self.assertEqual(hb.call_args.args[1]['players'],4)
            self.assertFalse(hb.call_args.args[1]['shutdownAck'])
            self.assertEqual(power.call_count,2)

    def test_status_packet_counts_real_players(self):
        payload = json.dumps({"players": {"online": 4}}).encode()
        packet = b"\x00" + agent.varint(len(payload)) + payload
        sock = Socket(agent.varint(len(packet)) + packet)
        with patch.object(agent.socket, "create_connection", return_value=sock):
            self.assertEqual(agent.minecraft_status("127.0.0.1", 25565), 4)
        self.assertTrue(sock.sent.endswith(b"\x01\x00"))

    def test_bad_packet_size_and_truncated_socket_fail_closed(self):
        with self.assertRaises(ValueError):
            agent.exact(Socket(b""), 1024 * 1024 + 1)
        with self.assertRaises(EOFError):
            agent.exact(Socket(b"a"), 2)
        with self.assertRaises(ValueError):
            agent.read_varint(Socket(b"\x80" * 5))

    def test_varint_round_trip(self):
        for value in [0, 127, 128, 255, 2097151, 0xffffffff]:
            self.assertEqual(agent.read_varint(Socket(agent.varint(value))), value)

    def test_wings_power_uses_only_loopback_and_existing_node_token(self):
        reply = Mock(status=202)
        reply.__enter__ = Mock(return_value=reply)
        reply.__exit__ = Mock(return_value=None)
        opener = Mock()
        opener.open.return_value = reply
        server = "12345678-1234-5678-1234-567812345678"
        with patch.object(wings, "local_token", return_value="test-node-secret"):
            wings.request_power(server, "stop", opener=opener)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, f"http://127.0.0.1:8080/api/servers/{server}/power")
        self.assertEqual(json.loads(request.data), {"action": "stop", "wait_seconds": 0})
        self.assertEqual(request.get_header("Authorization"), "Bearer test-node-secret")

    def test_wings_forbids_kill_and_non_uuid_targets(self):
        for server, action in [("bad", "start"), ("../other", "stop"),
                               ("12345678-1234-5678-1234-567812345678", "kill")]:
            with self.assertRaises(ValueError):
                wings.request_power(server, action)

    def test_wings_acceptance_is_not_shutdown_ack(self):
        reply = Mock(status=200)
        reply.__enter__ = Mock(return_value=reply)
        reply.__exit__ = Mock(return_value=None)
        opener = Mock()
        opener.open.return_value = reply
        with patch.object(wings, "local_token", return_value="test-node-secret"):
            with self.assertRaises(RuntimeError):
                wings.request_power("12345678-1234-5678-1234-567812345678", "stop", opener=opener)
