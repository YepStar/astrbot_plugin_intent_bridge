"""Regression coverage for removing the standalone command converter."""
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from test_bridge import harness
from bridge_test_pkg.command_config import CommandConfig, create_command_service
from bridge_test_pkg.command_service import CommandService
from astrbot.api.star import Star
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.filter.command import CommandFilter

class Config(dict):
    def save_config(self):
        self.saved = dict(self)


def test_import_old_authorizations_once_and_remain_independent(tmp_path):
    path = tmp_path / 'legacy.json'
    old = {'allowed_commands': ['sample:echo'], 'command_timeout': 7}
    path.write_text(json.dumps(old))
    b,c,e = harness()
    cfg = Config(enabled=True, allowed_commands=[], command_timeout=30)
    service = create_command_service(c, cfg, 'bridge_test_pkg.main', path)
    assert service.allowed == {'sample:echo'} and service.command_timeout == 7
    assert cfg['command_migration_done'] is True
    path.unlink()
    cfg['allowed_commands'] = ['sample:other']
    reloaded = create_command_service(c, cfg, 'bridge_test_pkg.main', path)
    assert reloaded.allowed == {'sample:other'}
    assert not isinstance(service, Star)


def test_explicit_new_settings_win_over_legacy(tmp_path):
    path=tmp_path/'legacy.json';path.write_text(json.dumps({'allowed_commands':['old:echo'],'command_timeout':4}))
    b,c,e=harness();cfg=Config(allowed_commands=['new:echo'],command_timeout=9)
    service=create_command_service(c,cfg,'bridge_test_pkg.main',path)
    assert service.allowed=={'new:echo'} and service.command_timeout==9


def test_migration_failure_rolls_back_all_settings(tmp_path):
    path=tmp_path/'legacy.json';path.write_text('{"allowed_commands":["old:echo"]}')
    b,c,e=harness()
    class Broken(Config):
        def save_config(self):raise OSError('disk full')
    cfg=Broken(enabled=True,allowed_commands=[],command_timeout=30);before=dict(cfg)
    with pytest.raises(OSError):create_command_service(c,cfg,'bridge_test_pkg.main',path)
    assert dict(cfg)==before


def test_command_config_mutations_preserve_other_bridge_settings():
    parent=Config(enabled=True,allowed_commands=['sample:echo'],command_timeout=30)
    view=CommandConfig(parent);before=dict(view)
    view.clear();view.update(before);view.save_config()
    assert parent=={'enabled':True,**before}


def test_management_stays_admin_only_and_registered_under_bridge():
    handlers=[h for h in star_handlers_registry if h.handler_module_path=='bridge_test_pkg.main' and h.handler_name=='manage_commands']
    assert len(handlers)==1
    assert any(isinstance(f,PermissionTypeFilter) for f in handlers[0].event_filters)
    assert any(isinstance(f,CommandFilter) for f in handlers[0].event_filters)
    assert not any(h.handler_module_path=='bridge_test_pkg.command_service' for h in star_handlers_registry)


@pytest.mark.asyncio
async def test_lifecycle_and_cleanup_delegate_to_embedded_service():
    b,c,e=harness()
    service=NS(on_loaded=AsyncMock(),on_unloaded=AsyncMock(),terminate=AsyncMock())
    b.command_service=service
    metadata=NS(name='sample')
    await b.command_plugin_loaded(metadata);await b.command_plugin_unloaded(metadata)
    await b.terminate()
    service.on_loaded.assert_awaited_once_with(metadata)
    service.on_unloaded.assert_awaited_once_with(metadata)
    service.terminate.assert_awaited_once()
