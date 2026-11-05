"""Bridge package connecting hydra-orch to transport layers (OmniRoute, SSH, Workers, CDP)."""

from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.bridge.ssh_tunnel import SshTunnelManager
from hydra_orch.bridge.worker_runner import WorkerRunner
from hydra_orch.bridge.cdp_fallback import CdpFallbackBridge

__all__ = [
    "OmniRouteClient",
    "SshTunnelManager",
    "WorkerRunner",
    "CdpFallbackBridge",
]
