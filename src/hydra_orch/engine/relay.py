"""Mode 2: Relay Sequential Pipeline with instant hot-swap failover."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional
from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.engine.checkpointer import EngineCheckpointer, stitch_code_blocks
from hydra_orch.model import ChatMessage

logger = logging.getLogger(__name__)


class RelayPipelineEngine:
    """Manages sequential step-by-step pipeline with instant hot-swap on token exhaustion."""

    def __init__(
        self,
        omniroute_client: Optional[OmniRouteClient] = None,
        checkpointer: Optional[EngineCheckpointer] = None,
    ):
        self.omniroute = omniroute_client or OmniRouteClient()
        self.checkpointer = checkpointer or EngineCheckpointer()

    async def execute_relay(
        self,
        task_prompt: str,
        sequence: Optional[List[Dict[str, str]]] = None,
        session_id: str = "relay-session",
    ) -> AsyncIterator[str]:
        stages = sequence or [
            {"stage": "contract_and_plan", "model": "architect_heavy"},
            {"stage": "implementation", "model": "fullstack_coder"},
            {"stage": "unit_and_integration_tests", "model": "database_and_tests"},
            {"stage": "documentation", "model": "context_and_docs"},
        ]

        yield f"--- [HYDRA RELAY PIPELINE: {len(stages)} Stages] ---\n\n"
        context_so_far = ""

        for idx, step in enumerate(stages, 1):
            stage_name = step.get("stage", f"stage_{idx}")
            model = step.get("model", "architect_heavy")

            yield f"### Stage {idx}/{len(stages)}: {stage_name.upper()} (Model: `{model}`)\n"

            prompt_for_stage = (
                f"Task: {task_prompt}\n\n"
                f"Current Pipeline Stage: {stage_name}\n"
            )
            if context_so_far:
                prompt_for_stage += f"\nPrevious Stage Output:\n```\n{context_so_far[-1500:]}\n```\n"

            messages = [ChatMessage(role="user", content=prompt_for_stage)]
            stage_output = ""

            try:
                async for chunk in self.omniroute.stream_chat_completion(model=model, messages=messages):
                    stage_output += chunk
                    yield chunk

                context_so_far += f"\n\n--- Stage {stage_name} Output ---\n{stage_output}"
                yield "\n\n"

            except Exception as e:
                logger.warning(f"Relay stage {stage_name} hit exception ({e}). Initiating hot-swap...")
                yield f"\n[Hot-Swap Triggered for {stage_name}: switching to fallback]\n"

                # Hot-swap fallback to next available model
                fallback_model = "database_and_tests"
                anchor = "\n".join(stage_output.splitlines()[-15:]) if stage_output else ""
                resume_prompt = self.checkpointer.build_resume_prompt(anchor)

                fallback_messages = [ChatMessage(role="user", content=resume_prompt)]
                fallback_output = ""
                async for chunk in self.omniroute.stream_chat_completion(
                    model=fallback_model, messages=fallback_messages
                ):
                    fallback_output += chunk
                    yield chunk

                stitched = stitch_code_blocks(stage_output, fallback_output)
                context_so_far += f"\n\n--- Stage {stage_name} Output (Stitched) ---\n{stitched}\n\n"

        yield "\n--- [HYDRA RELAY PIPELINE COMPLETED] ---\n"
