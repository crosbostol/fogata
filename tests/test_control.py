import hashlib
import hmac
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from control import (account, initial, month_key, public_status, receive_heartbeat,
                     reconcile, request_start, request_stop, used_hours, verify_heartbeat, verify_password)

LIMITS = {"monthly": 180, "session": 28800, "idle": 900, "boot": 900,
          "heartbeat": 180, "emergency": 300}
NOW = 1794052800


def beat(now, players=0, **kwargs):
    return dict(timestamp=now, bootId="test-boot", players=players, mcReady=True,
                panelReady=True, configured=True, shutdownAck=False, **kwargs)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.state = initial(NOW)

    def running(self):
        code, start = request_start(self.state, NOW, "deallocated", LIMITS)
        self.assertEqual((code, start), (202, True))
        account(self.state, NOW + 60, "running")
        receive_heartbeat(self.state, beat(NOW + 60), NOW + 60)

    def test_visiting_status_never_starts_and_hides_secrets(self):
        result = public_status(self.state, NOW, {"limits": LIMITS, "minecraft": "ip:25565", "panel": "https://panel"})
        self.assertEqual(result["phase"], "off")
        self.assertNotIn("heartbeat", result)
        self.assertIsNone(self.state["startedAt"])

    def test_repeated_click_is_idempotent(self):
        self.running()
        self.assertEqual(request_start(self.state, NOW + 61, "running", LIMITS), (200, False))
        self.assertEqual(self.state["startedAt"], NOW)

    def test_stop_rejects_start(self):
        self.running()
        self.state["phase"] = "stopping"
        self.assertEqual(request_start(self.state, NOW + 61, "running", LIMITS), (409, False))

    def test_manual_stop_waits_for_save_even_with_players(self):
        self.running()
        self.assertEqual(request_stop(self.state, NOW + 90, "running"), 202)
        receive_heartbeat(self.state, beat(NOW + 91, players=3), NOW + 91)
        self.assertEqual(self.state["stopReason"], "manual")
        self.assertIsNone(reconcile(self.state, NOW + 91, "running", LIMITS))
        self.assertEqual(request_stop(self.state, NOW + 100, "running"), 202)
        self.assertEqual(self.state["stopRequestedAt"], NOW + 90)
        packet = beat(NOW + 110)
        packet.update(mcReady=False, shutdownAck=True, shutdownStarted=True)
        receive_heartbeat(self.state, packet, NOW + 110)
        self.assertEqual(reconcile(self.state, NOW + 110, "running", LIMITS), "deallocate")

    def test_manual_stop_off_is_idempotent_and_unknown_is_rejected(self):
        self.assertEqual(request_stop(self.state, NOW, "deallocated"), 200)
        self.assertEqual(self.state["phase"], "off")
        self.assertEqual(request_stop(self.state, NOW + 1, "unknown"), 409)
        self.assertEqual(self.state["phase"], "off")

    def test_manual_stop_boot_failure_has_bounded_emergency(self):
        request_start(self.state, NOW, "deallocated", LIMITS)
        request_stop(self.state, NOW + 10, "starting")
        self.assertIsNone(reconcile(self.state, NOW + 309, "running", LIMITS))
        self.assertEqual(reconcile(self.state, NOW + 310, "running", LIMITS), "deallocate")

    def test_idle_ignores_polls_and_requires_graceful_ack(self):
        self.running()
        for seconds in [300, 600, 900, 961]:
            account(self.state, NOW + seconds, "running")
            receive_heartbeat(self.state, beat(NOW + seconds), NOW + seconds)
            action = reconcile(self.state, NOW + seconds, "running", LIMITS)
        self.assertIsNone(action)
        self.assertEqual(self.state["phase"], "stopping")
        packet = beat(NOW + 990)
        packet.update(mcReady=False, shutdownAck=True)
        receive_heartbeat(self.state, packet, NOW + 990)
        self.assertEqual(reconcile(self.state, NOW + 990, "running", LIMITS), "deallocate")

    def test_player_joining_at_idle_boundary_prevents_stop(self):
        self.running()
        account(self.state, NOW + 961, "running")
        receive_heartbeat(self.state, beat(NOW + 961, players=1), NOW + 961)
        self.assertIsNone(reconcile(self.state, NOW + 961, "running", LIMITS))
        self.assertEqual(self.state["phase"], "ready")
        self.assertIsNone(self.state["idleSince"])

    def test_players_do_not_prevent_monthly_cap(self):
        self.running()
        self.state["usage"][month_key(NOW)] = 180 * 3600
        account(self.state, NOW + 90, "running")
        receive_heartbeat(self.state, beat(NOW + 90, players=5), NOW + 90)
        reconcile(self.state, NOW + 90, "running", LIMITS)
        self.assertEqual(self.state["phase"], "stopping")

    def test_join_after_timer_idle_decision_cancels_unstarted_shutdown(self):
        self.running()
        self.state["heartbeatReceivedAt"] = NOW + 960
        reconcile(self.state, NOW + 961, "running", LIMITS)
        self.assertEqual(self.state["stopReason"], "idle")
        receive_heartbeat(self.state, beat(NOW + 962, players=1), NOW + 962)
        self.assertEqual(self.state["phase"], "ready")
        self.assertIsNone(self.state["stopRequestedAt"])

    def test_join_does_not_cancel_committed_or_budget_shutdown(self):
        self.running()
        self.state.update(phase="stopping", stopReason="budget", stopRequestedAt=NOW + 90)
        receive_heartbeat(self.state, beat(NOW + 91, players=1), NOW + 91)
        self.assertEqual(self.state["phase"], "stopping")
        self.state["stopReason"] = "idle"
        packet = beat(NOW + 92, players=1)
        packet["shutdownStarted"] = True
        receive_heartbeat(self.state, packet, NOW + 92)
        self.assertEqual(self.state["phase"], "stopping")

    def test_month_boundary_splits_accounting(self):
        before = datetime(2026, 11, 30, 23, 59, tzinfo=timezone.utc).timestamp()
        state = initial(before)
        state["lastPower"] = "running"
        account(state, before + 120, "running")
        self.assertEqual(state["usage"], {"2026-11": 60, "2026-12": 60})

    def test_stopped_allocated_is_charged(self):
        account(self.state, NOW + 60, "stopped")
        self.assertEqual(used_hours(self.state, NOW), 1 / 60)
        self.assertEqual(request_start(self.state, NOW + 60, "stopped", LIMITS), (202, True))

    def test_deallocated_time_not_charged(self):
        account(self.state, NOW + 9999, "deallocated")
        self.assertEqual(used_hours(self.state, NOW), 0)

    def test_stale_ready_is_hidden(self):
        self.running()
        result = public_status(self.state, NOW + 300, {"limits": LIMITS, "minecraft": "ip", "panel": "https://panel"})
        self.assertNotEqual(result["phase"], "ready")

    def test_failed_boot_stops_then_emergency_deallocates(self):
        request_start(self.state, NOW, "deallocated", LIMITS)
        self.assertIsNone(reconcile(self.state, NOW + 901, "running", LIMITS))
        self.assertEqual(self.state["phase"], "stopping")
        self.assertIsNone(reconcile(self.state, NOW + 1199, "running", LIMITS))
        self.assertEqual(reconcile(self.state, NOW + 1201, "running", LIMITS), "deallocate")

    def test_maximum_session_even_with_players(self):
        self.running()
        receive_heartbeat(self.state, beat(NOW + 28801, players=3), NOW + 28801)
        reconcile(self.state, NOW + 28801, "running", LIMITS)
        self.assertEqual(self.state["phase"], "stopping")

    def test_new_month_unblocks_start(self):
        self.state["usage"]["2026-10"] = 999999
        self.state["phase"] = "blocked"
        self.assertEqual(request_start(self.state, NOW, "deallocated", LIMITS), (202, True))

    def test_late_heartbeat_does_not_resurrect_off(self):
        receive_heartbeat(self.state, beat(NOW), NOW)
        self.assertEqual(self.state["phase"], "off")

    def test_replay_and_invalid_packet_rejected(self):
        self.running()
        with self.assertRaises(ValueError):
            receive_heartbeat(self.state, beat(NOW + 60), NOW + 61)
        with self.assertRaises(ValueError):
            receive_heartbeat(self.state, beat(NOW + 400, players=-1), NOW + 400)
        with self.assertRaises(ValueError):
            receive_heartbeat(self.state, beat(NOW + 400), NOW + 800)

    def test_no_start_over_budget(self):
        self.state["usage"][month_key(NOW)] = 180 * 3600
        self.assertEqual(request_start(self.state, NOW, "deallocated", LIMITS), (429, False))

    def test_shared_password_and_signed_body(self):
        digest = hashlib.sha256(b"a-strong-test-password").hexdigest()
        self.assertTrue(verify_password("a-strong-test-password", digest))
        self.assertFalse(verify_password("wrong", digest))
        self.assertFalse(verify_password("", ""))
        body = b'{"players":0}'
        signature = hmac.new(b"heartbeat-secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_heartbeat(body, signature, "heartbeat-secret"))
        self.assertFalse(verify_heartbeat(body + b" ", signature, "heartbeat-secret"))


if __name__ == "__main__":
    unittest.main()
