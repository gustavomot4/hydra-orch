"""T16/T29 eligibility, direct mode, uncertain quota, OmniRoute inventory, and next-run account overrides."""

from datetime import datetime, timezone
import json

import httpx
import pytest
import pytest_asyncio

from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.core.agent_registry import AgentDefinition, AgentRegistry, DriverCertificationReport
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.metrics import MetricsService, MetricSample
from hydra_orch.core.route_selector import AccountOverride, RouteCandidate, RouteDecision, RouteSelector
from hydra_orch.model import ChatMessage, ContractViolation, ExecutorCapability as Capability, ProcessStatus, RunSpec, TaskAttempt
from test_checkpointer import _make_run_spec
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


@pytest.mark.asyncio
async def test_omniroute_client_list_models_online_disabled_and_connection_refused():
    calls = []
    state = {"mode": "online"}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if state["mode"] == "refused":
            raise httpx.ConnectError("connection refused", request=request)
        if state["mode"] == "error":
            return httpx.Response(503, json={"error": "gateway down"})
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"id": "agy/gemini-4-argon-high", "owned_by": "google"},
                        {"id": "claude-3-7-sonnet", "provider": "claude_pro", "owned_by": "anthropic"},
                        {"id": "claude-3-7-sonnet", "provider": "claude_pro", "owned_by": "anthropic"},
                        {"id": "", "owned_by": "invalid"},
                    ],
                },
            )
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                200,
                content=b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = OmniRouteClient(transport=transport)

    assert await client.is_available() is True
    listed = await client.list_models()
    assert listed["status"] == "available"
    assert listed["source"] == "omniroute:models_api"
    assert listed["models"] == [
        {"id": "agy/gemini-4-argon-high", "provider": "agy", "owned_by": "google"},
        {"id": "claude-3-7-sonnet", "provider": "claude_pro", "owned_by": "anthropic"},
    ]

    streamed = [chunk async for chunk in client.stream_chat_completion("gemini-4-argon", [ChatMessage(role="user", content="hi")])]
    assert streamed == ["ok"]

    state["mode"] = "error"
    err_res = await client.list_models()
    assert err_res["status"] == "unavailable"
    assert err_res["models"] == []

    state["mode"] = "refused"
    assert await client.is_available() is False
    refused_res = await client.list_models()
    assert refused_res["status"] == "unavailable"
    assert refused_res["models"] == []

    before_disabled_calls = len(calls)
    disabled = OmniRouteClient(enabled=False, transport=transport)
    disabled_res = await disabled.list_models()
    assert disabled_res == {"status": "unavailable", "source": "omniroute:disabled", "models": []}
    assert len(calls) == before_disabled_calls


@pytest.mark.asyncio
async def test_omniroute_client_list_accounts_online_redaction_fallback_disabled_and_refused():
    calls = []
    state = {"accounts_mode": "online", "quota_mode": "online"}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/v1/accounts":
            if state["accounts_mode"] == "refused":
                raise httpx.ConnectError("connection refused", request=request)
            if state["accounts_mode"] == "missing":
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(
                200,
                json={
                    "accounts": [
                        {
                            "id": "acct-claude-work",
                            "provider": "claude_pro",
                            "label": "Work Bearer secret-bearer-999",
                            "quota_key": "claude_pro",
                            "access_token": "sk-ant-secret-token-12345678",
                            "refresh_token": "rt-super-secret-value",
                            "api_key": "api-key-secret",
                            "password": "pw-secret",
                            "secret": "top-secret",
                            "token": "tok-secret",
                        },
                        {
                            "id": "acct-openai-backup",
                            "provider": "openai",
                            "label": "OpenAI Backup",
                            "access_token": "sk-openai-secret-987654321",
                        },
                    ]
                },
            )
        if request.url.path == "/api/usage/quota":
            if state["quota_mode"] == "refused":
                raise httpx.ConnectError("connection refused", request=request)
            return httpx.Response(
                200,
                json={
                    "claude_pro": {"remaining_percent": 62.5, "resets_in_seconds": 420},
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = OmniRouteClient(transport=transport)

    online = await client.list_accounts()
    serialized = json.dumps(online)
    for forbidden in (
        "sk-ant-secret-token-12345678",
        "rt-super-secret-value",
        "api-key-secret",
        "pw-secret",
        "top-secret",
        "tok-secret",
        "sk-openai-secret-987654321",
        "secret-bearer-999",
        "access_token",
        "refresh_token",
        "api_key",
        "password",
    ):
        assert forbidden not in serialized

    assert online["status"] == "observed"
    by_id = {item["account_id"]: item for item in online["accounts"]}
    assert set(by_id) == {"acct-claude-work", "acct-openai-backup"}
    assert by_id["acct-claude-work"]["status"] == "observed"
    assert by_id["acct-claude-work"]["remaining_percent"] == 62.5
    assert by_id["acct-claude-work"]["resets_in_seconds"] == 420
    assert by_id["acct-claude-work"]["observed_at"] is not None
    assert "Bearer [REDACTED]" in by_id["acct-claude-work"]["label"]
    # Absent quota for acct-openai-backup must remain unknown/None, never 0 or 100
    assert by_id["acct-openai-backup"]["status"] == "unknown"
    assert by_id["acct-openai-backup"]["remaining_percent"] is None
    assert by_id["acct-openai-backup"]["resets_in_seconds"] is None

    # Fallback to quota API when /v1/accounts returns 404
    state["accounts_mode"] = "missing"
    fallback = await client.list_accounts()
    assert fallback["status"] == "observed"
    assert fallback["source"] == "omniroute:quota_api"
    assert fallback["accounts"][0]["account_id"] == "claude_pro"
    assert fallback["accounts"][0]["remaining_percent"] == 62.5

    # Fresh client with connection refused on both endpoints -> unknown & empty, never 0 or 100
    state["accounts_mode"] = "refused"
    state["quota_mode"] = "refused"
    fresh_offline = OmniRouteClient(transport=transport)
    refused = await fresh_offline.list_accounts()
    assert refused["status"] == "unknown"
    assert refused["accounts"] == []

    # Disabled client -> zero network calls, status unknown
    before_disabled_calls = len(calls)
    disabled = OmniRouteClient(enabled=False, transport=transport)
    disabled_res = await disabled.list_accounts()
    assert disabled_res == {"status": "unknown", "source": "omniroute:disabled", "accounts": []}
    assert len(calls) == before_disabled_calls


@pytest.mark.asyncio
async def test_route_selector_gateway_inventory_disabled_optional_required_and_online(routes):
    selector, _, _, _ = routes
    calls = []
    state = {"mode": "refused"}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if state["mode"] == "refused":
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "claude_pro/claude-3-7-sonnet", "owned_by": "anthropic"}]})
        if request.url.path == "/v1/accounts":
            return httpx.Response(200, json={"accounts": [{"id": "acct-1", "provider": "claude_pro", "access_token": "sk-secret-value-123456"}]})
        if request.url.path == "/api/usage/quota":
            return httpx.Response(200, json={"claude_pro": {"remaining_percent": 77, "resets_in_seconds": 300}})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    # disabled mode with configured gateway must make ZERO network calls
    selector.connection_mode = "disabled"
    selector.gateway = OmniRouteClient(enabled=True, transport=transport)
    inv_disabled = await selector.gateway_inventory()
    assert len(calls) == 0
    assert inv_disabled["connection_mode"] == "disabled"
    assert inv_disabled["direct_mode_supported"] is True
    assert inv_disabled["available"] is False
    assert inv_disabled["models"] == []
    assert inv_disabled["accounts"] == []
    assert inv_disabled["quota"]["status"] == "unknown"
    assert inv_disabled["quota"]["claude_pro"]["remaining_percent"] is None

    # gateway=None in optional mode makes zero network calls
    selector.connection_mode = "optional"
    selector.gateway = None
    inv_none = await selector.gateway_inventory()
    assert len(calls) == 0
    assert inv_none["available"] is False
    assert inv_none["quota"]["status"] == "unknown"

    # optional & required modes offline cleanly report unavailable + unknown quota
    selector.gateway = OmniRouteClient(enabled=True, transport=transport)
    for mode in ("optional", "required"):
        selector.connection_mode = mode
        inv_off = await selector.gateway_inventory()
        assert inv_off["connection_mode"] == mode
        assert inv_off["direct_mode_supported"] is True
        assert inv_off["available"] is False
        assert inv_off["models"] == []
        assert inv_off["accounts"] == []
        assert inv_off["quota"]["status"] == "unknown"
        assert inv_off["quota"]["claude_pro"]["remaining_percent"] is None

    # online inventory returns discovered models, redacted accounts, and observed quota
    state["mode"] = "online"
    selector.connection_mode = "optional"
    inv_on = await selector.gateway_inventory()
    assert inv_on["available"] is True
    assert inv_on["models"] == [{"id": "claude_pro/claude-3-7-sonnet", "provider": "claude_pro", "owned_by": "anthropic"}]
    assert inv_on["accounts"][0]["account_id"] == "acct-1"
    assert inv_on["accounts"][0]["remaining_percent"] == 77.0
    assert "sk-secret-value-123456" not in json.dumps(inv_on)
    assert inv_on["quota"]["status"] == "observed"


@pytest.mark.asyncio
async def test_select_next_account_persists_without_mutating_active_attempt_and_rejects_secrets(routes):
    selector, direct, run, service = routes
    now = datetime.now(timezone.utc)

    # Create an active RUNNING attempt on run_001 and an initial decision before changing next-run account
    running_attempt = TaskAttempt(
        attempt_id="running-attempt-1",
        task_id=run.tasks[0].task_id,
        run_id=run.run_id,
        ordinal=1,
        executor_id="codex",
        provider="fixture",
        model=direct.model_ref,
        base_sha=run.base_sha,
        process_status=ProcessStatus.RUNNING,
        started_at=now,
    )
    await service.store.save_attempt_atomic(running_attempt)
    initial_decision = await selector.select(run.run_id, (direct,))

    # Reject empty, secret-like, and unavailable account IDs
    for bad_account in (
        "",
        "   ",
        "sk-ant-1234567890abcdef",
        "ghp_1234567890abcdef",
        "Bearer my-secret-token",
        "access_token=secret123",
        "api_key",
    ):
        with pytest.raises(ContractViolation):
            await selector.select_next_account("default", "claude_pro", bad_account)

    with pytest.raises(ContractViolation):
        await selector.select_next_account("default", "access_token", "acct-clean-1")

    with pytest.raises(ContractViolation) as avail_err:
        await selector.select_next_account(
            "default",
            "claude_pro",
            "acct-missing",
            available_account_ids=["acct-work-1", "acct-work-2"],
        )
    assert avail_err.value.code == "account_not_available"

    # Persist default next-run account (scope_id="default" is not in runs; must not fail FK)
    saved_default = await selector.select_next_account(
        "default",
        "claude_pro",
        "acct-work-2",
        principal_id="operator",
        available_account_ids=["acct-work-1", "acct-work-2"],
    )
    parsed_override = AccountOverride.model_validate(saved_default)
    assert parsed_override.account_id == "acct-work-2"
    assert parsed_override.applies_to == "next_run"

    # Active running attempt and earlier route decision must remain completely untouched
    stored_attempt = await service.store.get_attempt(running_attempt.attempt_id)
    assert stored_attempt == running_attempt
    prior_decisions = await selector.list_decisions(run.run_id)
    assert len(prior_decisions) == 1
    assert prior_decisions[0]["id"] == initial_decision.decision_id
    assert "selected_account_id" not in json.loads(prior_decisions[0]["candidates_json"])[0]

    # Create next run and restart RouteSelector on a fresh ExecutionStore
    next_run_data = _make_run_spec(
        run.repo_root,
        run_id="run-002",
        project_id=run.project_id,
        idempotency_key="idemp-key-0002-efgh",
    ).model_dump(mode="json")
    next_run_data["base_sha"] = run.base_sha
    next_run = RunSpec.model_validate(next_run_data)
    await service.store.submit_run_idempotent(next_run)

    restarted_store = ExecutionStore(service.store.db_path)
    restarted_agents = AgentRegistry(
        restarted_store,
        certification_root=service.agents.certification_root,
        executable_locator=service.agents.locate,
    )
    restarted_selector = RouteSelector(
        restarted_store,
        restarted_agents,
        MetricsService(restarted_store),
        gateway=Gateway(available=True, quota={"claude_pro": {"status": "observed", "remaining_percent": 80}}),
        connection_mode="optional",
    )

    overrides_from_default = await restarted_selector.get_next_account_overrides(next_run.run_id)
    assert overrides_from_default["claude_pro"]["account_id"] == "acct-work-2"

    # Run-scoped override for next_run emits audit event on next_run and overrides default
    await restarted_selector.select_next_account(next_run.run_id, "claude_pro", "acct-work-3")
    next_events = await restarted_store.get_events(next_run.run_id)
    assert any(
        e.event_type == "route.selected" and e.redacted_payload.get("account_id") == "acct-work-3"
        for e in next_events
    )

    gateway_route = RouteCandidate.model_validate(
        {
            **direct.model_dump(mode="json"),
            "route_id": "gateway",
            "mode": "gateway",
            "priority": 0,
            "quota_key": "claude_pro",
        }
    )
    next_decision = await restarted_selector.select(next_run.run_id, (gateway_route, direct))
    assert isinstance(next_decision, RouteDecision)
    assert next_decision.selected_route == "gateway"
    audit_entries = {c["route_id"]: c for c in json.loads(next_decision.candidates_json)}
    assert audit_entries["gateway"]["selected_account_id"] == "acct-work-3"
    assert "selected_account_id" not in audit_entries["direct"]

    # Active attempt in run-001 is STILL untouched after next_run selection
    assert await restarted_store.get_attempt(running_attempt.attempt_id) == running_attempt

@pytest.mark.asyncio
async def test_omniroute_v3_bearer_auth_warmup_provider_limits_and_pii_redaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate real OmniRoute v3.x auth, warmup fallback, provider-limits, /api/providers, and PII scrubbing."""
    expected_token = "omni-test-bearer-secret-012345"
    monkeypatch.setenv("TEST_OMNIROUTE_KEY", expected_token)
    state = {"warmup": False, "all_503": False, "seen_auth": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["seen_auth"].append(request.headers.get("authorization"))
        if state["all_503"]:
            return httpx.Response(503, json={"error": "gateway down"})
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "version": "3.8.52"})

        if request.headers.get("authorization") != f"Bearer {expected_token}":
            return httpx.Response(401, json={"error": {"code": "AUTH_001"}})

        if request.url.path == "/v1/models":
            if state["warmup"]:
                return httpx.Response(503, json={"error": {"type": "service_unavailable"}})
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "agy/claude-opus-5-5-high", "owned_by": "agy"},
                        {"id": "codex/gpt-6-astra", "owned_by": "codex"},
                        {"id": "agy/gemini-4-argon-high", "owned_by": "agy"},
                        {"id": "auto/best-reasoning", "owned_by": "auto"},
                    ]
                },
            )
        if request.url.path == "/api/usage/quota":
            return httpx.Response(
                200,
                json={
                    "providers": [
                        {
                            "name": "alice@example.com",
                            "provider": "codex",
                            "connectionId": "conn-codex-1",
                            "quotaUsed": 0,
                            "quotaTotal": None,
                            "percentRemaining": 100,
                            "resetAt": None,
                            "tokenStatus": "valid",
                        },
                        {
                            "name": "bob@example.com",
                            "provider": "claude",
                            "connectionId": "conn-claude-exp",
                            "quotaUsed": 0,
                            "quotaTotal": None,
                            "percentRemaining": 100,
                            "resetAt": None,
                            "tokenStatus": "expired",
                        },
                        {
                            "name": "carol@example.com",
                            "provider": "opencode-go",
                            "connectionId": "conn-opencode-1",
                            "quotaUsed": 0,
                            "quotaTotal": None,
                            "percentRemaining": 100,
                            "resetAt": None,
                            "tokenStatus": "valid",
                        },
                    ],
                    "meta": {"totalProviders": 3},
                },
            )
        if request.url.path == "/api/usage/provider-limits":
            return httpx.Response(
                200,
                json={
                    "caches": {
                        "conn-codex-1": {
                            "provider": "codex",
                            "active": True,
                            "testStatus": "active",
                            "fetchedAt": "2026-11-13T18:00:00Z",
                            "quotas": {
                                "session": {
                                    "used": 3,
                                    "total": 100,
                                    "remaining": 97,
                                    "windowSeconds": 18000,
                                    "resetAt": "2099-01-01T00:00:00Z",
                                },
                                "weekly": {"used": 82, "total": 100, "remaining": 18},
                            },
                        },
                        "conn-agy-1": {
                            "provider": "agy",
                            "active": True,
                            "testStatus": "active",
                            "quotas": {
                                "gemini-4-argon-high": {"remainingPercentage": 80, "resetAt": "2099-01-01T00:00:00Z"},
                                "claude-opus-5-5-high": {"remainingPercentage": 45},
                            },
                        },
                        "conn-gh-1": {
                            "provider": "github",
                            "active": True,
                            "quotas": {
                                "premium_interactions": {"used": 200, "total": 200, "remainingPercentage": 0},
                                "chat": {"unlimited": True},
                            },
                        },
                        "conn-claude-exp": {
                            "provider": "claude",
                            "active": False,
                            "testStatus": "expired",
                            "errorCode": "invalid_grant",
                            "quotas": {"session": {"remainingPercentage": 99}},
                        },
                        "conn-opencode-1": {
                            "provider": "opencode-go",
                            "active": True,
                            "quotas": None,
                        },
                    }
                },
            )
        if request.url.path == "/v1/accounts":
            return httpx.Response(404)
        if request.url.path == "/api/providers":
            return httpx.Response(
                200,
                json={
                    "connections": [
                        {
                            "id": "conn-codex-1",
                            "provider": "codex",
                            "authType": "oauth",
                            "isActive": True,
                            "testStatus": "active",
                            "email": "alice@example.com",
                            "apiKey": "sk-secret-codex",
                            "providerSpecificData": {"refreshToken": "rt-secret"},
                        },
                        {
                            "id": "conn-claude-exp",
                            "provider": "claude",
                            "authType": "oauth",
                            "isActive": False,
                            "testStatus": "expired",
                            "email": "bob@example.com",
                        },
                        {
                            "id": "conn-gh-1",
                            "provider": "github",
                            "authType": "oauth",
                            "isActive": True,
                            "testStatus": "active",
                        },
                        {
                            "id": "conn-opencode-1",
                            "provider": "opencode-go",
                            "authType": "apikey",
                            "isActive": True,
                            "apiKey": "sk-opencode-secret",
                        },
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    unauth_client = OmniRouteClient(transport=transport, api_key_env="MISSING_OMNIROUTE_ENV")
    assert await unauth_client.is_available() is False

    client = OmniRouteClient(transport=transport, api_key_env="TEST_OMNIROUTE_KEY")
    assert await client.is_available() is True

    state["warmup"] = True
    assert await client.is_available() is True
    state["warmup"] = False

    state["all_503"] = True
    assert await client.is_available() is False
    state["all_503"] = False

    models = await client.list_models()
    assert models["status"] == "available"
    assert [m["id"] for m in models["models"]] == [
        "agy/claude-opus-5-5-high",
        "codex/gpt-6-astra",
        "agy/gemini-4-argon-high",
        "auto/best-reasoning",
    ]

    quota = await client.get_quota_status()
    assert quota["status"] == "observed"
    assert quota["chatgpt_plus"]["status"] == "observed"
    assert quota["chatgpt_plus"]["remaining_percent"] == 97.0
    assert quota["chatgpt_plus"]["resets_in_seconds"] is not None
    assert quota["gemini_pro"]["status"] == "observed"
    assert quota["gemini_pro"]["remaining_percent"] == 45.0
    assert quota["github"]["status"] == "observed"
    assert quota["github"]["remaining_percent"] == 0.0
    # Expired claude and unmeasured opencode-go must never be fabricated as 100%
    assert quota["claude_pro"]["status"] == "unknown"
    assert quota["claude_pro"]["remaining_percent"] is None
    assert "opencode-go" not in quota
    # Consolidated canonical keys prevent duplicate provider cards
    assert "codex" not in quota
    assert "agy" not in quota

    accounts = await client.list_accounts()
    assert accounts["source"] == "omniroute:providers_api"
    by_id = {acc["account_id"]: acc for acc in accounts["accounts"]}
    assert by_id["conn-codex-1"]["remaining_percent"] == 97.0
    assert by_id["conn-gh-1"]["remaining_percent"] == 0.0
    assert by_id["conn-claude-exp"]["status"] == "unknown"
    assert by_id["conn-claude-exp"]["remaining_percent"] is None
    assert by_id["conn-opencode-1"]["status"] == "unknown"
    assert by_id["conn-opencode-1"]["remaining_percent"] is None

    serialized = json.dumps({"quota": quota, "accounts": accounts})
    for forbidden in (
        "@",
        "alice@example.com",
        "bob@example.com",
        "sk-secret-codex",
        "rt-secret",
        "sk-opencode-secret",
        expected_token,
        "providerSpecificData",
    ):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_route_selector_canonical_quota_and_account_override_aliases(routes) -> None:
    selector, direct, run, _ = routes
    codex_route = RouteCandidate.model_validate(
        {
            **direct.model_dump(mode="json"),
            "route_id": "gateway-codex",
            "mode": "gateway",
            "priority": 0,
            "quota_key": "codex",
            "model_ref": "codex/gpt-6-astra",
        }
    )
    selector.connection_mode = "optional"
    selector.gateway = Gateway(
        available=True,
        quota={"status": "observed", "chatgpt_plus": {"status": "observed", "remaining_percent": 97.0}},
    )
    await selector.select_next_account("default", "codex", "acct-codex-1")
    decision = await selector.select(run.run_id, (codex_route, direct))
    assert decision.selected_route == "gateway-codex"
    audit = {c["route_id"]: c for c in json.loads(decision.candidates_json)}
    assert audit["gateway-codex"]["quota_status"] == "observed"
    assert audit["gateway-codex"]["remaining_percent"] == 97.0
    assert audit["gateway-codex"]["selected_account_id"] == "acct-codex-1"

    selector.gateway = Gateway(
        available=True,
        quota={"status": "observed", "chatgpt_plus": {"status": "observed", "remaining_percent": 0.0}},
    )
    exhausted_decision = await selector.select(run.run_id, (codex_route, direct))
    assert exhausted_decision.selected_route == "direct"
    exhausted_audit = {c["route_id"]: c for c in json.loads(exhausted_decision.candidates_json)}
    assert exhausted_audit["gateway-codex"]["reason"] == "quota_exhausted"
