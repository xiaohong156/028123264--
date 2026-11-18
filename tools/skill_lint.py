# -*- coding: utf-8 -*-
"""用复用的开源校验器检查本项目的 3 个技能（SKILL.md 结构/命名/描述长度）。

复用来源：anthropics/skills（Apache-2.0）skills/skill-creator/scripts/quick_validate.py
适配说明（原脚本无法直接在 Windows 中文环境运行）：
1. 原脚本用 ``Path.read_text()`` 读 SKILL.md，未指定编码；在 Windows 上默认 cp936，
   遇到中文内容会抛 UnicodeDecodeError。这里临时把 Path.read_text 的默认编码
   固定为 UTF-8，再调用原函数，原校验逻辑一行未改。
2. 原脚本只接受 name/description/license/metadata 等允许字段，因此本项目把
   version/inputs/outputs 放进 metadata 下（见各 SKILL.md）。

用法：
    python tools/skill_lint.py            # 校验 src/creditguard/skills 下全部技能
    python tools/skill_lint.py <dir>      # 校验单个技能目录
"""
from __future__ import annotations

import os
import pathlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
VENDOR = os.path.join(ROOT, "vendor", "anthropic-skills", "skills", "skill-creator", "scripts")
SKILLS_DIR = os.path.join(ROOT, "src", "creditguard", "skills")

sys.path.insert(0, VENDOR)

import quick_validate  # noqa: E402  （复用开源脚本）

_ORIGINAL_READ_TEXT = pathlib.Path.read_text


def _read_text_utf8(self, encoding=None, errors=None):
    """Windows 下默认 cp936，这里强制 UTF-8，避免中文 SKILL.md 读取失败。"""
    return _ORIGINAL_READ_TEXT(self, encoding=encoding or "utf-8", errors=errors)


def validate(skill_dir: str):
    pathlib.Path.read_text = _read_text_utf8
    try:
        return quick_validate.validate_skill(skill_dir)
    finally:
        pathlib.Path.read_text = _ORIGINAL_READ_TEXT


def iter_skills(root: str):
    for entry in sorted(os.listdir(root)):
        path = os.path.join(root, entry)
        if os.path.isdir(path) and os.path.exists(os.path.join(path, "SKILL.md")):
            yield path


def main(argv=None):
    argv = argv or sys.argv[1:]
    targets = [argv[0]] if argv else list(iter_skills(SKILLS_DIR))
    failed = 0
    for path in targets:
        ok, message = validate(path)
        name = os.path.basename(path)
        if ok:
            print("[PASS] %-20s %s" % (name, message))
        else:
            failed += 1
            print("[FAIL] %-20s %s" % (name, message))
    print("\n共 %d 个技能，失败 %d 个" % (len(targets), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
