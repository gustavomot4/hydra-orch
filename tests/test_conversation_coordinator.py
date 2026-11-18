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
from hydra_orch.core.conversation_coordinator import AgentReview, CoordinatorPlan, ConversationCoordinator, PlannedTask, planning_sources
from hydra_orch.core.run_service import RunService
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
    service.worker_timeout_seconds = 417
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
    run_record = await service.store.get_run(run_id)
    assert run_record['status']=='succeeded'
    assert all(t.timeout_seconds == 417 for t in run_record['spec'].tasks)
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
    assert 'SyntaxError' in snapshot['turns'][0]['error']
    assert 'exit 1' in snapshot['turns'][0]['error']


@pytest.mark.asyncio
@pytest.mark.parametrize('broken', [False, True])
async def test_validation_only_runs_real_checks_without_worker_patch_or_integration(service, tmp_path, broken):
    if broken:
        readme = service.runs.repo_root/'README.md'
        readme.write_text('# Broken\n[Missing](missing-file.md)\n', encoding='utf-8')
        subprocess.run(['git', 'add', 'README.md'], cwd=service.runs.repo_root, check=True)
        subprocess.run(['git', 'commit', '-m', 'broken fixture'], cwd=service.runs.repo_root, check=True, capture_output=True)
    validation = {**task('check-docs'), 'operation': 'validate', 'category': 'review',
                  'paths': ['README.md'], 'check_kind': 'docs', 'check_paths': ['README.md']}
    runner = CoordinatedCLI({'objective': 'Check existing documentation without edits', 'tasks': [validation]}, tmp_path/'never-start')
    async def unexpected(*args, **kwargs):
        pytest.fail('Validation must not launch a coding worker')
    runner.invocation = unexpected
    service.runner = runner
    cid, _ = await create(service, execution_mode='swarm', access_mode='workspace-write')
    await service._execute(await service.claim())
    turn = (await service.snapshot(cid))['turns'][0]
    assert turn['state'] == ('failed' if broken else 'completed'), turn['error']
    assert not turn['diff']
    assert not turn['coordination']['run_id']
    evidence = turn['coordination']['tasks']['check-docs']
    assert evidence['operation'] == 'validate'
    assert evidence['checks'][0]['exit_code'] == int(broken)
    assert evidence['artifacts']
    assert not (tmp_path/'never-start').exists()
    if broken:
        assert 'missing-file.md' in turn['error']
    else:
        assert 'Local Markdown links' in turn['response']


def test_frontend_checks_use_project_tools_and_explicit_tsconfig(monkeypatch):
    monkeypatch.setattr('hydra_orch.core.conversation_coordinator.shutil.which', lambda _: 'node')
    spec = PlannedTask(**{**task('types'), 'check_kind': 'typescript', 'check_paths': ['tsconfig.json'], 'check_cwd': 'frontend'})
    check = ConversationCoordinator.checks(spec)[0]
    assert check.command[-2:] == ('-p', 'tsconfig.json')
    assert check.cwd == 'frontend'
    vitest = spec.model_copy(update={'check_kind': 'vitest', 'check_paths': ['tests']})
    assert ConversationCoordinator.checks(vitest)[0].command == ('node', 'node_modules/vitest/vitest.mjs', 'run', 'tests')


@pytest.mark.asyncio
async def test_mixed_plan_validates_then_integrates_only_the_edit(service, tmp_path):
    validation = {**task('check-docs'), 'operation': 'validate', 'paths': ['README.md'],
                  'check_kind': 'docs', 'check_paths': ['README.md']}
    service.runner = CoordinatedCLI({'objective': 'Validate documentation then implement',
        'tasks': [validation, task('foundation')]}, tmp_path/'workers')
    cid, _ = await create(service, execution_mode='swarm', access_mode='workspace-write')
    await service._execute(await service.claim())
    snapshot = await service.snapshot(cid)
    turn = snapshot['turns'][0]
    assert turn['state'] == 'completed', turn['error']
    assert 'foundation.py' in turn['diff']
    assert turn['coordination']['tasks']['check-docs']['checks'][0]['exit_code'] == 0
    run = await service.store.get_run(turn['coordination']['run_id'])
    assert len(run['spec'].tasks) == 1
    assert run['status'] == 'succeeded'


@pytest.mark.asyncio
async def test_validation_splits_pytest_directory_into_evidenced_file_checks(service, tmp_path):
    directory = tmp_path/'isolated'
    (directory/'tests').mkdir(parents=True)
    for name in ['one', 'two']:
        (directory/'tests'/f'test_{name}.py').write_text('def test_ok():\n    assert 2 + 2 == 4\n', encoding='utf-8')
    coordinator = ConversationCoordinator(service.runs, ControlledRunner())
    validation = PlannedTask(**{**task('suite'), 'operation': 'validate', 'check_kind': 'pytest', 'check_paths': ['tests']})
    events = []
    async def emit(kind, payload):
        events.append((kind, payload))
    await coordinator.validate(validation, directory, 'a'*40, 'cr-file-checks', emit)
    checks = events[-1][1]['checks']
    assert len(checks) == 2 and all(c['exit_code'] == 0 for c in checks)
    assert {c['command'][-1] for c in checks} == {'tests/test_one.py', 'tests/test_two.py'}


@pytest.mark.asyncio
@pytest.mark.parametrize('parallel', [False, True])
async def test_plain_folder_automatically_runs_checked_agents_inside_nested_runtime(service, tmp_path, parallel):
    # Reproduce the desktop layout: the plain conversation copy lives inside
    # Hydra's own Git checkout. That checkout and the source must stay untouched.
    parent = service.runs.repo_root
    service.runs = RunService(parent,store=service.store,runtime_dir=parent/'.orchestrator')
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=parent,text=True).strip()
    source = tmp_path/'plain-source'
    source.mkdir()
    (source/'README.md').write_text('Original plain folder\n')
    (source/'.env').write_text('PRIVATE=do-not-copy')
    project = await service.runs.create_project(source,'Plain project',allow_plain_folder=True)
    tasks = [task('a'),task('b')] if parallel else [task('foundation')]
    service.runner = CoordinatedCLI({'objective':'Build in an ordinary folder','tasks':tasks},tmp_path/'barrier')
    created = await service.create(project_id=project['id'],executor='codex',content='Implementar o projeto',
                                   execution_mode='swarm',access_mode='workspace-write',idempotency_key='plain-coordinated-first-0001')
    cid = created['conversation_id']
    await service._execute(await service.claim())
    snap = await service.snapshot(cid)
    turn = snap['turns'][0]
    assert turn['state']=='completed',turn['error']
    assert turn['coordination']['phase']=='completed'
    assert all(v['state']=='accepted' for v in turn['coordination']['tasks'].values())
    working = Path(snap['workspace_path'])
    assert (working/'.git').is_file()
    assert not (working/'.env').exists()
    for t in tasks:
        assert (working/(t['id']+'.py')).read_text()=='VALUE = 1\n'
        assert t['id']+'.py' in turn['diff']
    assert (source/'README.md').read_text()=='Original plain folder\n'
    assert sorted(p.name for p in source.iterdir())==['.env','README.md']
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=parent,text=True).strip()==head
    assert subprocess.check_output(['git','status','--porcelain'],cwd=parent,text=True)==''
    # Continue the same conversation using its existing private repository.
    service.runner = CoordinatedCLI({'objective':'Continue the same ordinary folder','tasks':[task('next'),task('after')]},tmp_path/'next-barrier')
    service.coordinator = None
    await service.send(cid,content='Continue a implementação',idempotency_key='plain-coordinated-second-0001',expected_last_seq=snap['last_seq'])
    await service._execute(await service.claim())
    continued = await service.snapshot(cid)
    assert continued['turns'][-1]['state']=='completed',continued['turns'][-1]['error']
    assert continued['workspace_path']==snap['workspace_path']
    assert (working/'README.md').read_text()=='Original plain folder\n'
    assert (working/'next.py').read_text()=='VALUE = 1\n'
    assert (working/'after.py').read_text()=='VALUE = 1\n'


@pytest.mark.asyncio
async def test_plain_folder_read_only_plan_does_not_prepare_git(service, tmp_path):
    source=tmp_path/'source'
    source.mkdir()
    project=await service.runs.create_project(source,'Plain read-only',allow_plain_folder=True)
    service.runner=CoordinatedCLI({'objective':'Plan only','tasks':[task('foundation')]},tmp_path/'unused')
    result=await service.create(project_id=project['id'],executor='codex',content='Prepare um plano',
                                execution_mode='swarm',access_mode='read-only',idempotency_key='plain-readonly-coordination-0001')
    await service._execute(await service.claim())
    snap=await service.snapshot(result['conversation_id'])
    assert snap['turns'][0]['state']=='completed'
    assert not (Path(snap['workspace_path'])/'.git').exists()
    assert not (source/'.git').exists()


@pytest.mark.asyncio
async def test_failed_plain_folder_conversation_can_continue_without_recreating_it(service, tmp_path):
    class PreviousPolicy:
        active = {}
        async def run(self, turn, conv, prompt, cwd, emit):
            await emit('coordinator.plan',{'plan':{'objective':'Preserved plan','tasks':[task('foundation')]},'run_id':'cr-old-plan'})
            raise ContractViolation('coordinator_git_required','A execução paralela exige uma cópia Git.')

    source=tmp_path/'source'
    source.mkdir()
    project=await service.runs.create_project(source,'Recover plain folder',allow_plain_folder=True)
    result=await service.create(project_id=project['id'],executor='codex',content='Criar o projeto',
                                execution_mode='swarm',access_mode='workspace-write',idempotency_key='plain-old-policy-first-0001')
    cid=result['conversation_id']
    service.coordinator=PreviousPolicy()
    await service._execute(await service.claim())
    failed=await service.snapshot(cid)
    assert failed['turns'][0]['state']=='failed'
    working=Path(failed['workspace_path'])
    (working/'manual.md').write_text('Keep edits made after the failure')
    service.coordinator=None
    service.runner=CoordinatedCLI({'objective':'Resume preserved project','tasks':[task('foundation')]},tmp_path/'unused')
    await service.send(cid,content='Continue',idempotency_key='plain-old-policy-resume-0001',expected_last_seq=failed['last_seq'])
    await service._execute(await service.claim())
    resumed=await service.snapshot(cid)
    assert resumed['workspace_path']==failed['workspace_path']
    assert resumed['turns'][0]['state']=='failed'
    assert resumed['turns'][0]['coordination']['run_id']=='cr-old-plan'
    assert resumed['turns'][1]['state']=='completed',resumed['turns'][1]['error']
    assert (working/'foundation.py').is_file()
    assert (working/'manual.md').read_text()=='Keep edits made after the failure'
    assert not (source/'.git').exists()


@pytest.mark.asyncio
async def test_worker_timeout_is_specific_and_retains_diagnostics(service, tmp_path):
    class SlowWorker(CoordinatedCLI):
        async def invocation(self, child, cwd):
            return [sys.executable, '-c', "import time;print('worker-started',flush=True);time.sleep(30)"], {}, ExitStack(), {}

    service.runner = SlowWorker({'objective':'Bounded worker execution','tasks':[task('a')]}, tmp_path/'unused')
    service.worker_timeout_seconds = 1
    cid, _ = await create(service, access_mode='workspace-write', execution_mode='swarm')
    await service._execute(await service.claim())
    turn = (await service.snapshot(cid))['turns'][0]
    assert turn['state'] == 'failed'
    assert 'limite de 1 segundos' in turn['error']
    assert 'sem consolidação final' in turn['error']
    assert 'antes de executar as verificações' not in turn['error']
    assert turn['coordination']['phase'] == 'stopped'
    assert 'limite de 1 segundos' in turn['coordination']['tasks']['a']['summary']
    detail = await service.runs.get_run_detail(turn['coordination']['run_id'])
    assert detail['tasks'][0]['current_attempt']['process_status'] == 'timed_out'


def test_server_passes_configured_worker_timeout_to_conversations(service, monkeypatch):
    from hydra_orch import server
    monkeypatch.setattr(server, 'get_run_service', lambda: service.runs)
    monkeypatch.setattr(server, 'get_attachment_service', lambda: None)
    monkeypatch.setattr(server, 'get_conversation_routes', lambda: None)
    monkeypatch.setattr(server.app.state, 'conversation_service', None, raising=False)
    monkeypatch.setattr(server.config.execution, 'timeout_seconds', 487)
    assert server.get_conversation_service().worker_timeout_seconds == 487


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
@pytest.mark.asyncio
@pytest.mark.parametrize('broken_lockfile', [False, True])
async def test_frontend_worktree_installs_foundation_dependencies_then_repairs_types(service, tmp_path, broken_lockfile):
    import shutil
    compiler = Path(__file__).resolve().parents[1] / 'frontend/node_modules/typescript/bin/tsc'
    if not compiler.is_file() or not shutil.which('node') or not shutil.which('npm'):
        pytest.skip('Requires Node, npm, and the repository frontend toolchain')
    repo = service.runs.repo_root
    package = repo / 'frontend/vendor/typescript'
    (package / 'bin').mkdir(parents=True)
    (package / 'package.json').write_text('{"name":"typescript","version":"1.0.0"}', encoding='utf-8')
    (package / 'bin/tsc').write_text(f'require({json.dumps(str(compiler))})\n', encoding='utf-8')
    (repo / 'frontend/tsconfig.json').write_text('{"compilerOptions":{"types":[]},"files":["app.ts"]}', encoding='utf-8')
    subprocess.run(['git', 'add', 'frontend'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', 'fixture frontend compiler'], cwd=repo, check=True, capture_output=True)

    foundation = {**task('foundation'), 'paths': ['frontend/package.json', 'frontend/package-lock.json'],
                  'check_kind': 'docs', 'check_paths': ['README.md']}
    frontend = {**task('frontend', ['foundation']), 'paths': ['frontend/app.ts'],
                'check_kind': 'typescript', 'check_cwd': 'frontend', 'check_paths': ['tsconfig.json']}
    class FrontendCLI(CoordinatedCLI):
        async def invocation(self, child, cwd):
            code = r'''
from pathlib import Path
import json, sys
prompt = sys.stdin.read()
root = Path('frontend')
if 'Trabalhe somente nos arquivos: frontend/package.json' in prompt:
    package = {'name': 'fixture', 'devDependencies': {'typescript': 'file:vendor/typescript'}}
    lock = {'name': 'fixture', 'lockfileVersion': 3, 'packages': {
        '': package,
        'node_modules/typescript': {'resolved': 'vendor/typescript', 'link': True},
        'vendor/typescript': {'name': 'typescript', 'version': '1.0.0', 'dev': True},
    }}
    (root / 'package.json').write_text(json.dumps(package))
    (root / 'package-lock.json').write_text('invalid-lockfile' if sys.argv[1] == 'True' else json.dumps(lock))
else:
    assert not (root / 'node_modules').exists()
    app = root / 'app.ts'
    if 'A revisão anterior foi restaurada' in prompt:
        assert 'TS2322' in prompt
        assert 'const size: number = "errado"' in app.read_text()
        app.write_text('const size: number = 2;\n')
    else:
        app.write_text('const size: number = "errado";\n')
print(json.dumps({'type': 'turn.completed', 'model': 'gpt-test-observed'}))
'''
            return [sys.executable, '-c', code, str(broken_lockfile)], {}, ExitStack(), {}

    service.runner = FrontendCLI({'objective': 'Preparar e verificar frontend', 'foundation_id': 'foundation',
                                  'tasks': [foundation, frontend]}, tmp_path)
    cid, _ = await create(service, access_mode='workspace-write', execution_mode='swarm')
    await service._execute(await service.claim())
    snapshot = await service.snapshot(cid)
    turn = snapshot['turns'][0]
    progress = turn['coordination']['tasks']['frontend']
    if broken_lockfile:
        assert turn['state'] == 'failed'
        assert 'prepare-node-frontend' in turn['error']
        assert [attempt['state'] for attempt in progress['attempts']] == ['failed']
        assert not (repo / 'frontend/node_modules').exists()
        return
    assert turn['state'] == 'completed', turn['error']
    assert [attempt['state'] for attempt in progress['attempts']] == ['failed', 'ready_for_review']
    assert progress['identity']['model'] == 'gpt-test-observed'
    assert not (repo / 'frontend/app.ts').exists()
    assert not (repo / 'frontend/node_modules').exists()
    assert (Path(snapshot['workspace_path']) / 'frontend/app.ts').read_text() == 'const size: number = 2;\n'
    original = await service.store.get_attempt(progress['attempts'][0]['id'])
    assert 'errado' in (Path(original.workspace_path) / 'frontend/app.ts').read_text()
