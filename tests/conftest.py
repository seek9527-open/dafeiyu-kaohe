"""测试环境：注入 AstrBot 桩模块，让插件在无 AstrBot 的机器上可导入。"""

import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MAIN = ROOT / "astrbot_plugin_moon_gate" / "main.py"


def _build_stubs():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = logging.getLogger("astrbot")

    event_mod = types.ModuleType("astrbot.api.event")

    class AstrMessageEvent:  # noqa: D401 - 桩
        pass

    class _Filter:
        def command(self, *args, **kwargs):
            def deco(fn):
                fn.__command__ = (args, kwargs)
                return fn

            return deco

        def llm_tool(self, *args, **kwargs):
            def deco(fn):
                fn.__llm_tool__ = (args, kwargs)
                return fn

            return deco

    event_mod.AstrMessageEvent = AstrMessageEvent
    event_mod.filter = _Filter()

    star_mod = types.ModuleType("astrbot.api.star")

    class Context:
        pass

    class Star:
        def __init__(self, context=None):
            self.context = context

    class StarTools:
        @staticmethod
        def get_data_dir(name):  # pragma: no cover - 测试里会被替换
            raise RuntimeError("StarTools 桩未被替换")

    def register(*args, **kwargs):
        def deco(cls):
            return cls

        return deco

    star_mod.Context = Context
    star_mod.Star = Star
    star_mod.StarTools = StarTools
    star_mod.register = register

    api.event = event_mod
    api.star = star_mod
    astrbot.api = api

    for name, module in (
        ("astrbot", astrbot),
        ("astrbot.api", api),
        ("astrbot.api.event", event_mod),
        ("astrbot.api.star", star_mod),
    ):
        sys.modules.setdefault(name, module)


_build_stubs()


@pytest.fixture()
def gate_module():
    spec = importlib.util.spec_from_file_location("moon_gate_under_test", PLUGIN_MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
