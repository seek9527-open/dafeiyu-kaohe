# 安全策略

## 支持范围

只维护 `main` 分支上的最新版本。历史版本不单独发安全补丁。

## 报告漏洞

**请不要直接开公开 Issue。**

优先使用 GitHub 的 [私密漏洞报告](https://github.com/seek9527-open/dafeiyu-kaohe/security/advisories/new)；
如果不可用，请通过仓库主页所列联系方式私下联系维护者，并在标题注明 `[SECURITY]`。

我们会在 72 小时内确认收到，并在修复后于 `CHANGELOG.md` 与你公开致谢（除非你要求匿名）。

## 设计边界（重要）

本插件是**自律与审计**工具，不是安全沙箱：

- 红线关键词只能拦住「手滑与明显越界」，不能拦住恶意代码。
- 工坊拥有插件目录写权限，理论上存在绕过考核的路径。
- 真正的隔离应由容器、文件系统权限、AstrBot 管理员机制共同保证。

如果你把本插件当成硬性安全边界使用，请重新评估部署架构。

## 部署建议

- 不要让 AI 获得 `cmd_config.json` 的直接写权限；L3 只应保留极少数白名单键。
- 定期备份 `data/plugin_data/astrbot_plugin_moon_gate/`。
- 发现异常升级或计分，先查 `gate.json` 的 `events` 与工坊 `events.jsonl` 是否一致。
