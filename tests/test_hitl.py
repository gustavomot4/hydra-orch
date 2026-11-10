"""T26 durable, idempotent human intervention with dispatch admission barriers."""

import asyncio
from datetime import datetime, timedelta
import sys

from fastapi.testclient import TestClient
import pytest
import pytest_asyncio

from hydra_orch import server
from hydra_orch.core.auth import TokenVerifier
from hydra_orch.core.checkpointer import ExecutionStore, IdempotencyConflictError, OptimisticLockError
from hydra_orch.core.hitl import HITLService
from hydra_orch.core.run_service import RunService
from hydra_orch.model import CheckSpec, ContractViolation, ProcessStatus, RunSpec, RunStatus, TaskAttempt, TaskSpec, TaskStatus
from test_server import _init_temp_git_repo


@pytest_asyncio.fixture
async def hitl(tmp_path, monkeypatch):
    repo, sha = _init_temp_git_repo(tmp_path)
    store=ExecutionStore(tmp_path/'hitl.sqlite')
    runs=RunService(repo_root=repo,store=store)
    for run_id in ('run-a','run-b'):
        task=TaskSpec(task_id=f'{run_id}-task',run_id=run_id,objective='Apply operator context',assigned_executor='codex',
            allowed_paths=('src/**',),acceptance_criteria=(CheckSpec(check_id='ok',command=(sys.executable,'-c','print("OK")')),))
        spec=RunSpec(run_id=run_id,project_id='project',objective='Test intervention',repo_root=str(repo),base_sha=sha,
            base_branch='main',idempotency_key=f'hitl-run-key-000000-{run_id}',tasks=(task,))
        await runs.submit_run(spec)
    monkeypatch.setattr(server,'_run_service',runs)
    token='hitl-test-token-0123456789abcdef'
    monkeypatch.setitem(server.app.state._state,'token_verifier',TokenVerifier.from_token(token))
    return HITLService(store),runs,repo,token


async def request(service, *, kind='needs_context', timeout=300):
    return await service.request('run-a',kind,'Which value should be used?',task_id='run-a-task',
        timeout_seconds=timeout,idempotency_key='hitl-request-key-00001')


@pytest.mark.asyncio
async def test_pending_blocks_dispatch_and_reply_does_not_execute_twice(hitl):
    service,runs,repo,_=hitl
    snapshot=runs.git_workspace.snapshot_operator_checkout()
    pending=await request(service)
    assert (await runs.store.get_run('run-a'))['status']=='waiting'
    with pytest.raises(ContractViolation) as blocked:
        await runs.execute_task_attempt('run-a','run-a-task',custom_command=(sys.executable,'-c','raise RuntimeError("must not execute")'))
    assert blocked.value.code=='hitl_pending'
    assert await runs.store.list_attempts('run-a-task')==[]
    assert pending==await request(service)
    answered=await service.respond('run-a',pending.request_id,'Use the approved value',actor='operator',
        expected_revision=1,idempotency_key='hitl-answer-key-00001')
    repeated=await service.respond('run-a',pending.request_id,'Use the approved value',actor='operator',
        expected_revision=1,idempotency_key='hitl-answer-key-00001')
    assert answered==repeated and answered.state=='answered'
    assert await runs.store.list_attempts('run-a-task')==[]
    outcome=await runs.execute_task_attempt('run-a','run-a-task',custom_command=(sys.executable,'-c',
        "import pathlib,sys; pathlib.Path('src/answer.txt').write_text(sys.stdin.read(),encoding='utf-8')"))
    assert outcome.result.task_status==TaskStatus.READY_FOR_REVIEW
    assert 'Use the approved value' in (outcome.workspace.canonical_path/'src/answer.txt').read_text()
    assert len(await runs.store.list_attempts('run-a-task'))==1
    assert sum(e.event_type=='run.resumed' for e in await runs.store.get_events('run-a'))==1
    runs.git_workspace.assert_operator_checkout_intact(snapshot)


@pytest.mark.asyncio
async def test_atomic_store_admission_guards(hitl):
    service,runs,_,_=hitl
    pending=await request(service,kind='needs_approval')
    run=await runs.store.get_run('run-a')
    task=await runs.store.get_task('run-a-task')
    with pytest.raises(ContractViolation,match='before dispatch'):
        await runs.store.update_run_status_atomic('run-a',RunStatus.RUNNING,run['revision'],'run.resumed')
    with pytest.raises(ContractViolation,match='before dispatch'):
        await runs.store.update_task_status_atomic('run-a-task',TaskStatus.RUNNING,task['revision'],'task.started')
    attempt=TaskAttempt(attempt_id='blocked-attempt',run_id='run-a',task_id='run-a-task',ordinal=1,
        executor_id='codex',provider='fixture',model='fixture',base_sha=run['spec'].base_sha,process_status=ProcessStatus.QUEUED)
    with pytest.raises(ContractViolation,match='before dispatch'):
        await runs.store.save_attempt_atomic(attempt)
    with pytest.raises(ContractViolation):
        await runs.integrate_run('run-a')
    assert (await service.get_request('run-a',pending.request_id)).state=='pending'


@pytest.mark.asyncio
async def test_restart_expiration_fails_and_preserves_evidence(hitl):
    service,runs,_,_=hitl
    pending=await request(service,timeout=1)
    restarted=HITLService(ExecutionStore(runs.store.db_path))
    expired=await restarted.expire_due(now=pending.deadline+timedelta(seconds=1))
    assert expired[0].state=='expired'
    assert (await runs.store.get_run('run-a'))['status']=='failed'
    assert (await runs.store.get_task('run-a-task'))['status']=='failed'
    assert (await restarted.get_request('run-a',pending.request_id)).state=='expired'
    assert await restarted.expire_due(now=pending.deadline+timedelta(seconds=2))==()
    assert any(e.redacted_payload.get('reason')=='hitl_timeout' for e in await runs.store.get_events('run-a'))
    with pytest.raises(OptimisticLockError):
        await restarted.respond('run-a',pending.request_id,'late',actor='operator',expected_revision=1,
            idempotency_key='hitl-late-key-0000001')


@pytest.mark.asyncio
async def test_denial_cancellation_and_cross_run_scope(hitl):
    service,runs,_,_=hitl
    pending=await request(service,kind='needs_approval')
    with pytest.raises(ContractViolation,match='another run'):
        await service.get_request('run-b',pending.request_id)
    denied=await service.respond('run-a',pending.request_id,'Not approved',actor='operator',expected_revision=1,
        idempotency_key='hitl-deny-key-0000001',approved=False)
    assert denied.state=='denied' and (await runs.store.get_run('run-a'))['status']=='failed'
    other=await service.request('run-b','needs_context','Question',idempotency_key='hitl-request-run-b-001')
    await runs.cancel_run('run-b',reason='operator cancelled')
    assert (await service.get_request('run-b',other.request_id)).state=='cancelled'
    assert (await runs.store.get_run('run-b'))['status']=='cancelled'


@pytest.mark.asyncio
async def test_busy_attempt_and_payload_conflicts(hitl):
    service,runs,_,_=hitl
    task=await runs.store.get_task('run-b-task')
    await runs.store.update_task_status_atomic('run-b-task',TaskStatus.RUNNING,task['revision'],'task.started')
    with pytest.raises(ContractViolation,match='Running attempts'):
        await service.request('run-b','needs_context','question',idempotency_key='busy-request-key-00001')
    pending=await request(service)
    with pytest.raises(IdempotencyConflictError):
        await service.request('run-a','needs_context','different',task_id='run-a-task',idempotency_key='hitl-request-key-00001')
    await service.respond('run-a',pending.request_id,'answer',actor='operator',expected_revision=1,idempotency_key='response-key-00000001')
    with pytest.raises(IdempotencyConflictError):
        await service.respond('run-a',pending.request_id,'different',actor='operator',expected_revision=1,idempotency_key='response-key-00000001')


@pytest.mark.asyncio
async def test_expiration_reply_race_has_one_terminal_decision(hitl):
    service,runs,_,_=hitl
    pending=await request(service)
    await asyncio.gather(service.respond('run-a',pending.request_id,'answer',actor='operator',expected_revision=1,
        idempotency_key='racing-answer-key-0001'),service.expire_due(now=pending.deadline+timedelta(seconds=1)),return_exceptions=True)
    state=(await service.get_request('run-a',pending.request_id)).state
    assert state in {'answered','expired'}
    assert sum(e.event_type=='hitl.resolved' for e in await runs.store.get_events('run-a'))==1


@pytest.mark.asyncio
async def test_request_transaction_rolls_back_on_event_failure(hitl,monkeypatch):
    service,runs,_,_=hitl
    async def fail(*args,**kwargs):
        raise RuntimeError('event unavailable')
    monkeypatch.setattr(runs.store,'_insert_event_in_tx',fail)
    with pytest.raises(RuntimeError):
        await request(service)
    assert (await runs.store.get_run('run-a'))['status']=='queued'
    assert (await runs.store.get_task('run-a-task'))['status']=='pending'
    assert await service.list_requests('run-a')==()


@pytest.mark.asyncio
async def test_http_auth_and_human_response(hitl):
    service,runs,_,token=hitl
    client=TestClient(server.app,headers={'Authorization':'Bearer '+token})
    base='/v1/control-plane/runs/run-a/interventions'
    body={'kind':'needs_context','question':'Question','task_id':'run-a-task'}
    response=client.post(base,json=body,headers={'Idempotency-Key':'http-hitl-request-0001'})
    assert response.status_code==201
    request_id=response.json()['request_id']
    assert client.get(base).json()[0]['request_id']==request_id
    assert client.get(base+'/'+request_id).status_code==200
    assert client.get('/v1/control-plane/runs/run-b/interventions/'+request_id).status_code==403
    assert TestClient(server.app).get(base).status_code==401
    answer={'response':'Use this value','actor':'operator','expected_revision':1,'approved':True}
    assert client.post(base+'/'+request_id+'/response',json=answer,headers={'Idempotency-Key':'http-hitl-response-001'}).status_code==200
    assert (await runs.store.get_run('run-a'))['status']=='running'


@pytest.mark.asyncio
async def test_server_deadline_reconciler_stops_at_shutdown(hitl,monkeypatch):
    service,runs,_,_=hitl
    pending=await request(service,timeout=1)
    async def startup():
        pass
    monkeypatch.setattr(server,'startup_event',startup)
    async with server._lifespan(server.app):
        async def wait_expired():
            while (await runs.store.get_run('run-a'))['status']!='failed':
                await asyncio.sleep(.05)
        await asyncio.wait_for(wait_expired(),3)
    assert not any(t.get_name()=='hydra-hitl-deadlines' for t in asyncio.all_tasks())
    assert (await service.get_request('run-a',pending.request_id)).state=='expired'


@pytest.mark.asyncio
async def test_invalid_requests_scope_and_stale_decisions(hitl):
    service,runs,_,_=hitl
    with pytest.raises(ContractViolation):
        await service.request('run-a','needs_context',' ',idempotency_key='invalid-request-key-001')
    with pytest.raises(ContractViolation):
        await service.request('missing','needs_context','Question',idempotency_key='missing-request-key-001')
    with pytest.raises(ContractViolation):
        await service.get_request('run-a','missing')
    with pytest.raises(ContractViolation):
        await service.request('run-a','needs_context','Question',task_id='run-b-task',idempotency_key='wrong-task-key-000001')
    pending=await request(service)
    with pytest.raises(ContractViolation):
        await service.request('run-a','needs_context','Another question',idempotency_key='another-question-key-001')
    with pytest.raises(ContractViolation):
        await service.respond('run-a',pending.request_id,'answer',actor=' ',expected_revision=1,idempotency_key='invalid-actor-key-001')
    with pytest.raises(OptimisticLockError):
        await service.respond('run-a',pending.request_id,'answer',actor='operator',expected_revision=9,idempotency_key='wrong-revision-key-001')
    await service.respond('run-a',pending.request_id,'no',actor='operator',expected_revision=1,
        idempotency_key='valid-denial-key-0001',approved=False)
    with pytest.raises(ContractViolation):
        await service.respond('run-a',pending.request_id,'answer',actor='operator',expected_revision=2,idempotency_key='late-second-key-0001')
    with pytest.raises(ContractViolation):
        await service.request('run-a','needs_context','Question',idempotency_key='closed-run-key-000001')
    with pytest.raises(ContractViolation):
        await service.expire_due(now=datetime.now())


@pytest.mark.asyncio
async def test_question_and_answer_secrets_are_not_persisted(hitl):
    service,runs,_,_=hitl
    pending=await service.request('run-a','needs_context','password=never-store-question',
        idempotency_key='redacted-question-key-001')
    answered=await service.respond('run-a',pending.request_id,'secret=never-store-answer',actor='api_key=never-store-actor',
        expected_revision=1,idempotency_key='redacted-answer-key-0001')
    assert 'never-store' not in answered.model_dump_json()
    assert 'never-store' not in str(await service.context_for_task('run-a','run-a-task'))
    assert 'never-store' not in ''.join(e.model_dump_json() for e in await runs.store.get_events('run-a'))
