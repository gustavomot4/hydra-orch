"""Two-wave execution from an explicit immutable plan."""

from hydra_orch.model import ContractViolation


class MultiSessionSwarmEngine:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    async def execute_swarm(self, plan, **kwargs):
        if plan.run.orchestration_mode != 'swarm':
            raise ContractViolation('mode_mismatch', 'Swarm requires a two-wave plan')
        return await self.orchestrator.execute(plan, **kwargs)
