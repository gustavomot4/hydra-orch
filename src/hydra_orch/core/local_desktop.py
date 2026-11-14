"""Local launcher session bootstrap. Disabled for manually served or remote APIs."""
import os


def enabled():
    return os.environ.get("HYDRA_LOCAL_DESKTOP") == "1" and bool(os.environ.get("HYDRA_API_TOKEN"))


def loopback_request(request):
    return (enabled() and request.client is not None
            and request.client.host in {"127.0.0.1", "::1"}
            and request.url.hostname in {"127.0.0.1", "localhost", "::1"})


def allow_bootstrap(request):
    if not loopback_request(request) or request.method != "POST":
        return False
    origin = request.headers.get("origin", "")
    expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
    return (origin == expected and request.headers.get("sec-fetch-site") == "same-origin"
            and request.headers.get("x-hydra-desktop") == "1")


def public_frontend(request):
    path = request.url.path
    ui_routes = {"chat", "terminal", "workspace", "recursos", "automacoes", "dispositivos", "computador", "consumo", "configuracoes", "busca"}
    return (loopback_request(request) and request.method in {"GET", "HEAD"}
            and (path == "/" or path.startswith("/assets/") or path.strip("/").split("/")[0] in ui_routes))
