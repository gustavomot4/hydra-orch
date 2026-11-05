import pytest
from hydra_orch.config import load_config
from hydra_orch.core.router import HydraRouter
from hydra_orch.core.swarm import SwarmOrchestrator
from hydra_orch.model import ChatCompletionRequest, ChatMessage


def test_swarm_prompt_decomposition():
    swarm = SwarmOrchestrator()
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
