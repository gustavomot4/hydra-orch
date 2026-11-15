"""Windows Start menu PATH need not contain the Store app's CLI directory."""
import os
from types import SimpleNamespace

import pytest

from hydra_orch.bridge import agent_executable as locator


def test_path_resolution_preserves_explicit_installation(monkeypatch):
    monkeypatch.setattr(locator.shutil,'which',lambda command,path=None:'fixture/codex.exe')
    def unexpected(*_,**__):pytest.fail('PATH match must not query package registration')
    monkeypatch.setattr(locator.subprocess,'run',unexpected)
    assert locator.resolve_agent_executable('codex')=='fixture/codex.exe'


@pytest.mark.skipif(os.name!='nt',reason='Windows package registration')
def test_registered_codex_is_found_without_path_and_stale_cache_is_discarded(tmp_path,monkeypatch):
    monkeypatch.setattr(locator.shutil,'which',lambda *_,**__:None)
    monkeypatch.setattr(locator,'_codex_cache',None)
    root=tmp_path/'OpenAI.Codex_fixture'
    binary=root/'app/resources/codex.exe';binary.parent.mkdir(parents=True);binary.write_bytes(b'fixture')
    calls=[]
    def query(args,**kwargs):
        calls.append(args)
        assert kwargs['stdin']==locator.subprocess.DEVNULL
        return SimpleNamespace(returncode=0,stdout=(str(root)+'\n').encode())
    monkeypatch.setattr(locator.subprocess,'run',query)
    assert locator.resolve_agent_executable('codex')==str(binary)
    assert locator.resolve_agent_executable('codex')==str(binary)
    assert len(calls)==1
    binary.unlink()
    assert locator.resolve_agent_executable('codex') is None
    assert len(calls)==2
    assert locator.resolve_agent_executable('claude') is None
    assert len(calls)==2
