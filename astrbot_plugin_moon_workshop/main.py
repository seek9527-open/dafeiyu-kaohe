# -*- coding: utf-8 -*-
"""溟月的工坊：给溟月一双只在自己地盘上动手的手。

工具（函数调用）：
  ws_list_files     列目录
  ws_read_file      读文件
  ws_write_file     写文件（改前自动备份 + 写后自动检查）
  ws_rollback       回滚到上一份备份
  ws_check_syntax   语法检查
  ws_reload_plugin  重载一个插件

安全边界：
  - 只允许在 /AstrBot/data/plugins/ 与工坊的 workbench 目录里读写
  - 只允许 .py/.json/.md/.txt，单文件 ≤ max_bytes（默认 2MB）
  - 写前备份到 plugin_data/moon_workshop/backups/<插件>/<时间戳>/
  - .py 写完自动 py_compile，失败自动恢复原文件
  - 只允许管理员使用；一次对话最多写 max_files_per_turn 个文件
  - 禁止改本插件自身、cmd_config.json、data_v4.db、.env
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig

PLUGIN_NAME = "astrbot_plugin_moon_workshop"
DISPLAY_NAME = "溟月的工坊"

DATA_ROOT = Path("/AstrBot/data")
PLUGINS_ROOT = (DATA_ROOT / "plugins").resolve()
WORKSHOP_DATA = (DATA_ROOT / "plugin_data" / PLUGIN_NAME).resolve()
WORKBENCH_ROOT = (WORKSHOP_DATA / "workbench").resolve()
BACKUP_ROOT = (WORKSHOP_DATA / "backups").resolve()
EVENTS_FILE = (WORKSHOP_DATA / "events.jsonl").resolve()
DENY_BUCKETS = {"astrbot_plugin_moon_gate"}

ALLOWED_SUFFIXES = {".py", ".json", ".md", ".txt"}
DENY_NAMES = {"cmd_config.json", "data_v4.db", ".env", "astrbot_plugin_moon_workshop"}

MAX_NOTE_CHARS = 300


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sandbox_tar(plugin_dir: Path, max_bytes: int) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in sorted(plugin_dir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(plugin_dir)
            if "__pycache__" in rel.parts:
                continue
            if rel.parts and rel.parts[0] in {"data", ".git", "vendor"}:
                continue
            if p.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            if p.stat().st_size > max_bytes:
                continue
            info = tar.gettarinfo(str(p), arcname=str(rel))
            with p.open("rb") as f:
                tar.addfile(info, f)
    return buf.getvalue()


def _sandbox_post(plugin_dir: Path, url: str, token: str, max_bytes: int, timeout: int = 90) -> dict:
    tar_bytes = _sandbox_tar(plugin_dir, max_bytes)
    payload = json.dumps({"tar": base64.b64encode(tar_bytes).decode(), "timeout": 60}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"X-Token": token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@register(PLUGIN_NAME, "溟月", "给溟月一双只在自己地盘上动手的手：受限读写 + 自动备份 + 语法检查 + 回滚", "1.0.0")
class MoonWorkshop(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.conf = config or {}
        self.max_files_per_turn = int(self._conf("max_files_per_turn", 3))
        self.backup_keep = int(self._conf("backup_keep", 20))
        self.max_bytes = int(self._conf("max_bytes", 2 * 1024 * 1024))
        self.notes_name = str(self._conf("notes_file", "notes.md") or "notes.md")
        self._write_marks: dict[str, list[float]] = {}
        WORKBENCH_ROOT.mkdir(parents=True, exist_ok=True)
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        logger.info(f"[moon_workshop] {DISPLAY_NAME}已加载")

    def _conf(self, key: str, default):
        if isinstance(self.conf, dict):
            return self.conf.get(key, default)
        try:
            return self.conf.get(key, default)
        except Exception:
            return default

    # ---------------- 路径与备份 ----------------

    def _owner_only(self, event: AstrMessageEvent) -> str | None:
        try:
            if event.is_admin():
                return None
        except Exception:
            pass
        return "这把手只给主人用，别人碰不得。"

    def _allowed_path(self, raw: str, *, write: bool = False) -> tuple[Path | None, str]:
        raw = (raw or "").strip().strip('"').strip("'")
        if not raw:
            return None, "路径是空的。"
        p = Path(raw)
        if not p.is_absolute():
            p = WORKBENCH_ROOT / p
        try:
            rp = p.resolve()
        except Exception as e:
            return None, f"路径解析失败：{e}"

        if rp.suffix.lower() not in ALLOWED_SUFFIXES:
            return None, "只允许 .py / .json / .md / .txt 文件。"
        if rp.name in DENY_NAMES:
            return None, f"「{rp.name}」是红线文件，不能由本鲸动。"

        if rp == PLUGINS_ROOT:
            return None, "这是插件根目录，不是文件。"
        if rp == WORKBENCH_ROOT:
            return None, "这是工位根目录，不是文件。"

        under_plugins = PLUGINS_ROOT in rp.parents
        under_workbench = WORKBENCH_ROOT in rp.parents
        under_workshop = WORKSHOP_DATA in rp.parents
        if write:
            if not (under_plugins or under_workbench):
                return None, "只能动 /AstrBot/data/plugins 或工坊 workbench 里的文件，别处不行。"
        else:
            if not (under_plugins or under_workbench or under_workshop):
                return None, "只能读插件目录、工坊 workbench 或工坊数据（笔记/备份），别处不行。"

        if write and under_plugins and rp.relative_to(PLUGINS_ROOT).parts[:1] == (PLUGIN_NAME,):
            return None, "本鲸不能改自己这双手，要改让主人来。"
        if write and under_plugins and rp.relative_to(PLUGINS_ROOT).parts[:1] and rp.relative_to(PLUGINS_ROOT).parts[0] in DENY_BUCKETS:
            return None, "考核的手续不在工坊里办，那个插件不能碰。"
        return rp, ""

    def _plugin_bucket(self, rp: Path) -> str:
        try:
            return rp.relative_to(PLUGINS_ROOT).parts[0]
        except Exception:
            return "workbench"

    def _rel_path(self, rp: Path) -> Path:
        try:
            return rp.relative_to(PLUGINS_ROOT)
        except ValueError:
            try:
                return rp.relative_to(WORKBENCH_ROOT)
            except ValueError:
                return rp.relative_to(WORKSHOP_DATA)

    def _prune_backups(self, bucket: str) -> None:
        root = BACKUP_ROOT / bucket
        if not root.is_dir():
            return
        dirs = sorted([d for d in root.iterdir() if d.is_dir()], key=lambda d: d.name)
        for old in dirs[: max(0, len(dirs) - self.backup_keep)]:
            shutil.rmtree(old, ignore_errors=True)

    def _backup(self, rp: Path) -> str:
        if not rp.exists() or not rp.is_file():
            return ""
        bucket = self._plugin_bucket(rp)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        dest = BACKUP_ROOT / bucket / ts
        target = dest / self._rel_path(rp)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rp, target)
        manifest = BACKUP_ROOT / bucket / "manifest.jsonl"
        try:
            with manifest.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": ts,
                    "path": str(rp),
                    "backup": str(target),
                    "sha256": _sha256(rp),
                    "size": rp.stat().st_size,
                    "at": _now_text(),
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[moon_workshop] 写 manifest 失败：{e}")
        self._prune_backups(bucket)
        return str(target)

    def _append_note(self, line: str) -> None:
        try:
            notes = WORKSHOP_DATA / self.notes_name
            with notes.open("a", encoding="utf-8") as f:
                f.write(f"- {_now_text()} {line[:MAX_NOTE_CHARS]}\n")
        except Exception as e:
            logger.warning(f"[moon_workshop] 写笔记失败：{e}")

    def _event(self, kind: str, detail: str = "") -> None:
        try:
            with EVENTS_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": _now_text(),
                    "kind": kind,
                    "path": detail[:200],
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[moon_workshop] 写账本失败：{e}")

    def _turn_writes(self, umo: str) -> int:
        now = time.time()
        marks = [t for t in self._write_marks.get(umo, []) if now - t < 600]
        self._write_marks[umo] = marks
        return len(marks)

    def _mark_write(self, umo: str) -> None:
        self._write_marks.setdefault(umo, []).append(time.time())

    # ---------------- 检查 ----------------

    def _check_file(self, rp: Path) -> tuple[bool, str]:
        suffix = rp.suffix.lower()
        if suffix == ".py":
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(rp)],
                    capture_output=True, text=True, timeout=30,
                )
            except Exception as e:
                return False, f"语法检查没跑起来：{e}"
            if proc.returncode != 0:
                out = (proc.stderr or proc.stdout or "").strip()
                return False, out[:1500] or "py_compile 失败但没输出。"
            return True, "py_compile 通过"
        if suffix == ".json":
            try:
                json.loads(rp.read_text(encoding="utf-8"))
                return True, "JSON 合法"
            except Exception as e:
                return False, f"JSON 不合法：{e}"
        return True, "非代码文件，跳过检查"

    # ---------------- 工具 ----------------

    @filter.llm_tool(name="ws_list_files")
    async def ws_list_files(self, event: AstrMessageEvent, path: str = "") -> str:
        """在溟月自己的地盘里列目录（插件目录或工坊 workbench）。

        Args:
            path(string): 目录路径；相对路径按 workbench 解析，留空则列出工位
        """
        if err := self._owner_only(event):
            return err
        target = path.strip() if path else str(WORKBENCH_ROOT)
        p = Path(target)
        if not p.is_absolute():
            p = WORKBENCH_ROOT / p
        try:
            rp = p.resolve()
        except Exception as e:
            return f"路径解析失败：{e}"
        if not (rp == PLUGINS_ROOT or rp == WORKBENCH_ROOT or PLUGINS_ROOT in rp.parents or WORKBENCH_ROOT in rp.parents):
            return "只能看插件目录或 workbench 里面。"
        if not rp.is_dir():
            return f"不是目录：{rp}"
        lines = []
        for child in sorted(rp.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
            mark = "/" if child.is_dir() else ""
            size = "" if child.is_dir() else f"  {child.stat().st_size}B"
            lines.append(f"{child.name}{mark}{size}")
        return f"{rp}\n" + ("\n".join(lines) if lines else "（空）")

    @filter.llm_tool(name="ws_read_file")
    async def ws_read_file(self, event: AstrMessageEvent, path: str, max_chars: int = 4000) -> str:
        """读取溟月地盘里的一个文本文件。

        Args:
            path(string): 文件路径
            max_chars(int): 最多返回多少个字符，默认 4000
        """
        if err := self._owner_only(event):
            return err
        rp, err = self._allowed_path(path)
        if not rp:
            return err
        if not rp.is_file():
            return f"没有这个文件：{rp}"
        if rp.stat().st_size > self.max_bytes:
            return "文件超过大小上限，先别读了。"
        text = rp.read_text(encoding="utf-8", errors="replace")
        limit = max(200, min(int(max_chars or 4000), 20000))
        if len(text) > limit:
            text = text[:limit] + f"\n……（后面还有 {len(text) - limit} 字）"
        return text

    @filter.llm_tool(name="ws_write_file")
    async def ws_write_file(self, event: AstrMessageEvent, path: str, content: str, reason: str = "") -> str:
        """写一个文件到溟月的地盘：改前自动备份，写完自动做语法/JSON 检查，失败自动还原。

        Args:
            path(string): 要写的文件路径
            content(string): 新内容全文
            reason(string): 为什么改，一句话，会记进笔记
        """
        if err := self._owner_only(event):
            return err
        rp, err = self._allowed_path(path, write=True)
        if not rp:
            return err
        if not content or not content.strip():
            return "内容是空的，不写。"
        data = content.encode("utf-8")
        if len(data) > self.max_bytes:
            return "内容超过大小上限，没写。"
        umo = getattr(event, "unified_msg_origin", "") or ""
        if self._turn_writes(umo) >= self.max_files_per_turn:
            return f"这一轮已经改了 {self.max_files_per_turn} 个文件，先歇口气，跟主人说说改了啥。"

        backup_path = self._backup(rp)
        existed = rp.exists()
        try:
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(content, encoding="utf-8", newline="\n")
        except Exception as e:
            if backup_path and existed:
                try:
                    shutil.copy2(backup_path, rp)
                except Exception:
                    pass
            return f"写的时候出错了：{e}"

        ok, check_msg = self._check_file(rp)
        if not ok:
            self._event("syntax_fail", str(self._rel_path(rp)))
            if backup_path and existed:
                try:
                    shutil.copy2(backup_path, rp)
                    self._append_note(f"写入 {self._rel_path(rp)} 未通过检查，已还原：{check_msg[:80]}")
                    return f"检查没过，已经还原成原样。报错：\n{check_msg}"
                except Exception as e:
                    return f"检查没过，还原也失败了（{e}）。报错：\n{check_msg}"
            rp.unlink(missing_ok=True)
            return f"检查没过，文件没留下。报错：\n{check_msg}"

        self._mark_write(umo)
        self._append_note(
            f"写入 {self._rel_path(rp)}（{len(data)}B）{'，原因：' + reason if reason else ''}；{check_msg}"
        )
        self._event("write_ok", str(self._rel_path(rp)))
        backup_note = f"\n备份：{backup_path}" if backup_path else ""
        return f"写好了：{self._rel_path(rp)}（{check_msg}）{backup_note}"

    @filter.llm_tool(name="ws_rollback")
    async def ws_rollback(self, event: AstrMessageEvent, path: str, backup: str = "", reason: str = "") -> str:
        """把一个文件还原到最近一次（或指定一次）备份。

        Args:
            path(string): 要还原的文件路径
            backup(string): 备份点时间戳，留空则用最近一次
            reason(string): 为什么回滚；写「演练」则不计失败、只记一次演练
        """
        if err := self._owner_only(event):
            return err
        rp, err = self._allowed_path(path, write=True)
        if not rp:
            return err
        bucket = self._plugin_bucket(rp)
        root = BACKUP_ROOT / bucket
        if not root.is_dir():
            return "没有备份可还原。"
        dirs = sorted([d for d in root.iterdir() if d.is_dir()], key=lambda d: d.name)
        if not dirs:
            return "这个文件没有备份点（它是新写的，之前没有旧版本），回滚不了。"
        if backup:
            dirs = [d for d in dirs if d.name == backup.strip()]
            if not dirs:
                return "没找到这个备份点。"
        chosen = dirs[-1]
        rel = self._rel_path(rp)
        src = chosen / rel
        if not src.is_file():
            return "这个备份点里没有该文件。"
        self._backup(rp)
        shutil.copy2(src, rp)
        self._check_file(rp)
        self._append_note(f"回滚 {rel} 到备份 {chosen.name}")
        if "演练" in (reason or ""):
            self._event("drill_ok", str(rel))
            return f"已回滚（演练）：{rel} ← {chosen.name}"
        self._event("rollback_ok", str(rel))
        return f"已回滚：{rel} ← {chosen.name}"

    @filter.llm_tool(name="ws_check_syntax")
    async def ws_check_syntax(self, event: AstrMessageEvent, path: str) -> str:
        """检查一个文件的语法（.py 编译检查，.json 合法性检查）。

        Args:
            path(string): 文件路径
        """
        if err := self._owner_only(event):
            return err
        rp, err = self._allowed_path(path)
        if not rp:
            return err
        if not rp.is_file():
            return f"没有这个文件：{rp}"
        ok, msg = self._check_file(rp)
        return ("通过：" if ok else "没过：") + msg

    @filter.llm_tool(name="ws_sandbox_test")
    async def ws_sandbox_test(self, event: AstrMessageEvent, path: str) -> str:
        """在一次性沙箱容器里检查一个插件目录：语法、JSON 合法性、以及 tests/ 里的单测。沙箱没有网络、不挂宿主目录、用完即毁。

        Args:
            path(string): 插件目录路径，例如 /AstrBot/data/plugins/astrbot_plugin_moon_concise
        """
        if err := self._owner_only(event):
            return err
        rp, err = self._allowed_path(path)
        if not rp:
            return err
        if not rp.is_dir():
            return "沙箱只收插件目录。"
        url = str(self._conf("sandbox_url", "") or "").strip()
        token = str(self._conf("sandbox_token", "") or "").strip()
        if not url or not token:
            return "沙箱还没配好：让主人把 sandbox_url 和 sandbox_token 填进工坊配置。"
        rel = str(self._rel_path(rp))
        try:
            resp = await asyncio.to_thread(_sandbox_post, rp, url, token, self.max_bytes)
        except Exception as e:
            self._event("sandbox_fail", rel)
            return f"沙箱没回应：{e}"
        ok = bool(resp.get("ok"))
        self._event("sandbox_ok" if ok else "sandbox_fail", rel)
        head = "沙箱通过" if ok else "沙箱没过"
        log = str(resp.get("log", ""))[-2500:]
        return f"{head}\n{log}"

    @filter.llm_tool(name="ws_reload_plugin")
    async def ws_reload_plugin(self, event: AstrMessageEvent, plugin: str = "") -> str:
        """重载一个插件，让刚才的改动生效。

        Args:
            plugin(string): 插件注册名，例如 astrbot_plugin_poke_reaction；留空表示重载全部插件
        """
        if err := self._owner_only(event):
            return err
        manager = getattr(self.context, "_star_manager", None)
        if manager is None:
            return "后台的手还没接上，重载失败，让主人去面板点重启吧。"
        name = plugin.strip() or None
        try:
            result = await manager.reload(name)
        except Exception as e:
            return f"重载出错：{e}"
        self._append_note(f"重载插件 {name or '全部'} → {result}")
        return f"重载完成：{result}"
