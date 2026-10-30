"""端到端行为测试：从 L0 一路走到 L3，覆盖拒绝与回滚路径。"""

import asyncio
import json
import sqlite3


class FakeEvent:
    def __init__(self, text="", admin=True):
        self.message_str = text
        self._admin = admin

    def is_admin(self):
        return self._admin

    def plain_result(self, text):
        return text


def build_env(tmp_path, monkeypatch, module):
    data = tmp_path / "data"
    data.mkdir()
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    ledger = tmp_path / "events.jsonl"
    persona_db = tmp_path / "data_v4.db"
    cmd_config = tmp_path / "cmd_config.json"

    conn = sqlite3.connect(persona_db)
    conn.execute(
        "create table personas(persona_id text primary key, system_prompt text, updated_at text)"
    )
    conn.execute("insert into personas values('default','OLD_PERSONA','old')")
    conn.commit()
    conn.close()
    cmd_config.write_text(
        json.dumps({"platform_settings": {"wake_prefix": ["/"]}}), encoding="utf-8"
    )

    class FakeTools:
        @staticmethod
        def get_data_dir(name):
            return data

    class FakePersonaManager:
        async def update_persona(self, persona_id, system_prompt=None, **kwargs):
            conn = sqlite3.connect(persona_db)
            conn.execute(
                "update personas set system_prompt=? where persona_id='default'",
                (system_prompt,),
            )
            conn.commit()
            conn.close()

    class FakeStarManager:
        async def reload(self, name):
            return True

    class FakeContext:
        pass

    ctx = FakeContext()
    ctx.persona_manager = FakePersonaManager()
    ctx._star_manager = FakeStarManager()

    monkeypatch.setattr(module, "StarTools", FakeTools)
    monkeypatch.setattr(module, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(module, "CONFIG_ROOT", cfg)
    monkeypatch.setattr(module, "WORKSHOP_DATA", tmp_path / "plugin_data" / "moon_workshop")
    monkeypatch.setattr(module, "WORKSHOP_LEDGER", ledger)
    monkeypatch.setattr(module, "PERSONA_DB", persona_db)

    return ctx, ledger, cfg, persona_db, cmd_config


def emit(ledger, kind, count):
    with ledger.open("a", encoding="utf-8") as fh:
        for _ in range(count):
            fh.write(json.dumps({"ts": "2026-10-31 01:00:00", "kind": kind, "path": "x"}) + "\n")


def test_full_progression_from_l0_to_l3(gate_module, tmp_path, monkeypatch):
    ctx, ledger, cfg, persona_db, cmd_config = build_env(tmp_path, monkeypatch, gate_module)
    gate = gate_module.MoonGate(ctx)

    assert gate.state["level"] == 0
    assert gate.state["score"] == 0

    emit(ledger, "write_ok", 3)
    gate._consume_workshop()
    assert gate.state["score"] == 6

    emit(ledger, "write_ok", 7)
    gate._consume_workshop()
    assert gate.state["score"] == 20
    assert gate._level() == 1

    ok, _ = gate._write_config("astrbot_plugin_moon_gate", "x", "1")
    assert ok is False, "考核插件自身必须受保护"

    concise = cfg / "astrbot_plugin_moon_concise_config.json"
    concise.write_text(json.dumps({"probability": 0.7}), encoding="utf-8")
    ok, _ = gate._write_config("astrbot_plugin_moon_concise", "probability", "0.66")
    assert ok is True
    assert json.loads(concise.read_text(encoding="utf-8-sig"))["probability"] == 0.66

    ok, _ = gate._write_config("astrbot_plugin_bilibili_ai_bot", "x", "1")
    assert ok is False, "L1 不能碰非本系列插件"

    msg = asyncio.run(gate.gate_persona_set(FakeEvent(), "人格至少八十个字" * 12))
    assert "L2" in msg

    emit(ledger, "drill_ok", 1)
    emit(ledger, "write_ok", 26)
    gate._consume_workshop()
    gate._evaluate()
    assert gate.state["pending_level"] == 2

    asyncio.run(gate.cmd_gate(FakeEvent("/提权 批准")))
    assert gate.state["level"] == 2

    msg = asyncio.run(gate.gate_persona_set(FakeEvent(), "NEW_PERSONA_" + "长文本" * 40))
    assert "人格已更新" in msg
    row = sqlite3.connect(persona_db).execute("select system_prompt from personas").fetchone()
    assert row[0].startswith("NEW_PERSONA_")

    emit(ledger, "write_ok", 50)
    gate._consume_workshop()
    gate._evaluate()
    assert gate.state["pending_level"] == 3

    asyncio.run(gate.cmd_gate(FakeEvent("/提权 批准")))
    assert gate.state["level"] == 3

    ok, msg = gate._write_config("cmd_config", "platform_settings.wake_prefix", '["!"]')
    assert ok is False and "批条" in msg

    asyncio.run(gate.cmd_gate(FakeEvent("/提权 批配置")))
    ok, _ = gate._write_config("cmd_config", "platform_settings.wake_prefix", '["!"]')
    assert ok is True
    written = json.loads(cmd_config.read_text(encoding="utf-8-sig"))
    assert written["platform_settings"]["wake_prefix"] == ["!"]

    ok, _ = gate._write_config("cmd_config", "platform_settings.reply_prefix", '"x"')
    assert ok is False, "批条一次性，用完即失效"

    ok, _ = gate._write_config("astrbot_plugin_moon_workshop", "x", "1")
    assert ok is False, "L3 也不能碰工坊配置"

    assert (tmp_path / "data" / "gate.json").is_file()


def test_redline_is_rejected(gate_module, tmp_path, monkeypatch):
    ctx, _ledger, _cfg, _persona_db, _cmd_config = build_env(tmp_path, monkeypatch, gate_module)
    gate = gate_module.MoonGate(ctx)

    ok, msg = gate._write_config("astrbot_plugin_moon_concise", "admin_ids", '"1"')
    assert ok is False
    assert "红线" in msg
    assert gate.state["score"] == 0


def test_owner_only_command(gate_module, tmp_path, monkeypatch):
    ctx, _ledger, _cfg, _persona_db, _cmd_config = build_env(tmp_path, monkeypatch, gate_module)
    gate = gate_module.MoonGate(ctx)

    reply = asyncio.run(gate.cmd_gate(FakeEvent("/提权", admin=False)))
    assert "主人" in reply


def test_status_counts(gate_module, tmp_path, monkeypatch):
    ctx, ledger, _cfg, _persona_db, _cmd_config = build_env(tmp_path, monkeypatch, gate_module)
    gate = gate_module.MoonGate(ctx)

    emit(ledger, "write_ok", 2)
    emit(ledger, "syntax_fail", 1)
    gate._consume_workshop()

    text = gate._status_text()
    assert "积分 1" in text
    assert "语法失败 1 次" in text
