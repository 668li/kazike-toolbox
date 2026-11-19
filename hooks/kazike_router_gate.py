"""卡兹克路由闸门 —— 用户点名 kazike-toolbox 或要求选提示词时，强制注入路由层。

问题：ROUTER.md 默认不会被模型读取，路由机制容易荒废。
做法：两层钩子：
  · UserPromptSubmit：匹配用户消息里的触发词；
  · PreToolUse（Skill）：用户从 UI/斜杠直接调用 skill 时也能兜住。
触发后的行为：
  · 用户在选提示词（该用哪条/选一条/用什么思路）→ 注入索引 + ROUTER.md 全文；
  · 只是点名卡兹克工具箱 → 注入「任务书直通」闸门卡 + 索引。

安装位置：本文件在 <skill>/hooks/ 下，默认从 ~/.agents/skills/kazike-toolbox 读取规则。
可用环境变量 KAZIKE_SKILL_DIR 覆盖 skill 目录，KAZIKE_ROUTER_LOG 覆盖日志路径。

不变量：读不到输入 / 文件缺失 / 任何异常 → exit 0，绝不阻塞会话。
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(os.environ.get(
    "KAZIKE_SKILL_DIR",
    Path.home() / ".agents" / "skills" / "kazike-toolbox",
))
ROUTER = SKILL_DIR / "ROUTER.md"
SKILL = SKILL_DIR / "SKILL.md"
DELEGATION = SKILL_DIR / "DELEGATION.md"
LOG = Path(os.environ.get(
    "KAZIKE_ROUTER_LOG",
    Path.home() / ".zcode" / "hooks" / "kazike_router_gate.log",
))

ROUTER_TRIGGER = re.compile(r"(该用哪条|用哪条|选一条|帮我选|选个提示词|哪个提示词|用什么思路|路由一下)")
TOOLBOX_TRIGGER = re.compile(r"(卡兹克|kazike)", re.I)

DIRECT_CARD = """\
【卡兹克路由闸门】检测到本消息使用卡兹克工具箱。先判输入类型：
1. 完整任务书（明确对象 + 动作 + 交付物）→ 直接按 SKILL.md 索引执行对应 prompt；不路由、不问诊，缺的上下文默认当前仓库/最近 30 天，并在开头声明。
2. 用户明确要「选一条/该用哪条/用什么思路」→ 必须先读 ROUTER.md 全文，再按路由执行。
3. 其他模糊请求 → 只问一个最关键的问题。
硬门禁：未读 prompts/<文件>.md 的代码块就回答 = 违规。
回答开头必须先写一行路由声明：`路由：任务书直通 → <编号>（子代理/主线程）` 或 `路由：模糊请求 → 先问一个问题`；没有这行视为违规。
"""

DELEGATION_FALLBACK = "标「子代理」的条目必须派 Agent 执行；主线程只做打包/派发/验收/转述，不得自己代跑分析。"


def read_payload() -> dict:
    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def all_strings(obj, acc: list[str]) -> None:
    if isinstance(obj, str):
        acc.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            all_strings(value, acc)
    elif isinstance(obj, list):
        for value in obj:
            all_strings(value, acc)


def extract_prompt(payload: dict) -> str:
    for key in ("prompt", "userPrompt", "user_prompt", "text", "message", "input"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    for value in payload.values():
        if isinstance(value, str) and len(value) > 4:
            return value
    return ""


def read_modes() -> str:
    try:
        text = DELEGATION.read_text(encoding="utf-8")
    except Exception:
        return DELEGATION_FALLBACK
    start = text.find("<!-- MODES:START -->")
    end = text.find("<!-- MODES:END -->")
    if start < 0 or end < 0:
        return DELEGATION_FALLBACK
    block = text[start + len("<!-- MODES:START -->"):end].strip()
    return block + "\n" + DELEGATION_FALLBACK


def read_index() -> str:
    try:
        text = SKILL.read_text(encoding="utf-8")
    except Exception:
        return ""
    start = text.find("<!-- INDEX:START -->")
    end = text.find("<!-- INDEX:END -->")
    if start >= 0 and end >= 0:
        return text[start + len("<!-- INDEX:START -->"):end].strip()
    start = text.find("## 提示语索引")
    end = text.find("后两条", start)
    if start < 0 or end < 0:
        return ""
    return text[start:end].strip()


def read_router_context() -> str:
    try:
        router = ROUTER.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    if not router:
        return ""
    index = read_index()
    return (
        "【卡兹克显式路由·强制】用户要求选择提示词。以下是提示语索引与 ROUTER.md 全文，必须按它执行；"
        "读对应的 prompts/<文件>.md 代码块原文后再回答。"
        "回答开头必须先写一行「路由：<编号/组合>（理由，子代理/主线程）」；没有这行视为违规。\n\n"
        + index + "\n\n" + read_modes() + "\n\n" + router
    )


def log(mode: str, text: str) -> None:
    try:
        line = "%s\t%s\tlen=%d\n" % (
            datetime.datetime.now().isoformat(timespec="seconds"),
            mode,
            len(text),
        )
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def emit(context: str, event: str = "UserPromptSubmit") -> None:
    out = json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": context,
        }
    }, ensure_ascii=False)
    sys.stdout.buffer.write((out + "\n").encode("utf-8"))
    sys.exit(0)


def main() -> None:
    payload = read_payload()
    if not payload:
        sys.exit(0)

    if "--pretool" in sys.argv:
        strings: list[str] = []
        all_strings(payload, strings)
        joined = "\n".join(strings)
        if not re.search(r"(kazike|卡兹克)", joined, re.I):
            sys.exit(0)
        log("pretool", joined)
        if ROUTER_TRIGGER.search(joined):
            context = read_router_context()
            if context:
                emit(context, "PreToolUse")
        index = read_index()
        emit(DIRECT_CARD + "\n" + read_modes() + ("\n" + index if index else ""), "PreToolUse")

    text = extract_prompt(payload)
    if not text:
        sys.exit(0)

    if ROUTER_TRIGGER.search(text):
        context = read_router_context()
        if context:
            log("router", text)
            emit(context)
        log("router-missing", text)
        sys.exit(0)

    if TOOLBOX_TRIGGER.search(text):
        log("toolbox", text)
        index = read_index()
        emit(DIRECT_CARD + "\n" + read_modes() + ("\n" + index if index else ""))

    sys.exit(0)


if __name__ == "__main__":
    main()
