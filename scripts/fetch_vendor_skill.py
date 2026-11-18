# -*- coding: utf-8 -*-
"""下载要复用的开源技能（anthropics/skills, Apache-2.0）。

用 jsDelivr 镜像获取指定 tag 的文件，并把 commit 号记录到 VENDOR.md，
方便审计"来源/版本/许可证"。
"""
import json
import os
import urllib.request

BASE = "https://cdn.jsdelivr.net/gh/anthropics/skills@main/"
API = "https://api.github.com/repos/anthropics/skills/commits/main"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "vendor", "anthropic-skills"))

FILES = [
    "skills/skill-creator/SKILL.md",
    "skills/skill-creator/LICENSE.txt",
    "skills/skill-creator/scripts/quick_validate.py",
    "skills/skill-creator/scripts/package_skill.py",
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    os.makedirs(OUT, exist_ok=True)
    for rel in FILES:
        dest = os.path.join(OUT, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            print("[skip]", rel)
            continue
        data = fetch(BASE + rel)
        with open(dest, "wb") as f:
            f.write(data)
        print("[ok]", rel, len(data), "bytes")

    try:
        commit = json.loads(fetch(API).decode("utf-8"))
        sha = commit["sha"]
    except Exception as exc:
        sha = "unknown (%s)" % exc
    with open(os.path.join(OUT, "VENDOR.md"), "w", encoding="utf-8") as f:
        f.write("# 复用的开源技能\n\n")
        f.write("- 仓库：anthropics/skills（https://github.com/anthropics/skills）\n")
        f.write("- 许可证：Apache License 2.0（见 skills/skill-creator/LICENSE.txt）\n")
        f.write("- 引用 commit：`%s`\n" % sha)
        f.write("- 获取方式：jsDelivr CDN 镜像（%s）\n" % BASE)
        f.write("- 用途：按 Agent Skills 规范编写本项目 3 个技能，\n"
                "  并用其 quick_validate.py 做结构校验（见 tools/skill_lint.py）。\n")
    print("[ok] VENDOR.md", sha)


if __name__ == "__main__":
    main()
