"""Controlled CLI, real subprocesses/checks/worktrees; no provider certification."""
import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from test_conversation import service, create, ControlledRunner
from hydra_orch.core.conversation_coordinator import AgentReview, CoordinatorPlan, ConversationCoordinator, planning_sources
from hydra_orch.model import ContractViolation


def task(name, dependencies=()):
    return dict(id=name, title='Implementar '+name, objective='Criar implementação verificável '+name,
                paths=[name+'.py'], check_kind='python_compile', check_paths=[name+'.py'], dependencies=list(dependencies))


class CoordinatedCLI(ControlledRunner):
    def __init__(self, plan, root, broken=False):
        super().__init__()
        self.plan, self.root, self.broken = plan, root, broken

    async def run(self, turn, conv, prompt, cwd, emit):
        self.calls.append((turn, conv, prompt, cwd))
        assert conv['access_mode'] == 'read-only'
        answer = self.plan if turn['id'].endswith('-plan') else {'decision':'accepted', 'reason':'Controlled reviewer inspected the actual passing result.'}
        await emit('text.delta', {'text':json.dumps(answer)})

    async def invocation(self, child, cwd):
        code = '''import pathlib,sys,time,json
prompt=sys.stdin.read()
name=prompt.split('Trabalhe somente nos arquivos: ',1)[1].splitlines()[0]
root=pathlib.Path(sys.argv[1]);root.mkdir(exist_ok=True)
start=time.time()
if name != 'foundation.py':
    if sys.argv[3] == 'True': assert pathlib.Path('foundation.py').read_text() == 'VALUE = 1\\n'
    (root/name).write_text('ready')
    deadline=time.time()+15
    while len(list(root.glob('*.py'))) < 2 and time.time()<deadline: time.sleep(.02)
    assert len(list(root.glob('*.py'))) == 2, 'workers did not overlap'
    time.sleep(.15)
pathlib.Path(name).write_text('broken syntax !' if sys.argv[2]=='True' else 'VALUE = 1\\n')
with open(root/'timing.jsonl','a') as log:log.write(json.dumps([name,start,time.time()])+'\\n')
print('worker complete')
'''
        return [sys.executable, '-c', code, str(self.root), str(self.broken), str(bool(self.plan.get('foundation_id')))], {}, ExitStack(), {}


@pytest.mark.parametrize('bad', [
    {'objective':'Bad plan','tasks':[task('same'),task('same')]},
    {'objective':'Bad plan','tasks':[{**task('escape'),'paths':['../escape.py']}]},
    {'objective':'Bad plan','tasks':[{**task('credential'),'paths':['.env.local']}]},
    {'objective':'Bad plan','tasks':[task('a',['unknown'])]},
    {'objective':'Bad plan','tasks':[task('a'),{**task('b'),'paths':['a.py']}]},
])
def test_plan_rejects_unsafe_or_overlapping_ownership(bad):
    with pytest.raises(ValidationError):
        CoordinatorPlan.model_validate(bad)


@pytest.mark.parametrize('plan', [
    {'objective': 'Empty implementation', 'tasks': []},
    {'objective': 'Missing report', 'intent': 'analysis', 'tasks': []},
    {'objective': 'Mixed modes', 'intent': 'analysis', 'report': 'A sufficiently detailed report.', 'tasks': [task('a')]},
    {'objective': 'Mixed modes', 'report': 'A sufficiently detailed report.', 'tasks': [task('a')]},
])
def test_report_and_executable_plan_cannot_be_confused(plan):
    with pytest.raises(ValidationError):
        CoordinatorPlan.model_validate(plan)


def test_initial_reading_is_bounded_and_excludes_credentials(tmp_path):
    (tmp_path/'README.md').write_text('# Projeto\n'+'x'*2000, encoding='utf-8')
    (tmp_path/'pyproject.toml').write_text('[project]\nname="example"', encoding='utf-8')
    (tmp_path/'.env').write_text('SECRET=do-not-include')
    result = planning_sources(tmp_path, ['README.md', 'pyproject.toml', '.env'], budget_chars=1000)
    assert len(result) <= 1000
    assert '# Projeto' in result and 'trecho inicial' in result
    assert 'do-not-include' not in result


@pytest.mark.asyncio
@pytest.mark.parametrize('access_mode', ['read-only', 'workspace-write'])
async def test_repository_analysis_returns_report_without_workers_even_with_write_permission(service, tmp_path, access_mode):
    report = '# O que o projeto faz\n\nO ponto de entrada está em README.md.\n\n## Melhorias\n\nRevisar o fluxo; testes não executados nesta análise.'
    plan = {'objective': 'Explicar o projeto e propor melhorias', 'intent': 'analysis', 'report': report, 'tasks': []}
    runner = CoordinatedCLI(plan, tmp_path/'must-not-dispatch')
    service.runner = runner
    cid, _ = await create(service, execution_mode='swarm', access_mode=access_mode)
    await service._execute(await service.claim())
    snapshot = await service.snapshot(cid)
    turn = snapshot['turns'][0]
    assert turn['state'] == 'completed', turn['error']
    assert turn['response'] == report
    assert '# Projeto teste' in runner.calls[0][2]
    assert 'run_id' not in turn['coordination']
    assert not (tmp_path/'must-not-dispatch').exists()
    assert not list(Path(snapshot['workspace_path']).glob('*.py'))
    events = await service.events(cid)
    assert any(e['type'] == 'coordinator.analysis' for e in events)
    assert not any(e['type'] in {'coordinator.plan', 'coordinator.run', 'coordinator.task'} for e in events)


@pytest.mark.asyncio
async def test_planning_timeout_is_specific_and_preserves_read_events_without_claiming_worker_results(service):
    class SlowPlanner(ControlledRunner):
        def __init__(self):
            super().__init__()
            self.cancelled_jobs = []

        async def run(self, turn, conv, prompt, cwd, emit):
            assert conv['access_mode'] == 'read-only'
            assert 'Não rode testes' in prompt
            await emit('tool.started', {'tool': 'Read', 'detail': 'README.md'})
            await asyncio.Event().wait()

        async def cancel(self, job):
            self.cancelled_jobs.append(job)

    runner = SlowPlanner()
    service.runner = runner
    # The event is persisted to SQLite on the real filesystem. Allow that read
    # event to commit before testing cancellation of the deliberately hung CLI;
    # 30ms races Windows disk scheduling instead of the behavior under test.
    service.coordinator = ConversationCoordinator(service.runs, runner, structured_timeout_seconds=1, total_timeout_seconds=5)
    cid, _ = await create(service, execution_mode='swarm', access_mode='workspace-write')
    claimed = await service.claim()
    await service._execute(claimed)
    turn = (await service.snapshot(cid))['turns'][0]
    assert turn['state'] == 'failed'
    assert 'leitura e o planejamento' in turn['error']
    assert 'Nenhum worker foi iniciado' in turn['error']
    assert 'limite total' not in turn['error']
    assert not turn['coordination'].get('run_id')
    assert claimed['id']+'-plan' in runner.cancelled_jobs
    events = await service.events(cid)
    assert any(e['type'] == 'tool.started' for e in events)
    assert any(e['type'] == 'coordinator.diagnostic' and e['payload']['stage'] == 'planning' for e in events)


@pytest.mark.asyncio
async def test_review_timeout_is_not_reported_as_planning_or_total_timeout(service, tmp_path):
    class SlowReviewer(ControlledRunner):
        async def run(self, turn, conv, prompt, cwd, emit):
            await asyncio.Event().wait()

    runner = SlowReviewer()
    coordinator = ConversationCoordinator(service.runs, runner, structured_timeout_seconds=.01)
    observed = []
    async def emit(kind, payload):
        observed.append((kind, payload))
    with pytest.raises(ContractViolation) as error:
        await coordinator._structured('review-step', {'executor':'codex'}, tmp_path, 'Review', AgentReview, emit)
    assert error.value.code == 'coordinator_review_timeout'
    assert 'revisão do agente' in str(error.value)
    assert observed[0][1]['stage'] == 'review'


@pytest.mark.asyncio
async def test_worker_phase_timeout_names_preserved_execution(service, tmp_path):
    runner = CoordinatedCLI({'objective':'Timeout during execution','tasks':[task('a'),task('b')]},tmp_path/'workers')
    service.runner = runner
    service.coordinator = ConversationCoordinator(service.runs, runner, execution_timeout_seconds=.01, total_timeout_seconds=10)
    cid, _ = await create(service, execution_mode='swarm', access_mode='workspace-write')
    await service._execute(await service.claim())
    turn = (await service.snapshot(cid))['turns'][0]
    assert turn['state'] == 'failed'
    assert 'execução das tarefas' in turn['error']
    assert turn['coordination']['run_id'] in turn['error']
    assert turn['coordination']['phase'] == 'stopped'
    assert 'limite total' not in turn['error']


@pytest.mark.asyncio
@pytest.mark.parametrize('foundation', [False, True])
async def test_conversation_coordinates_real_workers_checks_review_and_isolated_integration(service, tmp_path, foundation, monkeypatch):
    tasks = ([task('foundation')] if foundation else []) + [task('a', ['foundation'] if foundation else []),task('b',['foundation'] if foundation else [])]
    plan = {'objective':'Two independently owned project changes', 'tasks':tasks, 'foundation_id':'foundation' if foundation else None}
    service.runner = CoordinatedCLI(plan,tmp_path/'barrier')
    cid, project = await create(service, access_mode='workspace-write', execution_mode='swarm')
    claimed = await service.claim()
    await service._execute(claimed)
    snapshot = await service.snapshot(cid)
    turn = snapshot['turns'][0]
    assert turn['state'] == 'completed', turn['error']
    cwd = Path(snapshot['workspace_path'])
    assert (cwd/'a.py').read_text() == (cwd/'b.py').read_text() == 'VALUE = 1\n'
    assert not (service.runs.repo_root/'a.py').exists()
    assert subprocess.run(['git','status','--porcelain'],cwd=service.runs.repo_root,capture_output=True,text=True).stdout == ''
    timings = [json.loads(line) for line in (tmp_path/'barrier'/'timing.jsonl').read_text().splitlines() if not line.startswith('["foundation')]
    assert max(t[1] for t in timings) < min(t[2] for t in timings)
    assert turn['coordination']['phase'] == 'completed'
    assert all(t['state']=='accepted' for t in turn['coordination']['tasks'].values())
    assert 'a.py' in turn['diff'] and 'b.py' in turn['diff']
    run_id = turn['coordination']['run_id']
    assert (await service.store.get_run(run_id))['status']=='succeeded'
    detail=await service.runs.get_run_detail(run_id)
    assert all(task['current_attempt']['result']['review']['actor'].startswith('agent:') for task in detail['tasks'])
    from hydra_orch import server
    monkeypatch.setattr(server,'get_run_service',lambda:service.runs)
    artifacts=await service.store.get_artifacts(run_id)
    check_log=next(a for a in artifacts if a.kind=='check_output')
    preview=await server.get_run_artifact_content_endpoint(run_id,check_log.artifact_id,max_bytes=4096)
    assert preview['artifact_id']==check_log.artifact_id
    with pytest.raises(ContractViolation, match='isolada'):
        # Even a policy flag never authorizes automatic review of the original.
        record = await service.store.get_run(run_id)
        fake = {**record['spec'].model_dump(mode='json'), 'run_id':'original-review', 'repo_root':str(service.runs.repo_root), 'idempotency_key':'original-review-test'}
        from hydra_orch.model import RunSpec
        replacements = {t['task_id']:'original-'+str(i) for i,t in enumerate(fake['tasks'])}
        fake['tasks'] = [{**t,'run_id':'original-review','task_id':replacements[t['task_id']], 'dependencies':[replacements[d] for d in t['dependencies']]} for t in fake['tasks']]
        await service.runs.submit_run(RunSpec.model_validate(fake))
        await service.runs._assert_isolated_agent_review('original-review')


@pytest.mark.asyncio
async def test_failed_worker_checks_preserve_results_without_integration(service, tmp_path):
    plan = {'objective':'Do not integrate invalid Python', 'tasks':[task('a'),task('b')]}
    service.runner = CoordinatedCLI(plan,tmp_path/'barrier',broken=True)
    cid,_ = await create(service,access_mode='workspace-write',execution_mode='swarm')
    await service._execute(await service.claim())
    snapshot=await service.snapshot(cid)
    assert snapshot['turns'][0]['state']=='failed'
    assert 'verificações' in snapshot['turns'][0]['error']
    assert not (Path(snapshot['workspace_path'])/'a.py').exists()
    assert snapshot['turns'][0]['coordination']['phase']=='stopped'


@pytest.mark.asyncio
async def test_read_only_coordination_plans_without_starting_workers(service, tmp_path):
    service.runner = CoordinatedCLI({'objective':'Read-only plan','tasks':[task('a')]},tmp_path/'never-start')
    cid,_ = await create(service,execution_mode='swarm')
    await service._execute(await service.claim())
    turn=(await service.snapshot(cid))['turns'][0]
    assert turn['state']=='completed'
    assert 'modo de leitura' in turn['response']
    assert not (tmp_path/'never-start').exists()


@pytest.mark.asyncio
async def test_cancel_coordination_terminates_owned_worker_and_preserves_original(service, tmp_path, monkeypatch):
    from hydra_orch.bridge import worker_runner
    killed = []
    original_cancel = worker_runner.cancel_process_tree
    async def cancel_tree(pid, **kwargs):
        killed.append(pid)
        return await original_cancel(pid, **kwargs)
    monkeypatch.setattr(worker_runner,'cancel_process_tree',cancel_tree)
    service.runner = CoordinatedCLI({'objective':'Cancelable worker','tasks':[task('a')]},tmp_path/'barrier')
    cid,_ = await create(service,access_mode='workspace-write',execution_mode='swarm')
    claimed = await service.claim()
    execution = asyncio.create_task(service._execute(claimed))
    try:
        for _ in range(300):
            if (tmp_path/'barrier'/'a.py').exists(): break
            if execution.done(): pytest.fail((await service.snapshot(cid))['turns'][0]['error'])
            await asyncio.sleep(.1)
        assert (tmp_path/'barrier'/'a.py').exists()
        snapshot=await service.snapshot(cid)
        run_id=snapshot['turns'][0]['coordination']['run_id']
        attempts=await service.store.list_attempts(run_id+'-0')
        assert attempts[0].process_status.value == 'running'
        await service.cancel(cid,claimed['id'])
        await asyncio.wait_for(asyncio.gather(execution,return_exceptions=True),20)
        assert (await service.snapshot(cid))['turns'][0]['state']=='cancelled'
        from hydra_orch.bridge.worker_runner import is_process_alive
        assert killed and all(not is_process_alive(pid) for pid in killed)
        assert not (service.runs.repo_root/'a.py').exists()
    finally:
        if not execution.done():
            execution.cancel()
            await asyncio.gather(execution,return_exceptions=True)
