import pytest
from hydra_orch.config import (
    HydraConfig, ProviderUnavailableError, GatewayUnavailableError, UnsupportedModeError, load_config,
)
from hydra_orch.core.router import HydraRouter
from hydra_orch.core.checkpointer import StreamCheckpointer
from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.core.swarm import SwarmOrchestrator
from hydra_orch.model import ChatCompletionRequest, ChatMessage


def test_swarm_prompt_decomposition(tmp_path):
    swarm = SwarmOrchestrator(repo_root=str(tmp_path))
    macro = "Create a full barbershop scheduling system with calendar, backend API, and Stripe payments."
    tasks = swarm.decompose_prompt(macro)
    
    assert len(tasks) == 4
    task_names = [t.name for t in tasks]
    assert "models_and_schemas" in task_names
    assert "core_backend_logic" in task_names

    contract = swarm.generate_base_contract(macro, tasks)
    assert "IMMUTABLE SWARM CONTRACT" in contract
    assert "models_and_schemas" in contract


def test_router_provider_selection():
    config = load_config()
    router = HydraRouter(config)

    # Complexity 2 should choose simple provider
    p_low = router.select_provider_for_complexity(2)
    assert p_low in router.adapters or p_low in config.orchestrator.resilience.handoff_fallback_chain

    # Complexity 9 should choose complex provider
    p_high = router.select_provider_for_complexity(9)
    assert p_high in router.adapters or p_high in config.orchestrator.resilience.handoff_fallback_chain


def local_config(**overrides):
    data = {
        "hydra": {"inference_fallback_chain": ["coder"]},
        "providers": {"remote_local": {"local": {
            "enabled": True, "base_url": "http://127.0.0.1:11434", "default_model": "direct-model",
        }}},
        "omniroute": {"logical_models": {"coder": {
            "primary": "local/alias-model", "min_difficulty": 1,
        }}},
    }
    for section, values in overrides.items():
        data[section].update(values)
    return HydraConfig.model_validate(data)


def test_only_explicitly_enabled_providers_are_instantiated():
    router = HydraRouter(local_config())
    assert list(router.adapters) == ["local"]
    assert router.config.resolve_alias("local").primary_model == "direct-model"


def test_absent_route_never_becomes_mock_or_an_arbitrary_adapter():
    router = HydraRouter(HydraConfig())
    with pytest.raises(ProviderUnavailableError):
        router.select_provider_for_complexity(5)
    with pytest.raises(ProviderUnavailableError):
        router.validate_request(ChatCompletionRequest(messages=[]))


def test_cli_target_cannot_be_used_as_an_inference_adapter():
    router = HydraRouter(local_config())
    with pytest.raises(ProviderUnavailableError):
        router.validate_request(ChatCompletionRequest(messages=[], preferred_provider="codex/model"))


def test_unverified_swarm_cannot_create_worktrees_through_chat():
    router = HydraRouter(local_config())
    with pytest.raises(UnsupportedModeError):
        router.validate_request(ChatCompletionRequest(messages=[], mode="swarm"))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["disabled", "optional"])
async def test_direct_and_optional_modes_do_not_require_gateway(monkeypatch, mode):
    async def unexpected_call(*args, **kwargs):
        pytest.fail("Gateway must not be contacted for local inference")
    monkeypatch.setattr(OmniRouteClient, "is_available", unexpected_call)
    config = local_config(omniroute={"enabled": mode != "disabled", "connection_mode": mode})
    await HydraRouter(config).ensure_gateway()


@pytest.mark.asyncio
@pytest.mark.parametrize("available", [False, True])
async def test_required_gateway_is_checked_before_generation(monkeypatch, available):
    async def availability(*args):
        return available
    monkeypatch.setattr(OmniRouteClient, "is_available", availability)
    router = HydraRouter(local_config(omniroute={"enabled": True, "connection_mode": "required"}))
    if available:
        await router.ensure_gateway()
    else:
        with pytest.raises(GatewayUnavailableError):
            await router.ensure_gateway()


@pytest.mark.asyncio
async def test_alias_model_reaches_adapter_without_gateway(monkeypatch, tmp_path):
    router = HydraRouter(local_config())
    router.checkpointer = StreamCheckpointer(str(tmp_path / "state.sqlite"))
    seen = []

    async def generate(messages, options):
        seen.append(options["model"])
        yield "local response"

    async def forbidden(*args):
        pytest.fail("Direct mode must never contact the gateway")

    monkeypatch.setattr(router.adapters["local"], "generate_stream", generate)
    monkeypatch.setattr(OmniRouteClient, "is_available", forbidden)
    result = [chunk async for chunk in router.stream_chat_completion(
        ChatCompletionRequest(messages=[ChatMessage(role="user", content="test")], session_id="direct-test"),
    )]
    assert result == ["local response"]
    assert seen == ["alias-model"]
    checkpoint = await router.checkpointer.get_checkpoint("direct-test")
    assert checkpoint["status"] == "completed"
    assert checkpoint["provider"] == "local"


@pytest.mark.parametrize("raw_model, expected", [
    ("gemini-4-argon", "agy/gemini-4-argon-high"),
    ("gemini/gemini-4-argon", "agy/gemini-4-argon-high"),
    ("antigravity/gemini-4-argon", "agy/gemini-4-argon-high"),
    ("antigravity/gemini-4-argon-high", "agy/gemini-4-argon-high"),
    ("agy/gemini-4-argon-high", "agy/gemini-4-argon-high"),
    ("gemini-4-argon-medium", "agy/gemini-4-argon-medium"),
])
def test_omniroute_client_normalizes_gemini_argon_models(raw_model, expected):
    assert OmniRouteClient.normalize_model(raw_model) == expected
