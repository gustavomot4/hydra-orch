"""Persistent sequential execution with bounded availability waits."""

from hydra_orch.model import ContractViolation


class PersistentEngine:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    async def execute_persistent(self, plan, **kwargs):
        if plan.run.orchestration_mode != 'persistent':
            raise ContractViolation('mode_mismatch', 'Persistent mode requires a matching plan')
        return await self.orchestrator.execute(plan, **kwargs)
