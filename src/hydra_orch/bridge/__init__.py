"""Bridge package connecting hydra-orch to transport layers (OmniRoute, SSH, Workers, CDP)."""

from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.bridge.ssh_tunnel import SshTunnelManager
from hydra_orch.bridge.worker_runner import (
    InvocationPlan,
    WorkerRunner,
    build_invocation,
    cancel_process_tree,
    filter_worker_env,
    is_process_alive,
)
from hydra_orch.bridge.cdp_fallback import CdpFallbackBridge
from hydra_orch.bridge.mcp_client import McpClient
from hydra_orch.bridge.extension_runner import (
    ExtensionAnomalyError,
    ExtensionPolicy,
    ExtensionRunner,
)

__all__ = [
    "OmniRouteClient",
    "SshTunnelManager",
    "InvocationPlan",
    "WorkerRunner",
    "build_invocation",
    "cancel_process_tree",
    "filter_worker_env",
    "is_process_alive",
    "CdpFallbackBridge",
    "McpClient",
    "ExtensionAnomalyError",
    "ExtensionPolicy",
    "ExtensionRunner",
]
