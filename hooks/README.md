# 可选：路由闸门 Hook

不装 hook 也能用这个 skill；装了，模型就不能跳过 `ROUTER.md`。

Hook 做两件事：

- `UserPromptSubmit`：消息里出现「卡兹克 / kazike」或「选一条 / 该用哪条 / 用什么思路」时，注入提示语索引 + 路由/分工规则；
- `PreToolUse(Skill)`：用户从 UI 或斜杠直接调用 skill 时，同样注入，防止绕过。

## 注册示例

把 `<SKILL_DIR>` 换成你的实际安装目录，例如 `C:/Users/你的用户名/.agents/skills/kazike-toolbox`。

```json
{
  "hooks": {
    "enabled": true,
    "events": {
      "UserPromptSubmit": [
        {
          "matcher": ".*",
          "hooks": [
            {
              "type": "command",
              "command": "python \"<SKILL_DIR>/hooks/kazike_router_gate.py\"",
              "timeoutMs": 5000
            }
          ]
        }
      ],
      "PreToolUse": [
        {
          "matcher": "Skill",
          "hooks": [
            {
              "type": "command",
              "command": "python \"<SKILL_DIR>/hooks/kazike_router_gate.py\" --pretool",
              "timeoutMs": 5000
            }
          ]
        }
      ]
    }
  }
}
```

## 环境变量

- `KAZIKE_SKILL_DIR`：skill 安装目录，默认 `~/.agents/skills/kazike-toolbox`。
- `KAZIKE_ROUTER_LOG`：日志路径，默认 `~/.zcode/hooks/kazike_router_gate.log`。

## 验证

重启客户端后，发一句：

```
用卡兹克工具箱帮我选一条：我纠结 A 还是 B
```

看日志是否新增一行 `router\tlen=...`。没有记录，说明 hook 没加载或路径不对。
