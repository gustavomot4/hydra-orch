"""Repair uses the same worker, check and review gates as initial execution."""


class SelfHealer:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    async def heal_build_failure(self, plan, **kwargs):
        """Resume tasks within repair budgets and return an evidence-backed report.

        Failed integrations remain preserved and require an explicit repair plan.
        """
        return await self.orchestrator.execute(plan, **kwargs)
