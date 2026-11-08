"""Power requests through local Wings so its intentional-stop state is respected.

Primary contract: pelican/wings router/router_server.go (postServerPower),
router/middleware/middleware.go (RequireAuthorization), config/config.go.
The existing node token stays in root-owned config; never expose it in logs.
An accepted request is not a completed operation. Inspect the container later.
"""
import json
from pathlib import Path
import urllib.error
import urllib.request
import uuid


CONFIG_PATH = Path("/etc/pelican/config.yml")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # An unexpected proxy redirect must not forward the node bearer token.
        return None


def local_token(config_path=CONFIG_PATH):
    import yaml  # Ubuntu package python3-yaml; safe parser, never yaml.load.
    with Path(config_path).open(encoding="utf-8") as source:
        config = yaml.safe_load(source)
    if not isinstance(config, dict):
        raise ValueError("Wings configuration must be a mapping")
    api = config.get("api", {})
    if not isinstance(api, dict):
        raise ValueError("Invalid Wings API configuration")
    host = api.get("host", "0.0.0.0")
    port = api.get("port", 8080)
    ssl = api.get("ssl", {})
    if host not in {"127.0.0.1", "0.0.0.0", "localhost", "::", "::1"}:
        raise ValueError("Configure local Wings API listening before using Fogata")
    if port != 8080 or not isinstance(ssl, dict) or ssl.get("enabled", False):
        raise ValueError("Fogata expects local HTTP Wings on port 8080 behind Caddy")
    token = config.get("token")
    if not isinstance(token, str) or not token or len(token) > 4096 or any(
            char in token for char in "\r\n") or "${" in token:
        raise ValueError("Configure a literal Wings node token in its protected YAML")
    return token


def request_power(server_uuid, action, config_path=CONFIG_PATH, opener=None):
    """Submit start/stop for one UUID. Return only after Wings accepts HTTP 202.

    No direct Docker power mutation, no kill/restart action and no remote URL.
    The caller must verify stopped state before acknowledging graceful shutdown.
    """
    if action not in {"start", "stop"}:
        raise ValueError("Only start and stop are permitted")
    try:
        normalized = str(uuid.UUID(server_uuid))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("The Pelican server container must use its UUID") from None
    if normalized != server_uuid:
        raise ValueError("Use the canonical Pelican server UUID")
    token = local_token(config_path)
    body = json.dumps({"action": action, "wait_seconds": 0}).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:8080/api/servers/{normalized}/power",
        data=body, method="POST", headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json"})
    # Local control never uses an HTTP proxy from the host's environment.
    client = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with client.open(request, timeout=8) as reply:
            if reply.status != 202:
                raise RuntimeError("Wings did not accept the power request")
    except urllib.error.HTTPError as error:
        # Do not include the request, Authorization or body in a chained error.
        code = error.code
        error.close()
        raise RuntimeError(f"Local Wings power request returned HTTP {code}") from None
