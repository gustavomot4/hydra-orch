"""Gateway startup without provider inference or changing a shared OmniRoute."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import httpx
import pytest

from hydra_orch.bridge.omniroute_daemon import ensure_local_gateway
from hydra_orch.bridge.worker_runner import cancel_process_tree, is_process_alive
from hydra_orch.config import HydraConfig, GatewayUnavailableError
from hydra_orch.core.router import HydraRouter
from test_conversation import service


async def free(*_): return False


def health_mock(ready=False):
    return httpx.MockTransport(lambda _: httpx.Response(200 if ready else 503, json={'status':'ok' if ready else 'unavailable'}))


@pytest.mark.asyncio
async def test_running_gateway_is_reused_without_a_cli_or_port_mutation():
    def forbidden(*_): pytest.fail('A running gateway must not start another CLI')
    result=await ensure_local_gateway('http://127.0.0.1:20128/v1',transport=health_mock(True),locate=forbidden,port_probe=forbidden)
    assert result['ready'] and result['status']=='reused'


@pytest.mark.asyncio
async def test_occupied_unhealthy_port_is_preserved():
    async def busy(*_): return True
    def forbidden(*_): pytest.fail('Never replace the owner of an occupied port')
    result=await ensure_local_gateway('http://127.0.0.1:20128/v1',transport=health_mock(),port_probe=busy,locate=forbidden)
    assert not result['ready'] and result['status']=='port_busy'


@pytest.mark.asyncio
async def test_external_address_never_launches_a_local_daemon():
    async def forbidden(*_): pytest.fail('Do not bind a remote address')
    result=await ensure_local_gateway('https://gateway.example/v1',transport=health_mock(),port_probe=forbidden)
    assert result['status']=='external'


@pytest.mark.asyncio
async def test_missing_cli_and_failed_launch_are_explicit_nonfatal_results():
    result=await ensure_local_gateway('http://localhost:20128/v1',transport=health_mock(),port_probe=free,locate=lambda _:None)
    assert result['status']=='not_installed'
    async def fail(*_): raise OSError('fixture failure')
    result=await ensure_local_gateway('http://localhost:20128/v1',transport=health_mock(),port_probe=free,locate=lambda _:'fixture',launcher=fail)
    assert result['status']=='unavailable' and not result['ready']


@pytest.mark.asyncio
async def test_start_wait_is_bounded_without_claiming_success():
    async def launch(*_): return True
    result=await asyncio.wait_for(ensure_local_gateway('http://127.0.0.1:20128/v1',timeout=.05,
        transport=health_mock(),port_probe=free,locate=lambda _:'fixture',launcher=launch),1)
    assert not result['ready'] and result['status']=='unavailable'


@pytest.mark.asyncio
async def test_cold_start_real_process_health_reuse_and_credential_separation(tmp_path, monkeypatch):
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
    pidfile=tmp_path/'pid'
    evidence=tmp_path/'launch.json'
    server=tmp_path/'server.py'
    server.write_text('''import http.server,sys
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"status":"ok"}')
 def log_message(self,*args):pass
http.server.HTTPServer(('127.0.0.1',int(sys.argv[1])),Handler).serve_forever()
''')
    cli=tmp_path/'cli.py'
    cli.write_text('''import json,os,pathlib,subprocess,sys
root=pathlib.Path(__file__).parent
assert sys.argv[1]=='serve' and all(flag in sys.argv for flag in ['--daemon','--no-open','--no-tray'])
port=sys.argv[sys.argv.index('--port')+1]
data={'args':sys.argv[1:],'hydra_secret_absent':'HYDRA_API_TOKEN' not in os.environ,'bind':os.environ['OMNIROUTE_SERVER_HOST']}
(root/'launch.json').write_text(json.dumps(data))
flags={'creationflags':subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
child=subprocess.Popen([sys.executable,str(root/'server.py'),port],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags)
(root/'pid').write_text(str(child.pid))
''')
    shim=tmp_path/('omniroute.cmd' if os.name=='nt' else 'omniroute')
    if os.name=='nt':shim.write_text(f'@echo off\r\n"{sys.executable}" "{cli}" %*\r\n')
    else:
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{cli}" "$@"\n');shim.chmod(0o755)
    monkeypatch.setenv('HYDRA_API_TOKEN','fixture-secret-must-stay-in-hydra')
    monkeypatch.setenv('OMNIROUTE_API_KEY','fixture-only-omni-credential')
    try:
        first=await ensure_local_gateway(f'http://127.0.0.1:{port}/v1',timeout=8,locate=lambda _:str(shim))
        assert first['ready'] and first['status']=='started'
        pid=int(pidfile.read_text());assert is_process_alive(pid)
        before=evidence.stat().st_mtime_ns
        second=await ensure_local_gateway(f'http://127.0.0.1:{port}/v1',timeout=3,locate=lambda _:str(shim))
        assert second['status']=='reused' and evidence.stat().st_mtime_ns==before
        assert json.loads(evidence.read_text())['hydra_secret_absent']
        assert json.loads(evidence.read_text())['bind']=='127.0.0.1'
        # Leaving ensure/startup does not stop the shared service.
        assert is_process_alive(pid)
    finally:
        if pidfile.exists():assert await cancel_process_tree(int(pidfile.read_text()))


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['optional','required'])
async def test_optional_opens_but_required_remains_fail_closed(monkeypatch,mode):
    import hydra_orch.bridge.omniroute_daemon as daemon
    async def unavailable(*_):return {'ready':False,'status':'unavailable','message':'fixture unavailable'}
    async def unavailable_gateway(*_):return False
    monkeypatch.setattr(daemon,'ensure_local_gateway',unavailable)
    from hydra_orch.bridge.omniroute_client import OmniRouteClient
    monkeypatch.setattr(OmniRouteClient,'is_available',unavailable_gateway)
    router=HydraRouter(HydraConfig.model_validate({'omniroute':{'enabled':True,'connection_mode':mode,'auto_start_daemon':True}}))
    if mode=='required':
        with pytest.raises(GatewayUnavailableError):await router.ensure_gateway()
    else:await router.ensure_gateway()
    assert router.gateway_startup['status']=='unavailable'


@pytest.mark.parametrize('optout',[False,True])
def test_desktop_enables_autostart_with_an_explicit_environment_optout(monkeypatch,optout):
    from hydra_orch import server,desktop_backend
    config=HydraConfig()
    monkeypatch.setattr(server,'config',config)
    monkeypatch.setitem(server.app.state._state,'desktop_shutdown',None)
    monkeypatch.setattr(sys,'argv',['hydra-desktop'])
    if optout:monkeypatch.setenv('HYDRA_OMNIROUTE_AUTOSTART','0')
    else:monkeypatch.delenv('HYDRA_OMNIROUTE_AUTOSTART',raising=False)
    class Server:
        should_exit=False
        def __init__(self,*_,**kwargs):pass
        def run(self):pass
    monkeypatch.setattr(desktop_backend.uvicorn,'Server',Server)
    desktop_backend.main()
    assert config.omniroute.auto_start_daemon is not optout
    assert config.omniroute.enabled is not optout


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled',[True,False])
async def test_startup_reads_saved_connection_before_autostart(service,monkeypatch,enabled):
    from hydra_orch import server
    from hydra_orch.core.auth import TokenVerifier
    from hydra_orch.core.conversation_route import ConversationRoutes
    from hydra_orch.bridge.omniroute_client import OmniRouteClient
    import hydra_orch.bridge.omniroute_daemon as daemon
    cfg=HydraConfig.model_validate({'omniroute':{'enabled':True,'connection_mode':'optional','auto_start_daemon':True}})
    routes=ConversationRoutes(service.store,OmniRouteClient(enabled=True))
    await routes.save_settings(base_url='http://127.0.0.1:22345/v1',enabled=enabled,
        expected_version=0,idempotency_key='saved-startup-connection-test')
    router=HydraRouter(cfg);router.checkpointer=service.store
    seen=[]
    async def ensure(url,key):
        seen.append(url);return {'ready':True,'status':'reused','message':'fixture ready'}
    monkeypatch.setattr(daemon,'ensure_local_gateway',ensure)
    monkeypatch.setattr(server,'config',cfg)
    monkeypatch.setattr(server,'router',router)
    monkeypatch.setattr(server,'get_conversation_routes',lambda:routes)
    monkeypatch.setattr(server,'load_token_verifier',lambda:TokenVerifier.from_token('isolated-startup-auth-token-1234567'))
    monkeypatch.setattr(server,'ssh_manager',None)
    monkeypatch.setitem(server.app.state._state,'token_verifier',None)
    await server.startup_event()
    assert seen==(['http://127.0.0.1:22345/v1'] if enabled else [])
    assert cfg.omniroute.enabled is enabled
