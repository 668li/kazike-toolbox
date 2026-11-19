"""kazike-toolbox 自检：frontmatter 合法、路由表文件齐全、Prompt 正文结构完整。

用法: python verify.py [原文纯文本路径]
原文路径省略时跳过逐字比对（只做结构检查）。提供原文时只比对 01–12（卡兹克原文），
13–21 为用户投稿，不参与逐字比对。
"""

import re
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
SKILL = BASE / "SKILL.md"
PROMPTS_DIR = BASE / "prompts"
on_disk = {p.name for p in PROMPTS_DIR.glob("*.md")}
EXPECTED_FILES = len(on_disk)
MIN_PROMPTS = 21
ORIGINAL_PREFIXES = {f"{i:02d}" for i in range(1, 13)}

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


if EXPECTED_FILES < MIN_PROMPTS:
    failures.append(f"prompts/ 只有 {EXPECTED_FILES} 个文件，少于最低要求 {MIN_PROMPTS}")


# 1. frontmatter
raw = SKILL.read_text(encoding="utf-8")
check(raw.startswith("---"), "SKILL.md 未以 --- 开头")
m = re.search(r"\n---\s*\n", raw[3:])
if m is None:
    print("FAIL")
    print("  - SKILL.md frontmatter 未闭合")
    sys.exit(1)
fm = yaml.safe_load(raw[3 : m.start() + 3])
if not isinstance(fm, dict):
    fm = {}
check(isinstance(fm, dict), "frontmatter 不是 YAML 映射")
check(fm.get("name") == "kazike-toolbox", f"name 异常: {fm.get('name')!r}")
desc = fm.get("description", "")
check(bool(desc), "description 缺失")
check(len(desc) <= 1024, f"description 超长: {len(desc)}")
check(len(raw[m.start() + 3 :].strip()) > 0, "SKILL.md 正文为空")

# 2. 路由表引用的文件全部存在，且 prompts/ 下没有未被引用的文件
referenced = set(re.findall(r"`prompts/([\w\-.]+\.md)`", raw))
check(len(referenced) == EXPECTED_FILES, f"路由表引用 {len(referenced)} 个文件，应为 {EXPECTED_FILES}")
check(not (referenced - on_disk), f"引用了不存在的文件: {sorted(referenced - on_disk)}")
check(not (on_disk - referenced), f"存在未被引用的文件: {sorted(on_disk - referenced)}")

# 3. 每个 prompt 文件必须有一个 ``` 代码块；模板型需含【】占位符，Role 型需含 # Role 头
def code_block(text: str) -> str:
    blocks = re.findall(r"```\n(.*?)```", text, re.S)
    return blocks[0] if len(blocks) == 1 else ""


bodies = {}
ROLE_PROMPTS = {"11-hidden-talent-excavation.md", "12-life-design.md"}
for name in sorted(referenced):
    text = (BASE / "prompts" / name).read_text(encoding="utf-8")
    body = code_block(text)
    check(bool(body), f"{name}: 缺少唯一的 ``` 代码块")
    if name in ROLE_PROMPTS:
        check(body.lstrip().startswith("# Role"), f"{name}: Role 型 Prompt 缺少 # Role 头")
    else:
        check("【" in body, f"{name}: 代码块内无【】占位符")
    if name[:2] in ORIGINAL_PREFIXES:
        bodies[name] = body

# 4. 与原文逐字比对（去空白后子串匹配）
if len(sys.argv) > 1:
    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    flat_src = re.sub(r"\s+", "", source)
    for name, body in bodies.items():
        # 原文用中文引号，本地文件用直引号，比对时统一
        flat = re.sub(r"\s+", "", body).replace('"', "").replace("“", "").replace("”", "")
        ref = flat_src.replace('"', "").replace("“", "").replace("”", "")
        check(flat in ref, f"{name}: Prompt 正文与原文不一致")
else:
    print("(跳过逐字比对：未提供原文路径)")

if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"OK: frontmatter 合法, {EXPECTED_FILES} 个 Prompt 文件齐全{'、01–12 正文与原文逐字一致' if len(sys.argv) > 1 else ''}")
