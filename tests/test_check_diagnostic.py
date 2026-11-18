"""Failure evidence survives timeout and remains safe to include in a chat."""
import sys

import pytest

from hydra_orch.core.run_service import CheckRunner
from hydra_orch.model import CheckSpec


@pytest.mark.asyncio
async def test_timeout_retains_flushed_output_and_redacts_excerpt(tmp_path):
    runner = CheckRunner(tmp_path)
    progress = []
    async def checked(result, artifacts):
        progress.append((result.exit_code, len(artifacts)))
    results, artifacts = await runner.run_checks(
        run_id='run-diagnostic', attempt_id=None, workspace_path=tmp_path,
        tested_sha='a'*40, scope_prefix='checkup', timeout_seconds=2, on_check=checked,
        checks=(CheckSpec(check_id='slow', command=(sys.executable, '-u', '-c',
            "import time; print('STARTED secret=do-not-share', flush=True); time.sleep(30)")),))
    assert results[0].exit_code == 124
    diagnostic = runner.diagnostics('run-diagnostic', 'checkup', results)[0]['output']
    assert 'STARTED' in diagnostic and 'timed out' in diagnostic
    assert 'do-not-share' not in diagnostic
    assert len(artifacts) == 2
    assert progress == [(124, 2)]
