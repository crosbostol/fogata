"""Azure Functions adapters. Shared password is checked on every portal call."""
import json
import logging
import os
import time
import urllib.request
from contextlib import contextmanager

import azure.functions as func
from azure.core.exceptions import ResourceExistsError, HttpResponseError
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient

from control import (account, initial, public_status, receive_heartbeat, reconcile,
                     request_start, request_stop, verify_heartbeat, verify_password)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def config():
    return {"minecraft": os.environ["MINECRAFT_ADDRESS"],
            "panel": os.environ["PANEL_URL"], "limits": {
                "monthly": float(os.getenv("MAX_MONTHLY_HOURS", "180")),
                "session": float(os.getenv("MAX_SESSION_HOURS", "8")) * 3600,
                "idle": float(os.getenv("IDLE_MINUTES", "15")) * 60,
                "boot": float(os.getenv("BOOT_TIMEOUT_MINUTES", "15")) * 60,
                "heartbeat": float(os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "180")),
                "emergency": float(os.getenv("EMERGENCY_STOP_SECONDS", "300"))}}


def response(body, status=200):
    return func.HttpResponse(json.dumps(body, ensure_ascii=False), status_code=status,
                             mimetype="application/json", headers={"Cache-Control": "no-store",
                             "X-Content-Type-Options": "nosniff"})


def authorized(req):
    return verify_password(req.headers.get("X-Portal-Password", ""),
                           os.getenv("PORTAL_PASSWORD_SHA256", ""))


@contextmanager
def state_transaction():
    service = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
    container = service.get_container_client(os.getenv("STATE_CONTAINER", "control"))
    try:
        container.create_container()
    except ResourceExistsError:
        pass
    blob = container.get_blob_client(os.getenv("STATE_BLOB", "state.json"))
    try:
        blob.upload_blob(json.dumps(initial(time.time())), overwrite=False)
    except ResourceExistsError:
        pass
    lease = blob.acquire_lease(lease_duration=60)
    try:
        state = json.loads(blob.download_blob(lease=lease).readall())
        yield state
        blob.upload_blob(json.dumps(state), overwrite=True, lease=lease)
    finally:
        lease.release()
        service.close()


def arm(method="GET", action="instanceView"):
    sub, group, vm = (os.environ[k] for k in ["SUBSCRIPTION_ID", "VM_RESOURCE_GROUP", "VM_NAME"])
    url = (f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{group}"
           f"/providers/Microsoft.Compute/virtualMachines/{vm}/{action}?api-version=2024-07-01")
    with ManagedIdentityCredential() as credential:
        token = credential.get_token("https://management.azure.com/.default").token
    req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None,
                                 headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=15) as reply:
        raw = reply.read()
        return json.loads(raw) if raw else {}


def power_state():
    statuses = arm().get("statuses", [])
    return next((s["code"].split("/", 1)[1] for s in statuses
                 if s.get("code", "").startswith("PowerState/")), "unknown")


def perform_tick(state, now, cfg, power):
    action = reconcile(state, now, power, cfg["limits"])
    if action == "deallocate":
        # Deallocate is idempotent. Retry on future ticks if ARM didn't accept.
        arm("POST", "deallocate")
        state["deallocatePending"] = True


@app.route(route="status", methods=["GET"])
def status(req: func.HttpRequest):
    if not authorized(req):
        return response({"message": "Contraseña incorrecta."}, 401)
    try:
        now, cfg = time.time(), config()
        # Timer handles reconciliation. Frequent UI polling never changes idle time.
        with state_transaction() as state:
            result = public_status(state, now, cfg)
        return response(result)
    except HttpResponseError:
        return response({"message": "Control ocupado. Reintenta en unos segundos."}, 503)
    except Exception:
        logging.exception("Status failed")
        return response({"message": "No se pudo consultar el estado."}, 503)


@app.route(route="start", methods=["POST"])
def start(req: func.HttpRequest):
    if not authorized(req):
        return response({"message": "Contraseña incorrecta."}, 401)
    try:
        now, cfg = time.time(), config()
        with state_transaction() as state:
            power = power_state()
            code, should_start = request_start(state, now, power, cfg["limits"])
            if should_start:
                try:
                    arm("POST", "start")
                except Exception:
                    # Commit the uncertainty; next timer recovers actual ARM state.
                    state.update(phase="error", message="Azure no confirmó el arranque. Consulta el estado antes de reintentar.")
                    code = 503
            result = public_status(state, now, cfg)
        return response(result, code)
    except HttpResponseError:
        return response({"message": "Ya hay otra operación. Reintenta en unos segundos."}, 409)
    except Exception:
        logging.exception("Start failed")
        return response({"message": "No se pudo solicitar el encendido."}, 503)


@app.route(route="stop", methods=["POST"])
def stop(req: func.HttpRequest):
    if not authorized(req):
        return response({"message": "Contraseña incorrecta."}, 401)
    try:
        now, cfg = time.time(), config()
        with state_transaction() as state:
            code = request_stop(state, now, power_state())
            result = public_status(state, now, cfg)
            if code == 409:
                result["message"] = "Azure aún no confirma el estado. Consulta de nuevo antes de apagar."
        return response(result, code)
    except HttpResponseError:
        return response({"message": "Control ocupado. Reintenta en unos segundos."}, 409)
    except Exception:
        logging.exception("Stop failed")
        return response({"message": "No se pudo confirmar el apagado. Consulta el estado."}, 503)


@app.route(route="heartbeat", methods=["POST"])
def heartbeat(req: func.HttpRequest):
    raw = req.get_body()
    if len(raw) > 4096 or not verify_heartbeat(raw, req.headers.get("X-Fogata-Signature", ""),
                                              os.getenv("HEARTBEAT_SECRET", "")):
        return response({"message": "Firma inválida."}, 401)
    try:
        payload, now, cfg = json.loads(raw), time.time(), config()
        if not isinstance(payload, dict):
            raise ValueError("Objeto esperado")
        with state_transaction() as state:
            # Refresh ARM here: heartbeats can arrive before the first timer tick.
            power = power_state()
            account(state, now, power)
            receive_heartbeat(state, payload, now)
            # A joining player resets idle before evaluating shutdown on this heartbeat.
            perform_tick(state, now, cfg, power)
            result = {"action": "stop" if state["phase"] == "stopping" else "none",
                      "reason": state["message"], "reasonCode": state.get("stopReason")}
        return response(result)
    except (ValueError, TypeError, json.JSONDecodeError):
        return response({"message": "Heartbeat inválido o repetido."}, 400)
    except Exception:
        logging.exception("Heartbeat failed")
        return response({"message": "Reintentar heartbeat."}, 503)


@app.timer_trigger(schedule="0 * * * * *", arg_name="timer", run_on_startup=False,
                   use_monitor=True)
def watchdog(timer: func.TimerRequest):
    with state_transaction() as state:
        perform_tick(state, time.time(), config(), power_state())
