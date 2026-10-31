"""工坊插件测试：路径白名单、备份、语法检查、回滚、限流与暂存审批上线。"""

import asyncio
import io
import json
import tarfile


class FakeEvent:
    def __init__(self, admin=True, umo="aiocqhttp:FriendMessage:1", message_str=""):
        self.message_str = message_str
        self.unified_msg_origin = umo
        self._admin = admin

    def is_admin(self):
        return self._admin

    def plain_result(self, text):
        return text


def run(coro):
    return asyncio.run(coro)


def collect(agen):
    async def _inner():
        return [msg async for msg in agen]

    return asyncio.run(_inner())


def setup_env(tmp_path, monkeypatch, module):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    data = tmp_path / "plugin_data" / "moon_workshop"
    workbench = data / "workbench"
    workbench.mkdir(parents=True)
    backups = data / "backups"
    backups.mkdir()
    events = data / "events.jsonl"
    staging = data / "staging"
    staging_done = data / "staging_done"
    approvals = data / "approvals"

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
    monkeypatch.setattr(module, "STAGING_ROOT", staging)
    monkeypatch.setattr(module, "STAGING_DONE_ROOT", staging_done)
    monkeypatch.setattr(module, "APPROVAL_ROOT", approvals)
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


def test_sandbox_tar_skips_data_dir(workshop_module, tmp_path):
    plugin = tmp_path / "demo_pkg"
    (plugin / "data").mkdir(parents=True)
    (plugin / "main.py").write_text("x = 1\n", encoding="utf-8")
    (plugin / "_conf_schema.json").write_text("{}", encoding="utf-8")
    (plugin / "data" / "cmd_config.json").write_text('{"secret": 1}', encoding="utf-8")

    raw = workshop_module._sandbox_tar(plugin, 1024 * 1024)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        names = tar.getnames()

    assert "main.py" in names
    assert "_conf_schema.json" in names
    assert all(not name.startswith("data/") for name in names)


def test_staging_redirects_live_write(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, _workbench, _backups, events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx, {"staging_required": True})

    reply = run(ws.ws_write_file(FakeEvent(), str(plugins / "demo6" / "main.py"), "x = 1\n"))
    assert "暂存区" in reply
    assert not (plugins / "demo6" / "main.py").exists()
    assert (workshop_module.STAGING_ROOT / "demo6" / "main.py").is_file()
    assert events_of(events)[-1]["kind"] == "stage_write"


def test_staging_write_allowed_directly(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, _workbench, _backups, events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx, {"staging_required": True})
    staged = workshop_module.STAGING_ROOT / "demo7" / "notes.md"

    reply = run(ws.ws_write_file(FakeEvent(), str(staged), "# 草稿", ""))
    assert "写好了" in reply or "暂存" in reply
    assert staged.is_file()


def test_promote_requires_sandbox_and_approval(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, _workbench, _backups, events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx, {"staging_required": True})
    run(ws.ws_write_file(FakeEvent(), str(plugins / "demo8" / "main.py"), "x = 1\n"))

    reply = run(ws.ws_promote(FakeEvent(), "demo8"))
    assert "沙箱" in reply

    ws._event("sandbox_ok", "staging/demo8")
    reply = run(ws.ws_promote(FakeEvent(), "demo8"))
    assert "还没批准" in reply

    msgs = collect(ws.workshop_command(FakeEvent(message_str="/工坊 批准 demo8")))
    assert any("批准了" in m for m in msgs)

    reply = run(ws.ws_promote(FakeEvent(), "demo8"))
    assert "上线了" in reply
    assert (plugins / "demo8" / "main.py").read_text(encoding="utf-8") == "x = 1\n"
    assert not (workshop_module.STAGING_ROOT / "demo8").exists()
    kinds = [e["kind"] for e in events_of(events)]
    assert "promote_ok" in kinds
    assert "write_ok" in kinds


def test_promote_rejects_stale_approval(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, _workbench, _backups, _events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx, {"staging_required": True})
    run(ws.ws_write_file(FakeEvent(), str(plugins / "demo9" / "main.py"), "x = 1\n"))
    ws._event("sandbox_ok", "staging/demo9")
    collect(ws.workshop_command(FakeEvent(message_str="/工坊 批准 demo9")))

    run(ws.ws_write_file(FakeEvent(), str(plugins / "demo9" / "main.py"), "x = 2\n"))
    reply = run(ws.ws_promote(FakeEvent(), "demo9"))
    assert "又改过" in reply
    assert not (plugins / "demo9" / "main.py").exists()


def test_reject_removes_staging(workshop_module, tmp_path, monkeypatch):
    ctx, plugins, _workbench, _backups, _events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx, {"staging_required": True})
    run(ws.ws_write_file(FakeEvent(), str(plugins / "demo10" / "main.py"), "x = 1\n"))

    msgs = collect(ws.workshop_command(FakeEvent(message_str="/工坊 拒绝 demo10")))
    assert any("驳回" in m for m in msgs)
    assert not (workshop_module.STAGING_ROOT / "demo10").exists()


def test_directory_path_allowed_for_read_denied_for_write(workshop_module, tmp_path, monkeypatch):
    """沙箱测试传进来的是目录：读目录要放行，写目录要明确拒绝——不能拿后缀去卡目录。"""
    ctx, plugins, _workbench, _backups, _events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx)
    d = plugins / "demo_dir"
    d.mkdir()
    (d / "metadata.yaml").write_text("name: demo\n", encoding="utf-8")

    ok, msg = ws._allowed_path(str(d))
    assert ok == d.resolve(), msg
    assert not msg

    denied, msg = ws._allowed_path(str(d), write=True)
    assert denied is None
    assert "目录" in msg

    denied, msg = ws._allowed_path(str(tmp_path / "outside_dir"))
    assert denied is None
    assert msg


def test_yaml_file_is_writable(workshop_module, tmp_path, monkeypatch):
    """metadata.yaml 是插件目录里的正当文件，写它不该被后缀规则拒绝。"""
    ctx, plugins, _workbench, _backups, _events = setup_env(tmp_path, monkeypatch, workshop_module)
    ws = workshop_module.MoonWorkshop(ctx)
    target = plugins / "demo_yaml" / "metadata.yaml"
    target.parent.mkdir()
    target.write_text("name: demo\nversion: 1\n", encoding="utf-8")

    ok, msg = ws._allowed_path(str(target), write=True)
    assert ok == target.resolve(), msg

    reply = run(ws.ws_write_file(FakeEvent(), str(target), "name: demo\nversion: 2\n", "改版本"))
    assert "写好了" in reply
    assert "version: 2" in target.read_text(encoding="utf-8")


def test_sandbox_tar_includes_aux_without_secrets(workshop_module, tmp_path):
    """沙箱要能检查完整插件目录：metadata.yaml、LICENSE 进包，.env 与数据库不进。"""
    plugin = tmp_path / "demo_aux"
    plugin.mkdir()
    (plugin / "main.py").write_text("x = 1\n", encoding="utf-8")
    (plugin / "metadata.yaml").write_text("name: demo\n", encoding="utf-8")
    (plugin / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (plugin / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (plugin / "cache.db").write_text("x", encoding="utf-8")
    (plugin / "data").mkdir()
    (plugin / "data" / "state.json").write_text("{}", encoding="utf-8")

    raw = workshop_module._sandbox_tar(plugin, 1024 * 1024)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        names = tar.getnames()

    assert "main.py" in names
    assert "metadata.yaml" in names
    assert "LICENSE" in names
    assert ".env" not in names
    assert "cache.db" not in names
    assert all(not name.startswith("data/") for name in names)
