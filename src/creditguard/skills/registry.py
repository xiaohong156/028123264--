# -*- coding: utf-8 -*-
"""技能注册表：按 Agent Skills 规范加载 SKILL.md 与 skill.py。

技能目录结构：
    skills/<name>/SKILL.md     # YAML frontmatter（name/description/version/license）
    skills/<name>/skill.py     # 提供 apply(payload) 的纯函数

注册表只做"发现 + 元数据解析 + 调用"，不替技能做业务判断，
这样技能可以独立测试、替换甚至由第三方提供。
"""
from __future__ import annotations

import importlib.util
import os
import re
from typing import Dict, List, Optional


class Skill:
    def __init__(self, name: str, path: str, meta: Dict[str, str], fn):
        self.name = name
        self.path = path
        self.meta = meta
        self.version = meta.get("version", "unknown")
        self.license = meta.get("license", "unknown")
        self.description = meta.get("description", "")
        self._fn = fn

    def apply(self, payload: Dict) -> Dict:
        return self._fn(payload)

    def __repr__(self) -> str:
        return "<Skill %s v%s>" % (self.name, self.version)


def _parse_frontmatter(text: str) -> Dict[str, str]:
    """解析 SKILL.md 顶部的 YAML frontmatter。

    优先用 PyYAML（与 Agent Skills 规范一致）；环境里没有 yaml 时退回
    "key: value" 的简单解析，保证技能仍可加载。
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not match:
        return {}
    block = match.group(1)
    try:
        import yaml
        meta = yaml.safe_load(block)
        if isinstance(meta, dict):
            data = {str(k): ("" if v is None else str(v)) for k, v in meta.items() if k != "metadata"}
            nested = meta.get("metadata") or {}
            if isinstance(nested, dict):
                for k, v in nested.items():
                    data.setdefault(str(k), str(v))
            return data
    except Exception:
        pass
    meta = {}
    for line in block.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def load_skill(skill_dir: str) -> Skill:
    skill_md = os.path.join(skill_dir, "SKILL.md")
    skill_py = os.path.join(skill_dir, "skill.py")
    if not os.path.exists(skill_md) or not os.path.exists(skill_py):
        raise FileNotFoundError("技能目录缺少 SKILL.md 或 skill.py: %s" % skill_dir)

    with open(skill_md, "r", encoding="utf-8") as f:
        meta = _parse_frontmatter(f.read())
    name = meta.get("name") or os.path.basename(skill_dir)

    # 用文件路径加载，避免与第三方包重名；每次加载都重新执行模块，
    # 便于测试时用临时目录覆盖技能。
    spec = importlib.util.spec_from_file_location("creditguard_skill_%s" % name.replace("-", "_"), skill_py)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "apply", None)
    if not callable(fn):
        raise AttributeError("技能 %s 未提供 apply(payload)" % name)
    return Skill(name=name, path=skill_dir, meta=meta, fn=fn)


class SkillRegistry:
    def __init__(self, skills_root: Optional[str] = None):
        self.root = skills_root or os.path.join(os.path.dirname(os.path.abspath(__file__)))
        self._skills: Dict[str, Skill] = {}

    def discover(self) -> "SkillRegistry":
        for entry in sorted(os.listdir(self.root)):
            path = os.path.join(self.root, entry)
            if os.path.isdir(path) and os.path.exists(os.path.join(path, "SKILL.md")):
                skill = load_skill(path)
                self._skills[skill.name] = skill
        return self

    def get(self, name: str) -> Skill:
        if name not in self._skills:
            raise KeyError("未注册的技能: %s（可用: %s）" % (name, list(self._skills)))
        return self._skills[name]

    def names(self) -> List[str]:
        return list(self._skills)

    def manifest(self) -> List[Dict[str, str]]:
        return [{"name": s.name, "version": s.version, "license": s.license,
                 "description": s.description} for s in self._skills.values()]
