"""Scoped loopback Responses transport for the CLI's plain function-tool profile.

The gateway currently drops native tools when hosted/custom tools are mixed in.
Keep the tested function protocol; execution and permissions remain in Codex.
No text is interpreted as a tool invocation here.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading

import httpx


def function_request(body, target):
    if not isinstance(body, dict) or not isinstance(body.get('tools', []), list):
        raise ValueError('Formato de requisição inválido.')
    if body.get('model') != target:
        raise ValueError('Modelo diferente da rota selecionada.')
    allowed = {'model', 'input', 'instructions', 'tool_choice', 'parallel_tool_calls', 'reasoning',
               'stream', 'max_output_tokens', 'previous_response_id'}
    request = {k: v for k, v in body.items() if k in allowed}
    request['tools'] = [t for t in body.get('tools', []) if isinstance(t, dict) and t.get('type') == 'function']
    # The CLI can always read/edit through its sandboxed shell tool. Unsupported
    # freeform, hosted search and deferred discovery are deliberately not exposed.
    if not any(t.get('name') in {'exec_command', 'shell_command', 'shell'} for t in request['tools']):
        raise ValueError('O agente não forneceu uma ferramenta de execução compatível.')
    return request


@contextmanager
def codex_transport(base_url, upstream_key, target):
    delegate = secrets.token_urlsafe(32)
    stopped = threading.Event()
    observed = {'models': [], 'source': 'omniroute.responses'}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path != '/v1/responses' or not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + delegate):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8 * 1024 * 1024:
                    raise ValueError('Tamanho inválido.')
                payload = function_request(json.loads(self.rfile.read(length)), target)
            except (ValueError, TypeError, KeyError):
                self.send_error(400, 'Invalid agent request')
                return
            try:
                with httpx.Client(timeout=httpx.Timeout(60, connect=3)) as client:
                    with client.stream('POST', base_url.rstrip('/') + '/responses', json=payload,
                                       headers={'Authorization': 'Bearer ' + upstream_key, 'Accept-Encoding': 'identity'}) as response:
                        self.send_response(response.status_code)
                        self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                        pending = ''
                        for chunk in response.iter_raw():
                            if stopped.is_set():
                                break
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            pending += chunk.decode('utf-8', errors='replace')
                            while '\n' in pending:
                                line, pending = pending.split('\n', 1)
                                if line.startswith('data: '):
                                    try:
                                        event = json.loads(line[6:])
                                        model = event.get('response', {}).get('model')
                                        if isinstance(model, str) and model != target and model not in observed['models']:
                                            observed['models'].append(model)
                                    except (ValueError, AttributeError):
                                        pass
                            if len(pending) > 65536:
                                pending = ''
            except (httpx.HTTPError, OSError):
                self.close_connection = True

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', delegate, observed
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
