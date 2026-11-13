"""T25 proof with real worker processes, Git worktrees and SQLite state."""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from test_profile import profiles
from hydra_orch.core.agent_registry import DriverCertificationReport, CERTIFICATION_CHECKS
from hydra_orch.core.metrics import MetricsService
from hydra_orch.core.profile_service import ProfileDefinition
from hydra_orch.core.route_selector import RouteCandidate, RouteSelector
from hydra_orch.core.run_service import RunService
from hydra_orch.engine.orchestration import Orchestrator, OrchestrationPlan, CommandBinding, TaskOwnership
from hydra_orch.engine.relay import RelayPipelineEngine, retry_atomic_turn
from hydra_orch.engine.swarm import MultiSessionSwarmEngine
from hydra_orch.engine.persist import PersistentEngine
from hydra_orch.engine.healer import SelfHealer
from hydra_orch.model import BudgetPolicy, CheckSpec, ContractViolation, ReviewDecision, RunSpec, TaskSpec


DRIVER = '''import json, pathlib, sys, time
obj = json.loads(sys.stdin.read().splitlines()[0])
model = sys.argv[1]
for required in obj.get("requires", []):
    assert pathlib.Path(required).is_file(), required
path = pathlib.Path(obj["path"])
path.parent.mkdir(parents=True, exist_ok=True)
if obj.get("restore") and model != "broken":
    assert path.read_text() == "partial", "lost partial Git state"
if obj.get("log"):
    with open(obj["log"], "a") as f: f.write(json.dumps(["start", obj["path"], time.time()]) + "\\n")
if obj.get("barrier_dir"):
    bdir = pathlib.Path(obj["barrier_dir"])
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / obj["path"].replace("/", "_")).write_text("ready")
    deadline = time.monotonic() + obj.get("barrier_timeout", 10.0)
    while len(list(bdir.iterdir())) < obj.get("barrier_count", 2) and time.monotonic() < deadline:
        time.sleep(0.02)
time.sleep(obj.get("delay", 0))
path.write_text("partial" if model == "broken" or obj.get("check_repair") and not path.exists() else obj["content"])
if obj.get("log"):
    with open(obj["log"], "a") as f: f.write(json.dumps(["end", obj["path"], time.time()]) + "\\n")
sys.exit(1 if model == "broken" else 0)
'''


async def setup(profiles, tmp_path, *, mode='relay', jobs=None, models=('good',), max_repairs=2):
    profiles_service, definition, repository, existing = profiles
    binary = Path(sys.executable)
    profiles_service.agents.locate = lambda _: str(binary)
    agent = await profiles_service.agents.get_agent(definition.agent_ref)
    report = DriverCertificationReport(agent_id=agent.agent_id, driver_type='codex', agent_version='1',
        platform=platform.system(), executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        capabilities=agent.declared_capabilities, passed_checks=tuple(CERTIFICATION_CHECKS), simulated=False,
        issued_at=datetime.now(timezone.utc))
    report_path = profiles_service.agents.certification_root / 'worker.json'
    report_path.write_text(report.model_dump_json())
    await profiles_service.agents.import_certificate(agent.agent_id, report_path, principal_id='operator')
    definition = ProfileDefinition.model_validate({**definition.model_dump(mode='json'), 'orchestration_mode': mode,
        'resource_limits': BudgetPolicy(max_parallel_worktrees=2).model_dump(mode='json')})
    await profiles_service.update_profile(definition, expected_revision=1)
    jobs = jobs or [{'path': 'src/output.txt', 'content': 'verified'}]
    run_id = 'orchestration-run'
    tasks = []
    for i, job in enumerate(jobs):
        path = job['path']
        task = TaskSpec(task_id=f'job-{i}', run_id=run_id, objective=json.dumps(job), assigned_executor='codex',
            acceptance_criteria=(CheckSpec(check_id=f'check-{i}', command=(sys.executable, '-c',
                f'from pathlib import Path; assert Path({path!r}).read_text() == {job["content"]!r}')),),
            allowed_paths=(path,), dependencies=('job-0',) if i and mode == 'swarm' else (), max_repair_attempts=max_repairs)
        tasks.append(task)
    run = RunSpec.model_validate({**existing.model_dump(mode='json'), 'run_id': run_id, 'tasks': [t.model_dump(mode='json') for t in tasks],
        'orchestration_mode': mode, 'idempotency_key': 'orchestration-fixture-001',
        'budget_policy': BudgetPolicy(max_parallel_worktrees=2).model_dump(mode='json')})
    runs = RunService(repo_root=run.repo_root, store=profiles_service.store)
    await runs.submit_run(run)
    routes = tuple(RouteCandidate(route_id=f'route-{i}', agent_id=agent.agent_id, model_ref=model, priority=i) for i, model in enumerate(models))
    data = dict(run=run, profile_id=definition.profile_id, repository_id=repository['id'], routes=routes,
        commands=tuple(CommandBinding(route_id=r.route_id, args=('-c', DRIVER, r.model_ref)) for r in routes),
        ownership=tuple(TaskOwnership(task_id=t.task_id, paths=t.allowed_paths) for t in tasks))
    if mode == 'swarm':
        data.update(foundation_task_id=tasks[0].task_id, foundation_checks=tasks[0].acceptance_criteria)
    plan = OrchestrationPlan(**data)
    selector = RouteSelector(runs.store, profiles_service.agents, MetricsService(runs.store))
    return Orchestrator(runs, profiles_service, selector), plan


async def accept(result):
    return ReviewDecision(result_id=result.result_id, actor='delegated-test-reviewer', decision='accepted',
        reason='Explicitly reviewed actual diff and passing checks in this fixture', expected_revision=result.revision)


async def reconcile_fixture(checkpoint):
    # This executable fixture only writes local files; its effects are known.
    assert checkpoint.tools_executed[-1].status == 'unknown'
    return True


@pytest.mark.asyncio
async def test_two_wave_real_foundation_parallel_workers_and_integration(profiles, tmp_path):
    log = tmp_path / 'workers.jsonl'
    barrier_dir = tmp_path / 'barrier'
    engine, plan = await setup(profiles, tmp_path, mode='swarm', jobs=[
        {'path': 'src/foundation.txt', 'content': 'contract'},
        {'path': 'src/a/output.txt', 'content': 'a', 'requires': ['src/foundation.txt'], 'delay': 0.2, 'log': str(log), 'barrier_dir': str(barrier_dir), 'barrier_count': 2},
        {'path': 'src/b/output.txt', 'content': 'b', 'requires': ['src/foundation.txt'], 'delay': 0.2, 'log': str(log), 'barrier_dir': str(barrier_dir), 'barrier_count': 2}])
    before = engine.runs.git_workspace.snapshot_operator_checkout()
    result = await MultiSessionSwarmEngine(engine).execute_swarm(plan, principal_id='operator', reviewer=accept, integrate=True)
    assert result.status == 'succeeded'
    assert engine.runs.git_workspace.snapshot_operator_checkout() == before
    foundation = (await engine.store.list_attempts('job-0'))[0]
    workers = [(await engine.store.list_attempts(f'job-{i}'))[0] for i in (1, 2)]
    assert foundation.base_sha == plan.run.base_sha
    assert workers[0].base_sha == workers[1].base_sha != plan.run.base_sha
    events = [json.loads(line) for line in log.read_text().splitlines()]
    starts = [e[2] for e in events if e[0] == 'start']
    ends = [e[2] for e in events if e[0] == 'end']
    assert max(starts) < min(ends), 'workers must overlap under parallel budget=2'
    assert (await engine.store.get_run(plan.run.run_id))['spec'].base_sha == plan.run.base_sha
    assert subprocess.run(['git', 'show', f'{result.result_sha}:src/a/output.txt'], cwd=plan.run.repo_root, capture_output=True, text=True, check=True).stdout == 'a'


@pytest.mark.asyncio
async def test_review_pause_restart_and_idempotent_completed_tasks(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path)
    report = await RelayPipelineEngine(engine).execute_relay(plan, principal_id='operator', integrate=True)
    assert report.status == 'needs_review'
    assert len(await engine.store.list_attempts('job-0')) == 1
    result = await Orchestrator(engine.runs, engine.profiles, engine.routes).execute(plan, principal_id='operator', reviewer=accept)
    assert result.status == 'ready_to_integrate'
    assert len(await engine.store.list_attempts('job-0')) == 1
    result = await engine.execute(plan, principal_id='operator', integrate=True)
    assert result.status == 'succeeded'
    with pytest.raises(ContractViolation, match='terminal'):
        await engine.execute(plan, principal_id='operator')


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['relay', 'persistent'])
async def test_sequential_stages_inherit_verified_git_base(profiles, tmp_path, mode):
    engine, plan = await setup(profiles, tmp_path, mode=mode, jobs=[
        {'path': 'src/a.txt', 'content': 'a'},
        {'path': 'src/b.txt', 'content': 'b', 'requires': ['src/a.txt']}])
    wrapper = RelayPipelineEngine(engine) if mode == 'relay' else PersistentEngine(engine)
    method = wrapper.execute_relay if mode == 'relay' else wrapper.execute_persistent
    result = await method(plan, principal_id='operator', reviewer=accept, integrate=True)
    assert result.status == 'succeeded'
    assert (await engine.store.list_attempts('job-1'))[0].base_sha != plan.run.base_sha


@pytest.mark.asyncio
async def test_bounded_real_repair_restores_git_state_and_preserves_source(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path, models=('broken', 'good'), jobs=[
        {'path': 'src/output.txt', 'content': 'repaired', 'restore': True}])
    report = await SelfHealer(engine).heal_build_failure(plan, principal_id='operator', reviewer=accept, handoff_reconciler=reconcile_fixture, integrate=True)
    assert report.status == 'succeeded'
    attempts = await engine.store.list_attempts('job-0')
    assert [a.model for a in attempts] == ['broken', 'good']
    assert attempts[0].workspace_path != attempts[1].workspace_path
    assert (Path(attempts[0].workspace_path) / 'src/output.txt').read_text() == 'partial'
    assert (Path(attempts[1].workspace_path) / 'src/output.txt').read_text() == 'repaired'
    checkpoint = await engine.store.get_handoff_checkpoint(attempts[0].attempt_id)
    assert checkpoint.affected_files == ('src/output.txt',)
    assert checkpoint.tools_executed[-1].status == 'unknown'
    assert len(checkpoint.decisions[-1]) == 64


@pytest.mark.asyncio
async def test_repair_exhaustion_never_claims_success(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path, models=('broken',), max_repairs=1)
    result = await engine.execute(plan, principal_id='operator', reviewer=accept, handoff_reconciler=reconcile_fixture, integrate=True)
    assert result.status == 'blocked'
    attempts = await engine.store.list_attempts('job-0')
    assert len(attempts) == 2
    assert await engine.store.get_handoff_checkpoint(attempts[-1].attempt_id)


@pytest.mark.asyncio
async def test_wave1_dependency_manifest_locked(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path, mode='swarm', jobs=[
        {'path': 'src/foundation.txt', 'content': 'base'},
        {'path': 'src/package.json', 'content': '{}'}])
    result = await engine.execute(plan, principal_id='operator', reviewer=accept, integrate=True)
    assert result.status == 'blocked'
    attempts = await engine.store.list_attempts('job-1')
    assert len(attempts) == 1
    failure = await engine.store.get_result_by_attempt(attempts[0].attempt_id)
    assert failure.failures[0].code == 'scope_violation'
    assert (Path(attempts[0].workspace_path) / 'src/package.json').exists()


@pytest.mark.asyncio
async def test_foundation_stops_before_workers_without_review(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path, mode='swarm', jobs=[
        {'path': 'src/foundation.txt', 'content': 'base'}, {'path': 'src/worker.txt', 'content': 'worker'}])
    result = await engine.execute(plan, principal_id='operator')
    assert result.status == 'needs_review'
    assert await engine.store.list_attempts('job-1') == []
    with pytest.raises(ContractViolation, match='Dependencies'):
        await engine.runs.execute_task_attempt(plan.run.run_id, 'job-1')


@pytest.mark.asyncio
async def test_plan_ownership_model_and_mode_validation(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path, mode='swarm', jobs=[
        {'path': 'src/foundation.txt', 'content': 'base'}, {'path': 'src/a.txt', 'content': 'a'}, {'path': 'src/b.txt', 'content': 'b'}])
    data = plan.model_dump(mode='json')
    for change in [dict(foundation_task_id=None), dict(foundation_checks=[]),
        dict(ownership=[]), dict(commands=[]), dict(routes=[{**data['routes'][0], 'mode': 'gateway'}])]:
        with pytest.raises(ValidationError):
            OrchestrationPlan.model_validate({**data, **change})
    owners = [dict(o, paths=['src/**']) for o in data['ownership']]
    with pytest.raises(ValidationError, match='overlap'):
        OrchestrationPlan.model_validate({**data, 'ownership': owners})
    for wrapper, method in [(RelayPipelineEngine(engine), 'execute_relay'), (PersistentEngine(engine), 'execute_persistent')]:
        with pytest.raises(ContractViolation):
            await getattr(wrapper, method)(plan, principal_id='operator')


@pytest.mark.asyncio
async def test_lease_plan_immutability_and_scope_revocation(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path)
    await engine.profiles.snapshot(plan.profile_id, plan.run.run_id, plan.repository_id, principal_id='operator')
    token = await engine._claim(plan)
    with pytest.raises(ContractViolation, match='active'):
        await engine.execute(plan, principal_id='operator')
    await engine._release(plan.run.run_id, token)
    changed = OrchestrationPlan.model_validate({**plan.model_dump(mode='json'), 'quota_wait_seconds': 1})
    with pytest.raises(ContractViolation, match='persisted'):
        await engine.execute(changed, principal_id='operator')
    await engine.profiles.workspaces.revoke_authorization(profiles[2]['authorization_id'], principal_id='operator')
    with pytest.raises(ContractViolation, match='current grant'):
        await engine.execute(plan, principal_id='operator')
    assert not await engine.store.list_attempts('job-0')


@pytest.mark.asyncio
async def test_atomic_turn_discards_partial_and_propagates_exhaustion():
    async def stream(ordinal):
        yield 'partial' if ordinal == 1 else 'complete'
        if ordinal == 1:
            raise RuntimeError('interrupted')
        yield ' turn'
    assert await retry_atomic_turn(stream) == 'complete turn'
    with pytest.raises(RuntimeError):
        await retry_atomic_turn(stream, max_attempts=1)
    for value in [0, True, 7]:
        with pytest.raises(ValueError):
            await retry_atomic_turn(stream, max_attempts=value)


@pytest.mark.asyncio
async def test_unknown_effects_require_reconciliation_and_changed_state_is_blocked(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path, models=('broken', 'good'))
    report = await engine.execute(plan, principal_id='operator', reviewer=accept)
    assert report.status == 'blocked'
    attempts = await engine.store.list_attempts('job-0')
    assert len(attempts) == 1
    checkpoint = await engine.store.get_handoff_checkpoint(attempts[0].attempt_id)
    assert checkpoint is not None
    # Same Git status, different bytes must invalidate the checkpoint as well.
    (Path(attempts[0].workspace_path) / 'src/output.txt').write_text('tampered')
    with pytest.raises(ContractViolation, match='changed after checkpoint'):
        await engine.execute(plan, principal_id='operator', reviewer=accept, handoff_reconciler=reconcile_fixture)
    assert len(await engine.store.list_attempts('job-0')) == 1


@pytest.mark.asyncio
async def test_foundation_combined_check_failure_stops_workers(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path, mode='swarm', jobs=[
        {'path': 'src/foundation.txt', 'content': 'base'}, {'path': 'src/worker.txt', 'content': 'worker'}])
    plan = OrchestrationPlan.model_validate({**plan.model_dump(mode='json'), 'foundation_checks': [
        CheckSpec(check_id='foundation-build', command=(sys.executable, '-c', 'raise SystemExit(1)')).model_dump(mode='json')]})
    with pytest.raises(ContractViolation, match='Consolidated'):
        await engine.execute(plan, principal_id='operator', reviewer=accept)
    assert not await engine.store.list_attempts('job-1')
    with pytest.raises(ContractViolation, match='explicit repair'):
        await engine.execute(plan, principal_id='operator', reviewer=accept)


@pytest.mark.asyncio
async def test_persistent_availability_wait_is_bounded_and_rechecks_route(profiles, tmp_path, monkeypatch):
    engine, plan = await setup(profiles, tmp_path, mode='persistent')
    plan = OrchestrationPlan.model_validate({**plan.model_dump(mode='json'), 'quota_wait_seconds': 0.05, 'quota_poll_seconds': 0.01})
    select = engine.routes.select
    calls = 0
    async def recovering(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ContractViolation('no_eligible_route', 'Unavailable fixture')
        return await select(*args, **kwargs)
    monkeypatch.setattr(engine.routes, 'select', recovering)
    report = await engine.execute(plan, principal_id='operator', reviewer=accept)
    assert report.status == 'ready_to_integrate' and calls == 2
    async def unavailable(*args, **kwargs):
        raise ContractViolation('no_eligible_route', 'Unavailable fixture')
    # A completed task is not dispatched again even if availability changed.
    monkeypatch.setattr(engine.routes, 'select', unavailable)
    assert (await engine.execute(plan, principal_id='operator')).status == 'ready_to_integrate'


@pytest.mark.asyncio
async def test_rejection_does_not_start_repair(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path)
    async def reject(result):
        return ReviewDecision(result_id=result.result_id, actor='reviewer', decision='rejected',
            reason='Do not retry this result', expected_revision=1)
    assert (await engine.execute(plan, principal_id='operator', reviewer=reject)).status == 'blocked'
    assert (await engine.execute(plan, principal_id='operator', reviewer=accept)).status == 'blocked'
    assert len(await engine.store.list_attempts('job-0')) == 1


@pytest.mark.asyncio
async def test_wall_budget_and_repository_scope_block_before_dispatch(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path)
    token = await engine._claim(plan)
    await engine._release(plan.run.run_id, token)
    async with engine.store._connect() as db:
        await db.execute("UPDATE commands SET response_json=json_set(response_json,'$.started_at','2000-01-01T00:00:00+00:00') WHERE scope='orchestration'")
    with pytest.raises(ContractViolation, match='wall-time budget'):
        await engine.execute(plan, principal_id='operator')
    assert not await engine.store.list_attempts('job-0')
    async with engine.store._connect() as db:
        await db.execute("UPDATE repositories SET allowed_paths_json='[\"src/other/**\"]' WHERE id=?", (plan.repository_id,))
    with pytest.raises(ContractViolation, match='current repository paths'):
        await engine.execute(plan, principal_id='operator')


@pytest.mark.asyncio
async def test_wrong_reviewer_result_rejected(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path)
    async def wrong(result):
        return ReviewDecision(result_id='other-result', actor='reviewer', decision='accepted', reason='Wrong result', expected_revision=1)
    with pytest.raises(ContractViolation, match='another result'):
        await engine.execute(plan, principal_id='operator', reviewer=wrong)
    assert (await engine.store.get_task('job-0'))['status'] == 'ready_for_review'


@pytest.mark.asyncio
async def test_cancelling_atomic_turn_propagates_without_retry():
    calls = 0
    async def stream(ordinal):
        nonlocal calls
        calls += 1
        yield 'partial'
        raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await retry_atomic_turn(stream)
    assert calls == 1


@pytest.mark.asyncio
async def test_repair_failed_checks_restores_committed_patch(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path, jobs=[
        {'path': 'src/output.txt', 'content': 'passes checks', 'check_repair': True}])
    report = await engine.execute(plan, principal_id='operator', reviewer=accept,
        handoff_reconciler=reconcile_fixture, integrate=True)
    assert report.status == 'succeeded'
    attempts = await engine.store.list_attempts('job-0')
    assert len(attempts) == 2
    first = await engine.store.get_result_by_attempt(attempts[0].attempt_id)
    assert first.failures[0].code == 'acceptance_check_failed'
    checkpoint = await engine.store.get_handoff_checkpoint(attempts[0].attempt_id)
    assert checkpoint.diff_artifact_ids and checkpoint.check_artifact_ids
    assert checkpoint.git_sha == first.patch_commit_sha


@pytest.mark.asyncio
async def test_coordinator_cancellation_kills_real_worker_and_requires_reconciliation(profiles, tmp_path):
    engine, plan = await setup(profiles, tmp_path, jobs=[
        {'path': 'src/output.txt', 'content': 'late', 'delay': 20, 'log': str(tmp_path / 'worker-started.jsonl')}])
    future = asyncio.create_task(engine.execute(plan, principal_id='operator'))
    for _ in range(300):
        if (tmp_path / 'worker-started.jsonl').exists():
            break
        await asyncio.sleep(0.05)
    assert (tmp_path / 'worker-started.jsonl').exists()
    entries = tuple(engine.runs.worker_runner._active_attempts.values())
    assert len(entries) == 1
    process = entries[0].process
    future.cancel()
    with pytest.raises(asyncio.CancelledError):
        await future
    assert process.returncode is not None
    assert not engine.runs.worker_runner._active_attempts
    with pytest.raises(ContractViolation, match='reconciliation'):
        await engine.execute(plan, principal_id='operator')
