import httpx
import pytest
from hydra_orch import server
from hydra_orch.core.auth import TokenVerifier

TOKEN = "isolated-desktop-session-test-0123456789"
HEADERS = {"Origin": "http://127.0.0.1:8000", "Sec-Fetch-Site": "same-origin", "X-Hydra-Desktop": "1"}


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    monkeypatch.setenv("HYDRA_LOCAL_DESKTOP", "1")
    monkeypatch.setenv("HYDRA_API_TOKEN", TOKEN)
    monkeypatch.setitem(server.app.state._state, "token_verifier", TokenVerifier.from_token(TOKEN))
    monkeypatch.setitem(server.app.state._state, "cors_allow_origins", ["http://127.0.0.1:8000"])
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><head></head><body>Hydra fixture</body></html>")
    (dist / "assets" / "main.js").write_text("console.log('fixture')")
    monkeypatch.setitem(server.app.state._state, "desktop_dist_dir", dist)
    return httpx.ASGITransport(app=server.app, client=("127.0.0.1", 12345))


@pytest.mark.asyncio
async def test_same_origin_desktop_bootstrap_keeps_api_protected(desktop):
    async with httpx.AsyncClient(transport=desktop, base_url="http://127.0.0.1:8000") as client:
        response = await client.post("/v1/launcher/session", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["token"] == TOKEN
        assert response.headers["cache-control"] == "no-store"
        assert (await client.get("/v1/control-plane/projects")).status_code == 401
        assert (await client.get("/quota_status")).status_code == 401
        page = await client.get("/chat/conversation-test")
        assert page.status_code == 200
        assert 'name="hydra-desktop"' in page.text
        assert TOKEN not in page.text
        assert page.headers["x-frame-options"] == "DENY"
        assert (await client.get("/assets/main.js")).status_code == 200
        assert (await client.get("/assets/missing.js")).status_code == 404
        assert (await client.get("/config.yaml")).status_code != 200


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"Origin": "https://example.com"}, {"Sec-Fetch-Site": "cross-site"}, {"X-Hydra-Desktop": ""}, {"Origin": ""}])
async def test_bootstrap_rejects_cross_origin_and_missing_proof(desktop, changes):
    async with httpx.AsyncClient(transport=desktop, base_url="http://127.0.0.1:8000") as client:
        assert (await client.post("/v1/launcher/session", headers={**HEADERS, **changes})).status_code == 403
        assert (await client.get("/v1/launcher/session", headers=HEADERS)).status_code == 403


@pytest.mark.asyncio
async def test_bootstrap_rejects_remote_client_rebound_host_and_manual_server(desktop, monkeypatch):
    remote = httpx.ASGITransport(app=server.app, client=("10.0.0.2", 12345))
    async with httpx.AsyncClient(transport=remote, base_url="http://127.0.0.1:8000") as client:
        assert (await client.post("/v1/launcher/session", headers=HEADERS)).status_code == 403
    async with httpx.AsyncClient(transport=desktop, base_url="http://evil.example:8000") as client:
        assert (await client.post("/v1/launcher/session", headers=HEADERS)).status_code == 403
    monkeypatch.delenv("HYDRA_LOCAL_DESKTOP")
    async with httpx.AsyncClient(transport=desktop, base_url="http://127.0.0.1:8000") as client:
        assert (await client.post("/v1/launcher/session", headers=HEADERS)).status_code == 403
        assert (await client.get("/")).status_code == 401


@pytest.mark.asyncio
async def test_desktop_stop_requires_bearer_and_explicit_launcher_owner(desktop, monkeypatch):
    stopped = []
    monkeypatch.setitem(server.app.state._state, "desktop_shutdown", lambda: stopped.append(True))
    async with httpx.AsyncClient(transport=desktop, base_url="http://127.0.0.1:8000") as client:
        assert (await client.post("/v1/launcher/stop")).status_code == 401
        assert not stopped
        assert (await client.post("/v1/launcher/stop", headers={"Authorization": f"Bearer {TOKEN}"})).status_code == 200
        assert stopped == [True]


@pytest.mark.asyncio
async def test_folder_picker_is_authenticated_local_and_cancelable(desktop, monkeypatch):
    async def pick(): return None
    monkeypatch.setitem(server.app.state._state, "desktop_folder_picker", pick)
    async with httpx.AsyncClient(transport=desktop, base_url="http://127.0.0.1:8000") as client:
        assert (await client.post("/v1/launcher/pick-folder")).status_code == 401
        response = await client.post("/v1/launcher/pick-folder", headers={"Authorization": f"Bearer {TOKEN}"})
        assert response.status_code == 200 and response.json()["path"] is None
        monkeypatch.delenv("HYDRA_LOCAL_DESKTOP")
        assert (await client.post("/v1/launcher/pick-folder", headers={"Authorization": f"Bearer {TOKEN}"})).status_code == 404
