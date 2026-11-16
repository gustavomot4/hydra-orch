"""Agent temp roots must not grant fresh sandboxes the user's shared temp tree."""
from contextlib import contextmanager
import pytest

from hydra_orch.bridge.conversation_runner import ConversationRunner
from hydra_orch.bridge.worker_runner import filter_worker_env
from hydra_orch.model import ContractViolation


@pytest.fixture
def scoped_invocation(monkeypatch, tmp_path):
    import hydra_orch.bridge.conversation_runner as module
    import hydra_orch.bridge.codex_catalog as catalog
    import hydra_orch.bridge.omniroute_transport as transport

    monkeypatch.setattr(module, 'resolve_agent_executable', lambda _: 'codex')
    monkeypatch.setattr(module, '_bundled_codex_needs_no_daemon', lambda _: False)
    monkeypatch.setattr(catalog, 'gateway_catalog', lambda exe, target, home: home/'gateway-model.json')

    @contextmanager
    def delegate(*args):
        yield 'http://127.0.0.1:12345/v1', 'scoped-test-delegate', {}

    monkeypatch.setattr(transport, 'codex_transport', delegate)
    shared = tmp_path/'shared-temp'
    shared.mkdir()
    for key in ('TEMP', 'TMP', 'TMPDIR'):
        monkeypatch.setenv(key, str(shared))
    return {
        'executor': 'codex', 'access_mode': 'workspace-write', 'workspace_kind': 'git',
        'route': {'connection_mode': 'omniroute', 'target_ref': 'test-combo'},
        '_gateway_base_url': 'http://127.0.0.1:20128/v1', '_gateway_token': 'upstream-test-key',
    }


@pytest.mark.asyncio
async def test_parallel_agent_temp_roots_are_private_and_stable_on_resume(scoped_invocation, tmp_path):
    runner = ConversationRunner()
    roots = []
    for agent, resume in [('worker-a', None), ('worker-b', None), ('worker-a', 'native-session')]:
        state = tmp_path/agent
        args, env, transport, _ = await runner.invocation({
            **scoped_invocation, '_agent_state_dir': str(state), 'native_session_id': resume,
        }, tmp_path)
        try:
            private = (state/'tmp').absolute()
            assert private.is_dir()
            assert all(env[key] == str(private) for key in ('TEMP', 'TMP', 'TMPDIR'))
            # The coordinator filters the invocation environment a second time.
            forwarded = filter_worker_env(allowed_env=env)
            assert forwarded['TEMP'] == str(private)
            assert env['CODEX_HOME'] == str(state/'codex_home')
            assert 'workspace-write' in args
            assert '--dangerously-bypass-approvals-and-sandbox' not in args
            assert 'features.plugins=false' in args
            assert env['OMNIROUTE_API_KEY'] == 'scoped-test-delegate'
            roots.append(private)
        finally:
            transport.close()
    assert roots[0] != roots[1]
    assert roots[0] == roots[2]


@pytest.mark.asyncio
async def test_agent_temp_root_cannot_redirect_to_another_directory(scoped_invocation, tmp_path):
    state = tmp_path/'worker'
    state.mkdir()
    elsewhere = tmp_path/'elsewhere'
    elsewhere.mkdir()
    try:
        (state/'tmp').symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip('Creating directory symlinks requires Windows developer mode or privilege')
    with pytest.raises(ContractViolation, match='temporário'):
        await ConversationRunner().invocation({**scoped_invocation, '_agent_state_dir': str(state)}, tmp_path)
    assert list(elsewhere.iterdir()) == []


@pytest.mark.asyncio
async def test_agent_temp_root_rejects_a_file(scoped_invocation, tmp_path):
    state = tmp_path/'worker'
    state.mkdir()
    (state/'tmp').write_text('preserve this file', encoding='utf-8')
    with pytest.raises(ContractViolation, match='temporário'):
        await ConversationRunner().invocation({**scoped_invocation, '_agent_state_dir': str(state)}, tmp_path)
    assert (state/'tmp').read_text(encoding='utf-8') == 'preserve this file'
