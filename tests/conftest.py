import pytest

@pytest.fixture(autouse=True)
def isolated_router_state(tmp_path, monkeypatch):
    import test_bridge
    import bridge_test_pkg.translation as translation
    import bridge_test_pkg.corrections as corrections
    import bridge_test_pkg.control as control
    from types import SimpleNamespace as NS
    monkeypatch.setattr(translation, 'state_directory', lambda: tmp_path / 'state')
    monkeypatch.setattr(corrections, 'state_directory', lambda: tmp_path / 'state')
    monkeypatch.setattr(control, 'installed_plugins', lambda stars, root=None: __import__(
        'bridge_test_pkg.inventory', fromlist=['installed_plugins']).installed_plugins(stars, root or tmp_path / 'plugins'))
    monkeypatch.setitem(control.star_map, 'fixture.main', NS(name='test_plugin', activated=True))
