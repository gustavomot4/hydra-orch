import pytest
from hydra_orch.model import (
    ChatMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChunk,
)


def test_chat_message_schema():
    msg = ChatMessage(role="user", content="Build a barbershop SaaS app")
    assert msg.role == "user"
    assert msg.content == "Build a barbershop SaaS app"


def test_chat_completion_request_modes():
    req = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Hello")],
        mode="swarm",
    )
    assert req.mode == "swarm"
    assert req.stream is False
