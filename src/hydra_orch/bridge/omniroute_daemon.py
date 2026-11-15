"""Idempotent local gateway startup; the shared daemon outlives the Hydra UI."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from urllib.parse import urlsplit

import httpx

from hydra_orch.bridge.worker_runner import cancel_process_tree


async def _listening(host, port):
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), .75)
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


async def _launch(executable, host, port, timeout):
    # Keep the Hydra access credential out of the independent gateway daemon.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('HYDRA_')}
    env.update(OMNIROUTE_SERVER_HOST=host, HOSTNAME=host,
               API_PORT=str(port), DASHBOARD_PORT=str(port))
    options = ({'creationflags': subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == 'nt' else {'start_new_session': True})
    process = await asyncio.create_subprocess_exec(
        executable, 'serve', '--daemon', '--no-open', '--no-tray', '--port', str(port),
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL, env=env, **options)
    try:
        return await asyncio.wait_for(process.wait(), timeout) == 0
    finally:
        if process.returncode is None:
            await cancel_process_tree(process.pid)


async def ensure_local_gateway(base_url, api_key_env='OMNIROUTE_API_KEY', *, timeout=35,
                               transport=None, launcher=None, port_probe=None, locate=None):
    """Probe first, start only an absent loopback service, and await health.

    No provider request, installation, restart, stop, or combo mutation occurs.
    Injectable boundaries allow cold-start tests without touching a shared daemon.
    """
    url = urlsplit(base_url)
    origin = f'{url.scheme}://{url.netloc}'
    headers = {}
    key = os.environ.get(api_key_env)
    if key:
        headers['Authorization'] = 'Bearer ' + key
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(transport=transport, headers=headers, trust_env=False,
                                timeout=httpx.Timeout(2, connect=.75)) as client:
        async def healthy():
            try:
                response = await client.get(origin + '/api/health')
                return response.status_code == 200 and response.json().get('status') == 'ok'
            except (httpx.HTTPError, ValueError, AttributeError):
                return False

        if await healthy():
            return {'status': 'reused', 'ready': True, 'message': 'OmniRoute já estava em execução.'}
        if url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1', '::1'}:
            return {'status': 'external', 'ready': False, 'message': 'O endereço configurado não permite partida local automática.'}
        host, port = url.hostname, url.port or 80
        if await (port_probe or _listening)(host, port):
            return {'status': 'port_busy', 'ready': False, 'message': 'A porta do OmniRoute está ocupada, mas a saúde não foi confirmada. O processo existente foi preservado.'}
        executable = (locate or shutil.which)('omniroute')
        if not executable:
            return {'status': 'not_installed', 'ready': False, 'message': 'OmniRoute não está instalado no PATH. O Hydra continua disponível.'}
        try:
            started = await (launcher or _launch)(executable, '127.0.0.1' if host == 'localhost' else host,
                                                  port, max(.1, deadline-time.monotonic()))
        except (OSError, asyncio.TimeoutError):
            started = False
        # Another launch can win a port race. Health, not the CLI exit code,
        # determines readiness; no existing process is stopped to clear the port.
        while time.monotonic() < deadline:
            if await healthy():
                return {'status': 'started' if started else 'reused', 'ready': True,
                        'message': 'OmniRoute disponível para o Hydra.'}
            if not started:
                break
            await asyncio.sleep(min(.25, max(0, deadline-time.monotonic())))
        return {'status': 'unavailable', 'ready': False, 'message': 'OmniRoute não confirmou saúde dentro do prazo. O Hydra continua disponível; confira a conexão em Configurações.'}
