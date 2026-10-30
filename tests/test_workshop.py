"""工坊插件测试：路径白名单、备份、语法检查、回滚与限流。"""

import asyncio
import json


class FakeEvent:
    def __init__(self, admin=True, umo="aiocqhttp:FriendMessage:1"):
        self.message_str = ""
        self.unified_msg_origin = umo
        self._admin = admin

    def is_admin(self):
        return self._admin

    def plain_result(self, text):
        return text


def run(coro):
    return asyncio.run(coro)


def setup_env(tmp_path, monkeypatch, module):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    data = tmp_path / "plugin_data" / "moon_workshop"
    workbench = data / "workbench"
    workbench.mkdir(parents=True)
    backups = data / "backups"
    backups.mkdir()
    events = data / "events.jsonl"

    class FakeStarManager:
        async def reload(self, name=None):
            return f"reloaded:{name}"

    class FakeContext:
        pass

    ctx = FakeContext()
    ctx._star_manager = FakeStarManager()

    monkeypatch.setattr(module, "PLUGINS_ROOT", plugins)
    monkeypatch.setattr(module, "WORKSHOP_DATA", data)
    monkeypatch.setattr(module, "WORKBENCH_ROOT", workbench)
    monkeypatch.setattr(module, "BACKUP_ROOT", backups)
    monkeypatch.setattr(module, "EVENTS_FILE", events)
    return ctx, plugins, workbench, backups, events


def events_of(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_path_whitelist(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, workbench, _backups, _events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx)

    ok, _ = ws._allowed_path(str(plugins / "demo" / "main.py"), write=True)
    assert ok is not None

    ok, _ = ws._allowed_path(str(workbench / "scratch.md"), write=True)
    assert ok is not None

    for bad in (
        str(tmp_path / "outside" / "evil.py"),
        str(plugins / "demo" / "cmd_config.json"),
        str(plugins / "demo" / "data_v4.db"),
        str(plugins / "demo" / "run.exe"),
        str(plugins / "astrbot_plugin_moon_workshop" / "main.py"),
        str(plugins / "astrbot_plugin_moon_gate" / "main.py"),
    ):
        denied, msg = ws._allowed_path(bad, write=True)
        assert denied is None, bad
        assert msg


def test_write_backup_and_event(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, _workbench, backups, events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx)

    target = plugins / "demo" / "notes.txt"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8")

    reply = run(ws.ws_write_file(FakeEvent(), str(target), "new", "测试"))
    assert "写好了" in reply

    assert target.read_text(encoding="utf-8") == "new"
    bucket = backups / "demo"
    assert bucket.is_dir()
    manifest = bucket / "manifest.jsonl"
    assert manifest.is_file()
    first = json.loads(manifest.read_text(encoding="utf-8").splitlines()[0])
    assert first["size"] == 3
    assert len(first["sha256"]) == 64
    kinds = [e["kind"] for e in events_of(events)]
    assert kinds == ["write_ok"]


def test_syntax_failure_restores_file(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, _workbench, _backups, events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx)

    target = plugins / "demo2" / "main.py"
    target.parent.mkdir()
    target.write_text("x = 1\n", encoding="utf-8")

    reply = run(ws.ws_write_file(FakeEvent(), str(target), "def broken(:\n", "写坏"))
    assert "检查没过" in reply
    assert target.read_text(encoding="utf-8") == "x = 1\n"

    kinds = [e["kind"] for e in events_of(events)]
    assert kinds == ["syntax_fail"]


def test_rollback_drill(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, _workbench, _backups, events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx)

    target = plugins / "demo3" / "main.py"
    target.parent.mkdir()
    target.write_text("v1 = 1\n", encoding="utf-8")

    assert "写好了" in run(ws.ws_write_file(FakeEvent(), str(target), "v2 = 2\n"))
    assert "写好了" in run(ws.ws_write_file(FakeEvent(), str(target), "v3 = 3\n"))

    reply = run(ws.ws_rollback(FakeEvent(), str(target), reason="演练"))
    assert "演练" in reply
    assert target.read_text(encoding="utf-8") == "v2 = 2\n"
    assert events_of(events)[-1]["kind"] == "drill_ok"


def test_max_files_per_turn(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, _workbench, _backups, _events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx)
    target_dir = plugins / "demo4"
    target_dir.mkdir()

    for name in ("a.txt", "b.txt", "c.txt"):
        reply = run(ws.ws_write_file(FakeEvent(), str(target_dir / name), "x", ""))
        assert "写好了" in reply

    reply = run(ws.ws_write_file(FakeEvent(), str(target_dir / "d.txt"), "x", ""))
    assert "已经改了" in reply


def test_owner_only(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, _workbench, _backups, _events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx)

    reply = run(ws.ws_write_file(FakeEvent(admin=False), str(plugins / "demo5" / "a.txt"), "x"))
    assert "主人" in reply
