"""Persist integrated command settings and import the legacy allowlist once."""
from collections.abc import MutableMapping
from pathlib import Path
import json
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from .command_service import CommandService


class CommandConfig(MutableMapping):
    KEYS = ('allowed_commands', 'command_timeout')
    def __init__(self, config):
        self.parent = config
    def __iter__(self):
        return iter(key for key in self.KEYS if key in self.parent)
    def __len__(self):
        return sum(key in self.parent for key in self.KEYS)
    def __getitem__(self, key):
        if key not in self.KEYS: raise KeyError(key)
        return self.parent[key]
    def __setitem__(self, key, value):
        if key not in self.KEYS: raise KeyError(key)
        self.parent[key] = value
    def __delitem__(self, key):
        if key not in self.KEYS: raise KeyError(key)
        self.parent.pop(key, None)
    def save_config(self):
        self.parent.save_config()


def create_command_service(context, config, owner_module, legacy_path=None):
    if config.get('command_migration_done', False):
        return CommandService(context, CommandConfig(config), owner_module)
    path = Path(legacy_path) if legacy_path is not None else Path(get_astrbot_data_path()) / 'config' / 'astrbot_plugin_command_tools_config.json'
    old = dict(config)
    try:
        if path.is_file():
            legacy = json.loads(path.read_text(encoding='utf-8-sig'))
            # Validate before persisting; explicit new authorizations take precedence.
            CommandService(context, legacy, owner_module)
            if not config.get('allowed_commands'):
                config['allowed_commands'] = legacy.get('allowed_commands', [])
                config['command_timeout'] = legacy.get('command_timeout', 30)
        service = CommandService(context, CommandConfig(config), owner_module)
        config['command_migration_done'] = True
        config.save_config()
        return service
    except Exception:
        config.clear()
        config.update(old)
        raise
