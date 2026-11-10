"""Sequential Git handoff and atomic inference-turn retry."""

import asyncio
from hydra_orch.model import ContractViolation


async def retry_atomic_turn(open_stream, *, max_attempts=2):
    """Return one complete turn, discarding interrupted generations.

    open_stream(ordinal) receives the original caller context on each attempt.
    This helper neither applies generated code nor asserts tool execution.
    """
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= 6:
        raise ValueError('Atomic turns require 1..6 attempts')
    for ordinal in range(1, max_attempts + 1):
        chunks = []
        try:
            async for chunk in open_stream(ordinal):
                chunks.append(chunk)
            return ''.join(chunks)
        except asyncio.CancelledError:
            raise
        except Exception:
            if ordinal == max_attempts:
                raise


class RelayPipelineEngine:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    async def execute_relay(self, plan, **kwargs):
        if plan.run.orchestration_mode != 'relay':
            raise ContractViolation('mode_mismatch', 'Relay requires a sequential plan')
        return await self.orchestrator.execute(plan, **kwargs)
