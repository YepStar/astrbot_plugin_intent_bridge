"""只读扫描安装目录；静态解析未载入插件，不导入或启用其代码。"""

import ast
from collections import defaultdict
from pathlib import Path

import yaml

from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path

from .annotations import plugin_title


def registered_commands():
    result = defaultdict(list)
    for handler in star_handlers_registry:
        if handler.event_type != EventType.AdapterMessageEvent:
            continue
        owner = star_map.get(handler.handler_module_path)
        filters = [f for f in handler.event_filters if isinstance(f, CommandFilter)]
        if owner and owner.name and len(filters) == 1:
            name = filters[0].get_complete_command_names()[0]
            result[owner.name + ":" + name].append((handler, filters[0]))
    return dict(result)


def installed_plugins(stars, root=None):
    plugins = {}
    commands = []
    for star in stars:
        if not star.name:
            continue
        plugins[star.name] = {
            "name": star.name,
            "title_zh": plugin_title(star.name),
            "version": str(star.version or ""),
            "active": bool(star.activated),
            "loaded": True,
            "description": str(getattr(star, "desc", "") or "")[:500],
            "directory": getattr(star, "root_dir_name", "") or "",
        }
        if plugins[star.name]["title_zh"] == star.name:
            plugins[star.name]["title_zh"] = (
                getattr(star, "display_name", "") or star.name
            )
    directory = Path(root or get_astrbot_plugin_path())
    if not directory.is_dir():
        return list(plugins.values()), commands
    for folder in sorted(directory.iterdir()):
        if not folder.is_dir() or folder.is_symlink() or folder.name.startswith("."):
            continue
        metadata = {}
        for filename in ("metadata.yaml", "metadata.yml"):
            path = folder / filename
            if path.is_file() and path.stat().st_size < 100_000:
                try:
                    metadata = yaml.safe_load(path.read_text("utf-8")) or {}
                except (OSError, ValueError, yaml.YAMLError):
                    pass
                break
        if not isinstance(metadata, dict):
            metadata = {}
        if not metadata and not (folder / "main.py").is_file():
            continue
        name = str(metadata.get("name") or folder.name)
        # 目录名和声明名不一致时，以运行时已知身份为准。
        match = next(
            (p for p in plugins.values() if p["directory"] == folder.name), None
        )
        if match:
            name = match["name"]
        if name not in plugins:
            plugins[name] = {
                "name": name,
                "title_zh": plugin_title(name),
                "version": str(metadata.get("version") or ""),
                "active": False,
                "loaded": False,
                "description": str(metadata.get("desc") or "")[:500],
                "directory": folder.name,
            }
            if plugins[name]["title_zh"] == name:
                plugins[name]["title_zh"] = str(metadata.get("display_name") or name)
        # 未载入/停用插件也展示静态指令，但静态目录绝不作为可执行注册表。
        if not plugins[name]["active"]:
            commands.extend(source_commands(folder, name))
    return list(plugins.values()), commands


def source_commands(folder, plugin):
    nodes = []
    for path in sorted(folder.rglob("*.py"))[:250]:
        if any(
            p in {"tests", ".git", "__pycache__", "venv", ".venv"}
            for p in path.relative_to(folder).parts
        ):
            continue
        try:
            if path.is_symlink() or path.stat().st_size > 500_000:
                continue
            tree = ast.parse(path.read_text("utf-8"))
            nodes.extend(
                n
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
        except (OSError, UnicodeError, SyntaxError):
            continue
    groups = {}
    result = {}
    # 多轮解析支持父指令组在其他文件/声明顺序中的常见情况。
    for _ in range(4):
        for node in nodes:
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(
                    decorator.func, ast.Attribute
                ):
                    continue
                if decorator.func.attr not in {"command", "command_group", "group"}:
                    continue
                value = (
                    decorator.args[0]
                    if decorator.args
                    else next(
                        (
                            k.value
                            for k in decorator.keywords
                            if k.arg == "command_name"
                        ),
                        None,
                    )
                )
                if not isinstance(value, ast.Constant) or not isinstance(
                    value.value, str
                ):
                    continue
                owner = ast.unparse(decorator.func.value).removeprefix("self.")
                if owner in {"filter", "event.filter"}:
                    command = value.value
                elif owner in groups:
                    command = groups[owner] + " " + value.value
                else:
                    continue
                if decorator.func.attr in {"command_group", "group"}:
                    groups[node.name] = command
                else:
                    key = plugin + ":" + command
                    result[key] = {
                        "key": key,
                        "plugin": plugin,
                        "name": command,
                        "description": (ast.get_docstring(node) or "")[:700],
                        "enabled": False,
                        "available": False,
                        "plugin_active": False,
                        "supported": False,
                        "registered": False,
                        "reason": "静态读取；请先在 AstrBot 系统 → 插件中启用并成功载入。",
                    }
    return list(result.values())
