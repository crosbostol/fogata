"""HTTP adapters with real Functions SDK, fake cloud. No Azure calls made."""
import copy
import hashlib
import hmac
import json
import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
try:
    import azure.functions as func
    import function_app as api
except ImportError:
    api = None

from control import initial


@unittest.skipIf(api is None, "Instala api/requirements.txt para probar adaptadores HTTP")
class HttpTests(unittest.TestCase):
    def setUp(self):
        self.state = initial(10000)
        self.password = "a-long-shared-test-password"
        self.env = patch.dict(os.environ, {
            "MINECRAFT_ADDRESS": "203.0.113.1:25565", "PANEL_URL": "https://example.com",
            "PORTAL_PASSWORD_SHA256": hashlib.sha256(self.password.encode()).hexdigest(),
            "HEARTBEAT_SECRET": "test-heartbeat-secret"})
        self.env.start()
        @contextmanager
        def transaction():
            candidate = copy.deepcopy(self.state)
            yield candidate
            self.state = candidate
        self.store = patch.object(api, "state_transaction", transaction)
        self.store.start()
        self.clock = patch.object(api.time, "time", return_value=10000)
        self.clock.start()
        self.power = patch.object(api, "power_state", return_value="deallocated")
        self.power.start()
        self.arm = patch.object(api, "arm", return_value={})
        self.cloud = self.arm.start()
        self.addCleanup(patch.stopall)

    def request(self, method, route, body=b"", auth=True, headers=None):
        values = {"X-Portal-Password": self.password} if auth else {}
        values.update(headers or {})
        return func.HttpRequest(method=method, url="https://api.test/api/" + route,
                                body=body, headers=values)

    def test_status_auth_and_no_vm_start(self):
        reply = api.status(self.request("GET", "status", auth=False))
        self.assertEqual(reply.status_code, 401)
        reply = api.status(self.request("GET", "status"))
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(json.loads(reply.get_body())["phase"], "off")
        self.cloud.assert_not_called()

    def test_start_is_one_arm_call_and_poll_never_starts(self):
        reply = api.start(self.request("POST", "start"))
        self.assertEqual(reply.status_code, 202)
        self.cloud.assert_called_once_with("POST", "start")
        self.assertEqual(api.start(self.request("POST", "start")).status_code, 429)
        api.status(self.request("GET", "status"))
        self.cloud.assert_called_once()

    def test_uncertain_start_commits_error_and_does_not_claim_ready(self):
        self.cloud.side_effect = TimeoutError()
        reply = api.start(self.request("POST", "start"))
        self.assertEqual(reply.status_code, 503)
        self.assertEqual(self.state["phase"], "error")

    def test_unsigned_heartbeat_does_not_touch_state(self):
        reply = api.heartbeat(self.request("POST", "heartbeat", body=b"{}", auth=False))
        self.assertEqual(reply.status_code, 401)
        self.cloud.assert_not_called()

    def test_signed_heartbeat_reports_ready_after_real_health(self):
        self.power.stop()
        patcher = patch.object(api, "power_state", return_value="running")
        patcher.start()
        self.state.update(phase="booting", startedAt=9990, lastPower="running")
        payload = {"timestamp": 10000, "bootId": "boot-1", "players": 1, "mcReady": True,
                   "panelReady": True, "configured": True, "shutdownAck": False}
        body = json.dumps(payload).encode()
        signature = hmac.new(b"test-heartbeat-secret", body, hashlib.sha256).hexdigest()
        reply = api.heartbeat(self.request("POST", "heartbeat", body, False,
                                           {"X-Fogata-Signature": signature}))
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(self.state["phase"], "ready")
        self.assertEqual(json.loads(reply.get_body())["action"], "none")

    def test_sdk_registers_all_triggers(self):
        self.assertEqual({f.get_function_name() for f in api.app.get_functions()},
                         {"start", "status", "heartbeat", "watchdog"})
