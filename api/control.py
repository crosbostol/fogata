"""Pure lifecycle policy. No credentials, network or Azure SDK imports here."""
import hashlib
import hmac
from datetime import datetime, timezone

BILLABLE = {"starting", "running", "stopping", "stopped", "unknown"}


def initial(now):
    return {"version": 1, "phase": "off", "usage": {}, "lastAccountAt": now,
            "lastPower": "deallocated", "startedAt": None, "heartbeat": None,
            "idleSince": None, "stopRequestedAt": None, "deallocatePending": False,
            "lastStartRequestAt": 0, "stopReason": None, "message": "Servidor apagado."}


def month_key(now):
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m")


def account(state, now, power):
    """Conservatively charge the observed interval, split at UTC month boundaries."""
    cursor = min(state.get("lastAccountAt", now), now)
    if state.get("lastPower") in BILLABLE or power in BILLABLE:
        while cursor < now:
            date = datetime.fromtimestamp(cursor, timezone.utc)
            next_month = datetime(date.year + (date.month == 12), date.month % 12 + 1, 1,
                                  tzinfo=timezone.utc).timestamp()
            end = min(now, next_month)
            key = month_key(cursor)
            state["usage"][key] = state["usage"].get(key, 0) + end - cursor
            cursor = end
    state["lastAccountAt"], state["lastPower"] = now, power


def used_hours(state, now):
    return state["usage"].get(month_key(now), 0) / 3600


def verify_password(password, expected_hash):
    return bool(password and len(expected_hash) == 64 and hmac.compare_digest(
        hashlib.sha256(password.encode()).hexdigest(), expected_hash.lower()))


def verify_heartbeat(body, signature, secret):
    return bool(secret and signature and hmac.compare_digest(
        hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), signature))


def request_start(state, now, power, limits):
    """Return (HTTP status, should_start). Caller holds distributed state lease."""
    account(state, now, power)
    if state["phase"] == "stopping" or power == "deallocating":
        state["message"] = "Guardando el mundo. Espera a que termine el apagado."
        return 409, False
    if used_hours(state, now) >= limits["monthly"]:
        state["message"] = "Se alcanzó el límite mensual de horas."
        if power == "deallocated":
            state["phase"] = "blocked"
        return 429, False
    if power != "deallocated":
        # An allocated-but-powered-off VM still costs money. Repair it via start.
        if power == "stopped":
            state.update(phase="starting", startedAt=now, heartbeat=None, idleSince=None)
            return 202, True
        if power in {"running", "starting"}:
            if state["phase"] in {"off", "blocked", "error"}:
                state.update(phase="booting", startedAt=now, heartbeat=None)
            return 200, False
        return 409, False
    if now - state.get("lastStartRequestAt", 0) < 60:
        return 429, False
    state.update(phase="starting", startedAt=now, heartbeat=None, idleSince=None,
                 stopRequestedAt=None, stopReason=None, deallocatePending=False, lastStartRequestAt=now,
                 message="Azure está iniciando la máquina.")
    return 202, True


def start_selected(state, now, power, limits, selected, catalog):
    if not isinstance(selected, str) or selected not in {item['id'] for item in catalog}:
        return 400, False
    current = state.get('selectedServer', 'paper')
    if power != 'deallocated' and selected != current:
        return 409, False
    code, start = request_start(state, now, power, limits)
    if code < 300:
        state['selectedServer'] = selected
    return code, start


def request_stop(state, now, power):
    """Request the existing graceful shutdown protocol; never cut VM power here."""
    account(state, now, power)
    if power == "deallocated":
        state.update(phase="off", startedAt=None, heartbeat=None, idleSince=None,
                     stopRequestedAt=None, stopReason=None, deallocatePending=False,
                     message="Servidor apagado.")
        return 200
    if power == "deallocating":
        state.update(phase="stopping", message="Azure está liberando la máquina.")
        return 202
    if state["phase"] == "stopping":
        if state.get("stopReason") == "idle":
            state["stopReason"] = "manual"
        return 202  # Repeated requests must not extend the emergency deadline.
    if power not in {"running", "starting", "stopped"}:
        return 409
    state.update(phase="stopping", stopRequestedAt=now, stopReason="manual",
                 message="Apagado solicitado: guardando el mundo antes de liberar la máquina.")
    return 202


def receive_heartbeat(state, payload, now):
    timestamp = payload.get("timestamp")
    players = payload.get("players")
    if not isinstance(timestamp, (int, float)) or abs(now - timestamp) > 120:
        raise ValueError("Heartbeat fuera de plazo")
    if not isinstance(players, int) or isinstance(players, bool) or not 0 <= players <= 10000:
        raise ValueError("Número de jugadores inválido")
    if not isinstance(payload.get("bootId"), str) or not 1 <= len(payload["bootId"]) <= 80:
        raise ValueError("bootId inválido")
    for key in ["mcReady", "panelReady", "configured", "shutdownAck"]:
        if not isinstance(payload.get(key), bool):
            raise ValueError("Estado inválido")
    if not isinstance(payload.get("shutdownStarted", False), bool):
        raise ValueError("Estado de cierre inválido")
    previous = state.get("heartbeat")
    if previous and timestamp <= previous["timestamp"]:
        raise ValueError("Heartbeat repetido")
    if state.get("startedAt") and timestamp < state["startedAt"] - 5:
        raise ValueError("Heartbeat anterior al arranque")
    if state["lastPower"] in {"deallocated", "deallocating"}:
        # Don't let a late packet resurrect the visible state.
        return
    closing_started = (previous or {}).get("shutdownStarted", False)
    state["heartbeat"] = payload
    state["heartbeatReceivedAt"] = now
    if state["phase"] == "stopping":
        if (state.get("stopReason") == "idle" and players > 0 and payload["mcReady"]
                and not closing_started and not payload.get("shutdownStarted", False)):
            state.update(phase="ready", stopRequestedAt=None, stopReason=None,
                         message="Entró un jugador; apagado por inactividad cancelado.")
        else:
            return
    if payload.get('serverId', 'paper') != state.get('selectedServer', 'paper'):
        payload = dict(payload, mcReady=False)
        state['heartbeat'] = payload
    if payload["configured"] and payload["mcReady"] and payload["panelReady"]:
        state["phase"] = "ready"
        state["message"] = "Minecraft y Pelican están listos."
    else:
        state["phase"] = "loading"
        state["message"] = ("Cargando Minecraft y el panel." if payload["configured"] else
                            "Falta completar la configuración de Pelican en la VM.")
    if players > 0 or not payload["mcReady"]:
        state["idleSince"] = None
    elif state.get("idleSince") is None:
        state["idleSince"] = now


def reconcile(state, now, power, limits):
    """Called each minute. Return deallocate only after graceful acknowledgement,
    or on a bounded emergency timeout when the agent cannot complete shutdown.
    """
    account(state, now, power)
    if power == "deallocated":
        state.update(phase="blocked" if used_hours(state, now) >= limits["monthly"] else "off",
                     startedAt=None, stopRequestedAt=None, stopReason=None, deallocatePending=False,
                     heartbeat=None, idleSince=None, message="Servidor apagado.")
        return None
    if power == "deallocating":
        state.update(phase="stopping", message="Azure está liberando la máquina.")
        return None
    if state.get("startedAt") is None:
        state["startedAt"] = now  # Also supervise manual starts outside the portal.
    heartbeat = state.get("heartbeat")
    fresh = heartbeat and now - state.get("heartbeatReceivedAt", 0) <= limits["heartbeat"]
    if state["phase"] == "stopping":
        if fresh and heartbeat.get("shutdownAck"):
            return "deallocate"
        if now - state.get("stopRequestedAt", now) >= limits["emergency"]:
            state["message"] = "Apagado de emergencia: agente sin confirmación; revisar backups."
            return "deallocate"
        return None
    reason, reason_code = None, None
    if used_hours(state, now) >= limits["monthly"]:
        reason = "Límite mensual de horas alcanzado."
        reason_code = "budget"
    elif now - state["startedAt"] >= limits["session"]:
        reason = "Duración máxima de sesión alcanzada."
        reason_code = "session"
    elif not fresh and now - state["startedAt"] >= limits["boot"]:
        reason = "La VM no informa estado; se apagará para contener el gasto."
        reason_code = "unhealthy"
    elif fresh and not (heartbeat["mcReady"] and heartbeat["configured"]) and now - state["startedAt"] >= limits["boot"]:
        reason = "Minecraft no inició dentro del plazo."
        reason_code = "unhealthy"
    elif fresh and state.get("idleSince") is not None and now - state["idleSince"] >= limits["idle"]:
        reason = "Sin jugadores: guardando el mundo antes de apagar."
        reason_code = "idle"
    if reason:
        state.update(phase="stopping", stopRequestedAt=now, stopReason=reason_code, message=reason)
        return None
    if not fresh:
        state["phase"] = "starting" if power == "starting" else "booting"
        state["message"] = "Esperando confirmación de la máquina."
    return None


def public_status(state, now, config):
    heartbeat = state.get("heartbeat") or {}
    fresh = now - state.get("heartbeatReceivedAt", 0) <= config["limits"]["heartbeat"]
    phase = state["phase"]
    if phase == "ready" and not fresh:
        phase = "booting"
    catalog = config.get('servers', [{'id': 'paper', 'name': 'Mundo habitual', 'address': config['minecraft']}])
    selected = state.get('selectedServer', 'paper')
    chosen = next((item for item in catalog if item['id'] == selected), catalog[0])
    return {"selectedServer": selected, "servers": catalog, "phase": phase, "players": heartbeat.get("players", 0) if fresh else 0,
            "usedHours": round(used_hours(state, now), 3),
            "maxHours": config["limits"]["monthly"],
            "minecraftAddress": chosen["address"], "panelUrl": config["panel"],
            "message": state["message"], "updatedAt": state.get("lastAccountAt", now)}
