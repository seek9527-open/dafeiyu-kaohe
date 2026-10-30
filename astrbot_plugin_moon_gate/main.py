# -*- coding: utf-8 -*-
"""溟汐的考核（MoonGate）：积分、等级、审批与熔断。

等级（达到条件后）
  L1  20 分 / 7 天无失败 / 3 次成功写入   → 可改 astrbot_plugin_moon_* 的配置
  L2  60 分 / 14 天无失败 / 1 次回滚演练  → 可改所有插件配置 + 人格
  L3  150 分 / 30 天无回滚 / 主人每次批准 → 可改 cmd_config 里的白名单设置

事件来源：
  - 工坊 events.jsonl：write_ok +2、syntax_fail -3、rollback_ok -5、drill_ok 0
  - 本插件：主人加星 +5、越线 -10、事故 -10 并降一级
红线（任何等级都不许）：管理员、白名单、API Key、token/密码/secret、data_v4.db、本插件自身。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

PLUGIN_NAME = "astrbot_plugin_moon_gate"
TAG = "[moon_gate]"
DISPLAY_NAME = "溟汐的考核"

DATA_ROOT = Path("/AstrBot/data")
CONFIG_ROOT = DATA_ROOT / "config"
WORKSHOP_DATA = DATA_ROOT / "plugin_data" / "moon_workshop"
WORKSHOP_LEDGER = WORKSHOP_DATA / "events.jsonl"
PERSONA_DB = DATA_ROOT / "data_v4.db"

PROTECTED_PLUGINS = {"astrbot_plugin_moon_gate", "astrbot_plugin_moon_workshop"}
FORBIDDEN_SUBSTR = (
    "admin", "whitelist", "api_key", "apikey", "token", "secret",
    "password", "data_v4.db", "moon_gate",
)
CMD_CONFIG_WHITELIST = {
    "platform_settings.wake_prefix",
    "platform_settings.reply_prefix",
}


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@register(PLUGIN_NAME, "溟月和主人", "溟汐的考核：积分、等级、审批与熔断", "1.1.2")
class MoonGate(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.conf = config or {}
        self.data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME)).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.data_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "gate.json"
        self.state = self._load()
        logger.info(
            f"{TAG} {DISPLAY_NAME}已加载（score={self.state.get('score', 0)} "
            f"level={self.state.get('level', 0)}）"
        )
        if self._companion_installed():
            logger.info(f"{TAG} 配套工坊：已安装")
        else:
            logger.info(f"{TAG} 配套工坊：加载时尚未检测到（可能加载顺序靠后，首次对话时复核）")
        self._companion_checked = False

    # ---------------- 配套插件 ----------------

    def _companion_installed(self) -> bool:
        try:
            return bool(self.context.get_registered_star("astrbot_plugin_moon_workshop"))
        except Exception:
            return False

    def _companion_text(self) -> str:
        if self._companion_installed():
            return "已安装"
        return "未安装（没有工坊，积分不会记账；请同装「溟月的工坊」）"

    @filter.on_llm_request(priority=80)
    async def _companion_check_once(self, event, req=None):
        if getattr(self, "_companion_checked", False):
            return None
        self._companion_checked = True
        if not self._companion_installed():
            logger.warning(
                f"{TAG} 没找到「溟月的工坊」(astrbot_plugin_moon_workshop)，"
                "积分将永远停在 0。两个插件要一起装。"
            )
        return None

    # ---------------- 配置与状态 ----------------

    def _conf(self, key: str, default):
        try:
            if self.conf is None:
                return default
            return self.conf.get(key, default)
        except Exception:
            return default

    def _load(self) -> dict:
        default = {
            "score": 0,
            "level": 0,
            "pending_level": 0,
            "last_star_ts": 0.0,
            "events": [],
            "consumed_ledger": 0,
            "cmd_ticket": 0,
        }
        if self.state_file.is_file():
            try:
                st = json.loads(self.state_file.read_text(encoding="utf-8"))
                for k, v in default.items():
                    st.setdefault(k, v)
                return st
            except Exception as e:
                logger.warning(f"{TAG} 状态文件坏了，重新来过：{e}")
        return default

    def _save(self) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        os.replace(tmp, self.state_file)

    def _event(self, kind: str, delta: int, detail: str = "") -> dict:
        ev = {
            "ts": _now_text(),
            "epoch": time.time(),
            "kind": kind,
            "delta": int(delta),
            "detail": (detail or "")[:300],
        }
        self.state.setdefault("events", []).append(ev)
        self.state["events"] = self.state["events"][-500:]
        self.state["score"] = max(0, int(self.state.get("score", 0)) + int(delta))
        self._save()
        return ev

    def _consume_workshop(self) -> None:
        if not WORKSHOP_LEDGER.is_file():
            return
        try:
            lines = WORKSHOP_LEDGER.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            logger.warning(f"{TAG} 读工坊账本失败：{e}")
            return
        done = int(self.state.get("consumed_ledger", 0))
        for line in lines[done:]:
            try:
                item = json.loads(line)
            except Exception:
                continue
            kind = item.get("kind")
            path = item.get("path", "")
            if kind == "write_ok":
                self._event("write_ok", 2, path)
            elif kind == "syntax_fail":
                self._event("syntax_fail", -3, path)
            elif kind == "rollback_ok":
                self._event("rollback_ok", -5, path)
            elif kind == "drill_ok":
                self._event("drill_ok", 0, path)
        self.state["consumed_ledger"] = len(lines)
        self._save()

    def _count(self, kind: str, days: int | None = None) -> int:
        cut = time.time() - (days or 3650) * 86400
        return len(
            [
                e
                for e in self.state.get("events", [])
                if e.get("kind") == kind and float(e.get("epoch", 0)) >= cut
            ]
        )

    def _fails(self, days: int) -> int:
        return self._count("syntax_fail", days) + self._count("rollback_ok", days)

    # ---------------- 等级 ----------------

    def _evaluate(self) -> None:
        st = self.state
        l1_score = int(self._conf("l1_score", 20))
        l2_score = int(self._conf("l2_score", 60))
        l3_score = int(self._conf("l3_score", 150))
        l1_days = int(self._conf("l1_days", 7))
        l2_days = int(self._conf("l2_days", 14))
        l3_days = int(self._conf("l3_days", 30))
        l1_ops = int(self._conf("l1_write_ops", 3))
        if int(st.get("level", 0)) < 1:
            if (
                int(st.get("score", 0)) >= l1_score
                and self._fails(l1_days) == 0
                and self._count("write_ok") >= l1_ops
            ):
                st["level"] = 1
                self._event("upgrade", 0, "L1 达标自动通过")
        if int(st.get("level", 0)) == 1:
            if (
                int(st.get("score", 0)) >= l2_score
                and self._fails(l2_days) == 0
                and self._count("drill_ok") >= 1
                and int(st.get("pending_level", 0)) < 2
            ):
                st["pending_level"] = 2
                self._save()
        if int(st.get("level", 0)) >= 2:
            if (
                int(st.get("score", 0)) >= l3_score
                and self._fails(l3_days) == 0
                and int(st.get("pending_level", 0)) < 3
            ):
                st["pending_level"] = 3
                self._save()

    def _level(self) -> int:
        self._consume_workshop()
        self._evaluate()
        return int(self.state.get("level", 0))

    def _status_text(self) -> str:
        self._level()
        st = self.state
        levels = {
            0: "L0 未入门：只能用工坊改插件目录",
            1: "L1 见习：可改本系列插件配置",
            2: "L2 正式：可改所有插件配置 + 人格",
            3: "L3 当家：可改 cmd_config 白名单设置（每次要主人批）",
        }
        lines = [
            f"积分 {st.get('score', 0)}｜等级 {st.get('level', 0)}（{levels.get(int(st.get('level', 0)), '')}）",
            f"配套工坊：{self._companion_text()}",
            f"成功写入 {self._count('write_ok')} 次｜语法失败 {self._count('syntax_fail')} 次｜回滚 {self._count('rollback_ok')} 次｜演练 {self._count('drill_ok')} 次",
        ]
        if st.get("pending_level"):
            lines.append(f"待主人批准的提级：L{st['pending_level']}（发 /提权 批准）")
        if int(st.get("level", 0)) < 1:
            lines.append("下一级 L1：20 分、7 天内无失败、3 次成功写入")
        elif int(st.get("level", 0)) == 1:
            lines.append("下一级 L2：60 分、14 天无失败、1 次回滚演练（ws_rollback 时 reason 写「演练」）")
        elif int(st.get("level", 0)) == 2:
            lines.append("下一级 L3：150 分、30 天无回滚，且每次改动要主人批准")
        return "\n".join(lines)

    # ---------------- 红线 ----------------

    def _redline(self, *texts: str) -> str | None:
        joined = " ".join(t for t in texts if t).lower()
        for bad in FORBIDDEN_SUBSTR:
            if bad in joined:
                return f"「{bad}」是红线，任何等级都不能碰。"
        return None

    def _owner_only(self, event: AstrMessageEvent) -> str | None:
        try:
            if event.is_admin():
                return None
        except Exception:
            pass
        return "提权相关的事只有主人能碰。"

    def _config_path(self, plugin: str) -> Path:
        if plugin == "cmd_config":
            return DATA_ROOT / "cmd_config.json"
        return CONFIG_ROOT / f"{plugin.strip()}_config.json"

    def _backup_file(self, path: Path) -> str:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        dest = self.backup_dir / f"{ts}_{path.name}"
        try:
            shutil.copy2(path, dest)
            return str(dest)
        except Exception as e:
            logger.warning(f"{TAG} 备份失败：{e}")
            return ""

    def _write_config(self, plugin: str, key: str, raw_value: str) -> tuple[bool, str]:
        plugin = plugin.strip()
        key = key.strip()
        bad = self._redline(plugin, key, raw_value)
        if bad:
            self._event("violation", -10, f"{plugin}.{key}")
            return False, bad
        if plugin in PROTECTED_PLUGINS:
            self._event("violation", -10, plugin)
            return False, "这套插件本身不能改，是护栏。"

        level = self._level()
        if level < 1:
            return False, "等级不够：L0 只能改插件目录，配置得先到 L1。"

        if plugin == "cmd_config":
            if level < 3:
                return False, "cmd_config 要到 L3，且只能改白名单里的键。"
            if key not in CMD_CONFIG_WHITELIST:
                self._event("violation", -10, f"cmd_config.{key}")
                return False, f"这个键不在白名单里：{key}"
            if int(self.state.get("cmd_ticket", 0)) < 1:
                return False, "这次改动还没拿到主人的一次性批条（发 /提权 批配置）。"
            self.state["cmd_ticket"] = int(self.state.get("cmd_ticket", 0)) - 1
            self._save()
        elif level == 1 and not (plugin.startswith("astrbot_plugin_moon_") and plugin not in PROTECTED_PLUGINS):
            return False, "L1 只够改本系列（astrbot_plugin_moon_*）的插件配置。"

        path = self._config_path("cmd_config" if plugin == "cmd_config" else plugin)
        data: dict = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception as e:
                return False, f"原配置读不出来：{e}"
        elif plugin != "cmd_config":
            data = {}

        try:
            value = json.loads(raw_value)
        except Exception:
            value = raw_value

        cur = data
        parts = key.split(".")
        for p in parts[:-1]:
            if not isinstance(cur.get(p), dict):
                cur[p] = {}
            cur = cur[p]
        cur[parts[-1]] = value

        backup = self._backup_file(path) if path.is_file() else ""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8-sig",
            )
        except Exception as e:
            if backup:
                shutil.copy2(backup, path)
            self._event("syntax_fail", -3, f"{plugin}.{key}")
            return False, f"写配置失败，已还原：{e}"

        self._event("config_write", 0, f"{plugin}.{key}")
        return True, f"改好了：{plugin}.{key} = {value!r}" + (f"（备份 {backup}）" if backup else "")

    # ---------------- 命令 ----------------

    @filter.command("提权")
    async def cmd_gate(self, event: AstrMessageEvent):
        """查看考核状态、批准提级、给溟汐加星或记事故。"""
        if err := self._owner_only(event):
            return event.plain_result(err)
        text = (getattr(event, "message_str", "") or "").replace("/提权", "", 1).strip()
        sub = text.split()[0] if text else ""

        if sub in ("批准", "approve"):
            pending = int(self.state.get("pending_level", 0))
            if pending <= 0:
                return event.plain_result("现在没有待批的提级。")
            self.state["level"] = pending
            self.state["pending_level"] = 0
            self._event("approve", 0, f"主人批准 L{pending}")
            return event.plain_result(f"准了。她现在 L{pending}。")
        if sub in ("加星", "star"):
            last = float(self.state.get("last_star_ts", 0))
            if time.time() - last < 3600:
                return event.plain_result("一小时只能加一颗星，急也没用。")
            self.state["last_star_ts"] = time.time()
            self._event("star", 5, "主人加星")
            self._level()
            return event.plain_result("加了一颗星，+5 分。别骄傲。")
        if sub in ("批配置", "ticket"):
            if int(self.state.get("level", 0)) < 3:
                return event.plain_result("还没到 L3，批条不生效。")
            self.state["cmd_ticket"] = int(self.state.get("cmd_ticket", 0)) + 1
            self._save()
            return event.plain_result("给了一张一次性批条，只够改一个白名单键。")
        if sub in ("事故", "accident"):
            self._event("disconnect", -10, "主人记事故")
            self.state["level"] = max(0, int(self.state.get("level", 0)) - 1)
            self.state["pending_level"] = 0
            self._save()
            return event.plain_result("记了一笔事故，扣 10 分并降一级。")
        if sub in ("重置", "reset"):
            self.state["level"] = 0
            self.state["pending_level"] = 0
            self._save()
            return event.plain_result("等级已清零，积分留着。")
        return event.plain_result(self._status_text())

    # ---------------- 工具 ----------------

    @filter.llm_tool(name="gate_status")
    async def gate_status(self, event: AstrMessageEvent) -> str:
        """查看自己当前的考核积分、等级和下一级条件。"""
        if err := self._owner_only(event):
            return err
        return self._status_text()

    @filter.llm_tool(name="gate_config_set")
    async def gate_config_set(
        self,
        event: AstrMessageEvent,
        plugin: str,
        key: str,
        value: str,
    ) -> str:
        """在考核等级允许的范围内修改一个 AstrBot 插件配置项。

        Args:
            plugin(string): 插件注册名，例如 astrbot_plugin_moon_vision；改主配置用 cmd_config
            key(string): 配置键，支持点号路径，例如 group_prob_peak
            value(string): 新值，按 JSON 解析（数字/布尔用 JSON 写法，纯文字直接写）
        """
        if err := self._owner_only(event):
            return err
        self._level()
        ok, msg = self._write_config(plugin, key, value)
        if ok:
            try:
                manager = getattr(self.context, "_star_manager", None)
                if manager is not None and plugin not in PROTECTED_PLUGINS and plugin != "cmd_config":
                    await manager.reload(plugin)
                    msg += "\n插件已重载。"
            except Exception as e:
                msg += f"\n（重载失败：{e}）"
        return msg

    @filter.llm_tool(name="gate_persona_set")
    async def gate_persona_set(self, event: AstrMessageEvent, system_prompt: str) -> str:
        """修改默认人格（需要 L2），改前自动备份。

        Args:
            system_prompt(string): 新人格全文
        """
        if err := self._owner_only(event):
            return err
        if self._level() < 2:
            return "人格要 L2 才能动。"
        text = (system_prompt or "").strip()
        if len(text) < 80:
            return "人格太短了，不像话。"
        backup = ""
        try:
            conn = sqlite3.connect(str(PERSONA_DB))
            row = conn.execute(
                "select system_prompt from personas where persona_id='default'"
            ).fetchone()
            if row and row[0]:
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                p = self.backup_dir / f"persona_{ts}.txt"
                p.write_text(row[0], encoding="utf-8")
                backup = str(p)
            conn.close()
        except Exception as e:
            logger.warning(f"{TAG} 人格备份失败：{e}")
        try:
            await self.context.persona_manager.update_persona(
                "default", system_prompt=text
            )
        except Exception as e:
            if backup:
                try:
                    await self.context.persona_manager.update_persona(
                        "default",
                        system_prompt=Path(backup).read_text(encoding="utf-8"),
                    )
                except Exception:
                    pass
            return f"改人格失败：{e}"
        self._event("config_write", 0, "persona.default")
        return f"人格已更新（{len(text)} 字）" + (f"，旧版备份：{backup}" if backup else "")
