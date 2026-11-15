"""Explicit conversation targets, read-only catalog and evidence-based admission."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from hydra_orch.core.redaction import redact
from hydra_orch.model import ContractViolation


class ConversationRoute(BaseModel):
    model_config = ConfigDict(extra='forbid')
    executor: Literal['codex', 'claude'] = 'codex'
    connection_mode: Literal['direct', 'omniroute'] = 'direct'
    target_kind: Literal['model', 'combo'] = 'model'
    target_ref: str = Field(default='', max_length=300)

    def checked(self):
        if any(ord(c) < 32 for c in self.target_ref) or self.target_ref != self.target_ref.strip():
            raise ContractViolation('route_invalid', 'Escolha um nome de modelo ou combo válido.')
        if self.connection_mode == 'direct' and self.target_kind != 'model':
            raise ContractViolation('route_invalid', 'Combos exigem conexão OmniRoute.')
        if self.connection_mode == 'omniroute' and not self.target_ref:
            raise ContractViolation('route_invalid', 'Escolha o modelo ou combo do OmniRoute.')
        return self


def route_from(conversation):
    raw = conversation.get('route_json') or '{}'
    return json.loads(raw) if raw != '{}' else ConversationRoute(executor=conversation['executor']).model_dump()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def direct_models(executor):
    if executor == 'claude':
        return [{'id': x, 'name': x.capitalize()} for x in ('sonnet', 'opus', 'haiku')]
    try:
        cache = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'models_cache.json'
        data = json.loads(cache.read_text(encoding='utf-8'))
        return [{'id': m['slug'], 'name': m.get('display_name', m['slug'])} for m in data.get('models', [])
                if m.get('visibility') == 'list' and isinstance(m.get('slug'), str) and 'auto-review' not in m['slug']]
    except (OSError, ValueError, TypeError):
        return []


class ConversationRoutes:
    def __init__(self, store, gateway):
        self.store, self.gateway = store, gateway
        self._cache = None
        self._cache_at = 0
        self._lock = asyncio.Lock()
        self._versions = {}
        self.certifying = asyncio.Lock()
        self._settings_loaded = False

    async def settings(self):
        from hydra_orch.core.preferences import PreferenceService
        saved = await PreferenceService(self.store).get_preference('user', 'operator', 'integration.omniroute')
        if saved:
            value = json.loads(saved.value_json)
            self.gateway.base_url = value['base_url']
            self.gateway.quota_api_url = value['base_url'].removesuffix('/v1') + '/api/usage/quota'
            self.gateway.enabled = value['enabled']
        self._settings_loaded = True
        return {'base_url': self.gateway.base_url, 'enabled': self.gateway.enabled,
                'credential_available': bool(self.gateway._resolve_api_key()),
                'credential_env': self.gateway.api_key_env, 'version': saved.version if saved else 0}

    async def save_settings(self, *, base_url, enabled, expected_version, idempotency_key):
        from urllib.parse import urlsplit
        from hydra_orch.core.preferences import PreferenceService
        try:
            url = urlsplit(base_url)
        except ValueError as exc:
            raise ContractViolation('route_invalid', 'Use um endereço HTTP/HTTPS válido.') from exc
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ContractViolation('route_invalid', 'Use um endereço HTTP/HTTPS sem credenciais, consulta ou fragmento.')
        try:
            url.port
        except ValueError as exc:
            raise ContractViolation('route_invalid', 'A porta do endereço não é válida.') from exc
        value = {'base_url': base_url.rstrip('/'), 'enabled': enabled}
        await PreferenceService(self.store).set_preference('user', 'operator', 'integration.omniroute', value,
            expected_version=expected_version, idempotency_key=idempotency_key)
        self._cache = None
        return await self.settings()

    async def version(self, executor):
        if executor not in self._versions:
            exe = shutil.which(executor)
            def read():
                if not exe:
                    return 'not-installed'
                try:
                    p = subprocess.run([exe, '--version'], capture_output=True, timeout=10, stdin=subprocess.DEVNULL,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    return p.stdout.decode('utf-8', errors='replace').strip()[:100] if p.returncode == 0 else 'unknown'
                except (OSError, subprocess.TimeoutExpired):
                    return 'unknown'
            self._versions[executor] = await asyncio.to_thread(read)
        return self._versions[executor]

    async def raw(self, refresh=False):
        if not self._settings_loaded or refresh:
            await self.settings()
        if refresh or self._cache is None or time.monotonic() - self._cache_at > 30:
            async with self._lock:
                if refresh or self._cache is None or time.monotonic() - self._cache_at > 30:
                    self._cache = await self.gateway.conversation_catalog()
                    self._cache_at = time.monotonic()
        return self._cache

    @staticmethod
    def leaves(item, combos, seen=(), definitions=None):
        name = item.get('name', '')
        if name in seen or len(seen) > 12:
            raise ValueError('Combo com referência circular ou profundidade excessiva.')
        if definitions is not None:
            definitions[name] = item
        if item.get('strategy', 'priority') not in {'priority', 'round-robin', 'weighted', 'fill-first'}:
            raise ValueError('A estratégia deste combo ainda não foi certificada para ferramentas.')
        if any(item.get(k) for k in ('shadowRouting', 'evalRouting', 'shadow', 'eval')):
            raise ValueError('Alvos auxiliares precisam de certificação específica.')
        result = []
        for step in item.get('models', []):
            if isinstance(step, str):
                result.append(step)
            elif isinstance(step, dict) and step.get('kind') == 'combo-ref':
                child = combos.get(step.get('comboName'))
                if child is None:
                    raise ValueError('O combo referencia outro combo indisponível.')
                result.extend(ConversationRoutes.leaves(child, combos, (*seen, name), definitions))
            elif isinstance(step, dict) and isinstance(step.get('model'), str):
                result.append(step['model'])
            else:
                raise ValueError('O combo contém um destino não reconhecido.')
        if not result:
            raise ValueError('Este combo não contém modelos.')
        return result

    async def describe(self, selection, *, refresh=False):
        route = ConversationRoute.model_validate(selection).checked()
        value = route.model_dump()
        metadata = {'cli_version':await self.version(route.executor),
                    'protocol':'codex_jsonl' if route.executor=='codex' else 'claude_stream_json'}
        if route.connection_mode == 'direct':
            known = {m['id'] for m in direct_models(route.executor)}
            if route.target_ref and route.target_ref not in known:
                raise ContractViolation('route_invalid', 'O modelo não está no catálogo local deste agente. Atualize a lista.')
            return {**value, **metadata, 'fingerprint': identity({**value,**metadata}), 'compatibility': 'verified', 'reason': 'Conexão nativa do agente.'}
        raw = await self.raw(refresh)
        if raw['status'] != 'connected':
            raise ContractViolation('gateway_unavailable', 'Não foi possível conectar ao OmniRoute. Confira o estado da conexão.')
        combos = {c.get('name'): c for c in raw.get('combos', []) if isinstance(c, dict)}
        if route.target_kind == 'combo':
            item = combos.get(route.target_ref)
            if item is None:
                raise ContractViolation('combo_not_found', 'O combo não está disponível. Atualize a lista e escolha novamente.')
            try:
                definition = {}
                leaves = self.leaves(item, combos, definitions=definition)
            except ValueError as e:
                raise ContractViolation('route_unsupported', str(e)) from e
        else:
            item = next((m for m in raw.get('models', []) if isinstance(m, dict) and m.get('id') == route.target_ref), None)
            if item is None:
                raise ContractViolation('model_not_found', 'O modelo não está disponível no gateway.')
            leaves, definition = [route.target_ref], item
        if route.executor == 'claude' and any(not any(part.startswith('claude-') for part in m.split('/')) for m in leaves):
            raise ContractViolation('route_unsupported', 'Claude Code exige que todos os destinos do combo sejam modelos Claude.')
        fingerprint = identity({'route': value, 'definition': definition, 'base_url': self.gateway.base_url,
                                'cli_version': await self.version(route.executor), 'profile': 2})
        await self.store.initialize()
        async with self.store._connect() as db:
            row = await (await db.execute('SELECT evidence_json FROM conversation_route_certificates WHERE certificate_key=?', (fingerprint,))).fetchone()
        return {**value, **metadata, 'fingerprint': fingerprint, 'compatibility': 'verified' if row else 'unverified',
                'reason': 'Leitura, edição e continuidade verificadas.' if row else 'Teste esta combinação antes de enviar.',
                'evidence': json.loads(row[0]) if row else None}

    async def validate(self, selection, *, refresh=False):
        described = await self.describe(selection, refresh=refresh)
        if described['compatibility'] != 'verified':
            raise ContractViolation('route_unverified', 'Use Testar combinação para validar ferramentas e continuidade antes de enviar.')
        return described

    async def catalog(self, executor='codex', refresh=False, include_gateway=True):
        if not include_gateway:
            return {'status': 'not_requested', 'combos': [], 'models': [], 'direct_models': direct_models(executor)}
        raw = await self.raw(refresh)
        combos = []
        for item in raw.get('combos', [])[:1000]:
            if not isinstance(item, dict) or not isinstance(item.get('name'), str):
                continue
            if not item['name'].strip() or len(item['name']) > 300 or any(ord(c) < 32 for c in item['name']):
                continue
            selection = ConversationRoute(executor=executor, connection_mode='omniroute', target_kind='combo', target_ref=item['name']).model_dump()
            try:
                info = await self.describe(selection)
                compatibility, reason = info['compatibility'], info['reason']
            except ContractViolation as e:
                compatibility, reason = 'unsupported', str(e)
            combos.append({'id': str(item.get('id') or item['name']), 'name': item['name'], 'target_kind': 'combo',
                           'compatibility': compatibility, 'reason': reason})
        models = [{'id': m['id'], 'name': m['id'], 'target_kind': 'model'} for m in raw.get('models', [])[:5000]
                  if isinstance(m, dict) and isinstance(m.get('id'), str)]
        return redact({'status': raw['status'], 'combos_status': raw.get('combos_status'),
                       'models_status': raw.get('models_status'), 'observed_at': datetime.now(timezone.utc).isoformat(),
                       'combos': combos, 'models': models, 'direct_models': direct_models(executor),
                       'base_url': self.gateway.base_url, 'cli_version': await self.version(executor)})

    async def certify(self, selection, runner, runtime_dir):
        """Explicit operator action: prove file tools and native continuation in a fixture."""
        import secrets
        import uuid
        async with self.certifying:
            info = await self.describe(selection, refresh=True)
            if info['connection_mode'] == 'direct':
                return info
            if info['compatibility'] == 'verified':
                return info
            run_id = 'cert-' + uuid.uuid4().hex
            root = Path(runtime_dir).resolve() / 'route_certification' / run_id
            root.mkdir(parents=True)
            nonce = secrets.token_hex(12)
            (root / 'origem.txt').write_text(nonce, encoding='utf-8')
            conv = {'id': run_id, 'executor': info['executor'], 'access_mode': 'workspace-write',
                    'workspace_kind': 'folder', 'route': info, '_gateway_base_url': self.gateway.base_url,
                    '_gateway_token': self.gateway._resolve_api_key(), '_agent_state_dir': str(root.parent / (run_id + '_agent'))}
            events = []
            async def emit(kind, payload):
                if kind == 'session.started':
                    conv['native_session_id'] = payload['session_id']
                events.append({'type': kind, **payload})
                with (root.parent / (run_id + '_events.jsonl')).open('a', encoding='utf-8') as log:
                    log.write(json.dumps(redact({'type': kind, **payload}), ensure_ascii=False) + '\n')
            started = time.monotonic()
            try:
                await asyncio.wait_for(runner.run({'id': run_id}, conv,
                    'Teste de ferramentas: leia origem.txt e crie resultado.txt com exatamente o mesmo conteúdo. '
                    'Use ferramentas de arquivo ou shell; não descreva comandos como se tivessem sido executados. Não faça commit.', root, emit), 100)
                result = root / 'resultado.txt'
                if not result.is_file() or result.is_symlink() or result.read_text(encoding='utf-8-sig').strip() != nonce:
                    raise ContractViolation('route_certification_failed', 'A resposta chegou, mas o agente não comprovou leitura e edição de arquivo. A combinação continua bloqueada.')
                if not conv.get('native_session_id'):
                    raise ContractViolation('route_certification_failed', 'O agente não confirmou uma sessão para continuidade.')
                events.clear()
                await asyncio.wait_for(runner.run({'id': run_id}, conv,
                    'Sem reler arquivos, retorne apenas o conteúdo que você copiou no pedido anterior.', root, emit), 100)
                answer = ''.join(e.get('text', '') for e in events if e['type'] == 'text.delta')
                if nonce not in answer:
                    raise ContractViolation('route_certification_failed', 'A continuidade de contexto não foi comprovada. A combinação continua bloqueada.')
                current = await self.describe(selection, refresh=True)
                if current['fingerprint'] != info['fingerprint']:
                    raise ContractViolation('route_changed', 'O combo mudou durante o teste. Atualize e tente novamente.')
                evidence = {'executor': info['executor'], 'cli_version': await self.version(info['executor']),
                            'target_kind': info['target_kind'], 'target_ref': info['target_ref'],
                            'file_read_write': True, 'native_continuation': True,
                            'seconds': round(time.monotonic() - started, 2),
                            'observed_at': datetime.now(timezone.utc).isoformat(),
                            'scope': 'selected route and observed upstream; unexercised fallbacks are not individually certified'}
                async with self.store._connect() as db:
                    await db.execute('INSERT OR REPLACE INTO conversation_route_certificates(certificate_key,evidence_json) VALUES(?,?)',
                                     (info['fingerprint'], json.dumps(evidence)))
                return await self.describe(selection)
            except asyncio.TimeoutError as exc:
                raise ContractViolation('route_certification_failed', 'O teste do modelo excedeu o tempo limite. A combinação continua bloqueada; confira a disponibilidade no OmniRoute ou escolha outra rota.') from exc
            finally:
                await runner.cancel(run_id)
