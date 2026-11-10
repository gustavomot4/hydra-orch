"""T16 eligibility, direct mode, uncertain quota and reproducible route audit."""

from datetime import datetime, timezone
import json

import httpx
import pytest
import pytest_asyncio

from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.core.agent_registry import AgentDefinition, DriverCertificationReport
from hydra_orch.core.metrics import MetricsService, MetricSample
from hydra_orch.core.route_selector import RouteCandidate, RouteSelector
from hydra_orch.model import ContractViolation, ExecutorCapability as Capability, ProcessStatus, TaskAttempt
from test_profile import profiles


class Gateway:
    def __init__(self,available=True,quota=None):
        self.available=available
        self.quota=quota or {'status':'unknown'}
        self.calls=0
    async def is_available(self):
        self.calls+=1
        return self.available
    async def get_quota_status(self):
        self.calls+=1
        return self.quota


@pytest_asyncio.fixture
async def routes(profiles):
    service,profile,repository,run=profiles
    metrics=MetricsService(service.store)
    selector=RouteSelector(service.store,service.agents,metrics)
    direct=RouteCandidate(route_id='direct',agent_id=profile.agent_ref,model_ref=profile.model_ref)
    return selector,direct,run,service


@pytest.mark.asyncio
async def test_direct_mode_has_no_gateway_calls_and_audit_survives_restart(routes):
    selector,direct,run,service=routes
    gateway=Gateway()
    selector.gateway=gateway
    decision=await selector.select(run.run_id,(direct,))
    assert decision.selected_route=='direct' and decision.execution_driver=='codex'
    assert gateway.calls==0
    restarted=RouteSelector(service.store,service.agents,MetricsService(service.store))
    rows=await restarted.list_decisions(run.run_id)
    assert rows[0]['id']==decision.decision_id
    candidate=json.loads(rows[0]['candidates_json'])[0]
    assert candidate['eligible'] and candidate['cost_status']=='unknown' and candidate['observed_cost'] is None
    assert (await service.store.get_events(run.run_id))[-1].event_type=='route.selected'


@pytest.mark.asyncio
async def test_fallback_gateway_offline_quota_zero_unknown_and_required(routes):
    selector,direct,run,service=routes
    gateway_route=RouteCandidate.model_validate({**direct.model_dump(mode='json'),'route_id':'gateway','mode':'gateway','priority':0,'quota_key':'claude_pro'})
    selector.connection_mode='optional'
    selector.gateway=Gateway(available=False)
    assert (await selector.select(run.run_id,(gateway_route,direct))).selected_route=='direct'
    selector.gateway=Gateway(quota={'claude_pro':{'status':'observed','remaining_percent':0}})
    decision=await selector.select(run.run_id,(gateway_route,direct))
    assert json.loads(decision.candidates_json)[0]['reason']=='quota_exhausted'
    selector.gateway=Gateway(quota={'status':'unknown'})
    assert (await selector.select(run.run_id,(gateway_route,direct))).selected_route=='gateway'
    assert (await selector.select(run.run_id,(gateway_route,direct),unknown_quota='reject')).selected_route=='direct'
    selector.connection_mode='required'
    selector.gateway=Gateway(available=False)
    with pytest.raises(ContractViolation) as error:
        await selector.select(run.run_id,(direct,gateway_route))
    assert error.value.code=='gateway_required_unavailable'
    assert (await service.store.get_events(run.run_id))[-1].event_type=='route.rejected'
    selector.gateway=Gateway(quota={'claude_pro':{'status':'observed','remaining_percent':50}})
    assert (await selector.select(run.run_id,(direct,gateway_route))).selected_route=='gateway'


@pytest.mark.asyncio
async def test_ineligible_certificates_capabilities_and_disabled_candidates(routes):
    selector,direct,run,service=routes
    disabled=RouteCandidate.model_validate({**direct.model_dump(mode='json'),'route_id':'disabled','enabled':False})
    unknown=RouteCandidate.model_validate({**direct.model_dump(mode='json'),'route_id':'unknown','agent_id':'missing'})
    decision=await selector.select(run.run_id,(disabled,unknown,direct))
    audit={c['route_id']:c for c in json.loads(decision.candidates_json)}
    assert audit['disabled']['reason']=='disabled' and audit['unknown']['reason']=='resource_not_found'
    with pytest.raises(ContractViolation,match='No route'):
        await selector.select(run.run_id,(direct,),required_capabilities=(Capability.NETWORK_ISOLATION,))
    await service.agents.revoke_certification(direct.agent_id,__import__('platform').system(),principal_id='operator')
    with pytest.raises(ContractViolation,match='No route'):
        await selector.select(run.run_id,(direct,))


@pytest.mark.asyncio
async def test_observed_telemetry_ranks_routes_without_treating_unknown_as_zero(routes):
    selector,direct,run,service=routes
    now=datetime.now(timezone.utc)
    attempt=TaskAttempt(attempt_id='telemetry-attempt',task_id=run.tasks[0].task_id,run_id=run.run_id,ordinal=1,
        executor_id='codex',provider='fixture',model=direct.model_ref,base_sha=run.base_sha,process_status=ProcessStatus.QUEUED)
    await service.store.save_attempt_atomic(attempt)
    await selector.metrics.record_usage(run.run_id,attempt.attempt_id,source='provider:fixture',observed_at=now,tokens_in=3,cost_usd=1)
    measured=RouteCandidate.model_validate({**direct.model_dump(mode='json'),'route_id':'measured','telemetry_attempt_id':attempt.attempt_id})
    unknown=RouteCandidate.model_validate({**direct.model_dump(mode='json'),'route_id':'a-unknown'})
    decision=await selector.select(run.run_id,(unknown,measured))
    assert decision.selected_route=='measured' and decision.fallback_chain==('a-unknown',)
    assert json.loads(decision.candidates_json)[1]['observed_cost']==1
    unrelated=RouteCandidate.model_validate({**measured.model_dump(mode='json'),'route_id':'unrelated','model_ref':'other-model'})
    decision=await selector.select(run.run_id,(unrelated,unknown))
    assert json.loads(decision.candidates_json)[0]['telemetry_reason']=='uncorrelated_attempt'
    await selector.metrics.record_usage(run.run_id,attempt.attempt_id,source='not_reported',observed_at=now)
    await selector.metrics.record_batch((MetricSample(run_id=run.run_id,scope='attempt',scope_id=attempt.attempt_id,
        kind='duration',value=4,unit='seconds',source='local_calc:fixture',status='observed',observed_at=now),))
    decision=await selector.select(run.run_id,(unknown,measured))
    assert decision.selected_route=='measured'
    assert json.loads(decision.candidates_json)[1]['observed_duration']==4


@pytest.mark.asyncio
async def test_invalid_candidates_and_missing_run(routes):
    selector,direct,run,service=routes
    for candidates in [(),(direct,direct)]:
        with pytest.raises(ContractViolation):
            await selector.select(run.run_id,candidates)
    with pytest.raises(ContractViolation):
        await selector.select('missing',(direct,))
    with pytest.raises(ContractViolation):
        await selector.list_decisions('missing')


@pytest.mark.asyncio
async def test_gateway_quota_normalization_offline_cache_and_disabled(monkeypatch):
    actual_client=httpx.AsyncClient
    mode={'payload':{'claude_pro':{'remaining_percent':37,'resets_in_seconds':60}},'online':True}
    def handler(request):
        if not mode['online']:
            raise httpx.ConnectError('offline')
        return httpx.Response(200,json=mode['payload'])
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:actual_client(transport=httpx.MockTransport(handler),**kwargs))
    gateway=OmniRouteClient()
    observed=await gateway.get_quota_status()
    assert observed['claude_pro']['status']=='observed' and observed['claude_pro']['remaining_percent']==37
    mode['online']=False
    stale=await gateway.get_quota_status()
    assert stale['claude_pro']['status']=='stale' and stale['claude_pro']['remaining_percent']==37
    assert stale['claude_pro']['resets_in_seconds'] is None
    disabled=OmniRouteClient(enabled=False)
    assert (await disabled.get_quota_status())['claude_pro']['remaining_percent'] is None
    with pytest.raises(ConnectionError,match='disabled'):
        await anext(disabled.stream_chat_completion('model',[]))
    mode['online']=True
    mode['payload']={'claude_pro':{'remaining_percent':500},'chatgpt_plus':{'remaining_percent':True}}
    assert (await OmniRouteClient().get_quota_status())['status']=='unknown'


@pytest.mark.asyncio
async def test_authenticated_route_audit_endpoint(routes,monkeypatch):
    from fastapi.testclient import TestClient
    from hydra_orch import server
    from hydra_orch.core.auth import TokenVerifier
    from hydra_orch.core.run_service import RunService
    selector,direct,run,service=routes
    decision=await selector.select(run.run_id,(direct,))
    monkeypatch.setattr(server,'_run_service',RunService(repo_root=run.repo_root,store=selector.store))
    token='route-audit-token-0123456789abcdef'
    monkeypatch.setitem(server.app.state._state,'token_verifier',TokenVerifier.from_token(token))
    client=TestClient(server.app,headers={'Authorization':'Bearer '+token})
    path=f'/v1/control-plane/runs/{run.run_id}/route-decisions'
    assert client.get(path).json()[0]['id']==decision.decision_id
    assert TestClient(server.app).get(path).status_code==401
