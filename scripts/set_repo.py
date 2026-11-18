# -*- coding: utf-8 -*-
"""把 README / docs 里的 OWNER/REPO 占位符替换成真实仓库地址。

用法：
    python scripts/set_repo.py yourname/credit_guard
它会更新：
    README.md            徽章、clone 命令、Codespaces 链接
    docs/index.html      仓库链接
"""
from __future__ import annotations

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
README = os.path.join(ROOT, "README.md")
INDEX = os.path.join(ROOT, "docs", "index.html")


def rewrite(path: str, replacements):
    text = io.open(path, encoding="utf-8").read()
    for old, new in replacements:
        text = text.replace(old, new)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)


def main():
    if len(sys.argv) != 2 or "/" not in sys.argv[1]:
        print("用法: python scripts/set_repo.py <owner>/<repo>")
        return 1
    slug = sys.argv[1].strip().strip("/")
    owner, repo = slug.split("/", 1)
    pages = "https://%s.github.io/%s/" % (owner, repo)

    rewrite(README, [
        ("OWNER/REPO", slug),
        ("https://github.com/OWNER/REPO", "https://github.com/%s" % slug),
        ("&& cd REPO", "&& cd %s" % repo),
        ("OWNER.github.io/REPO", "%s.github.io/%s" % (owner, repo)),
    ])
    rewrite(INDEX, [
        ("https://github.com/&lt;你的用户名&gt;/&lt;仓库名&gt;", "https://github.com/%s" % slug),
        ("&lt;owner&gt;/&lt;repo&gt;", slug),
        ("&lt;repo&gt;", repo),
    ])
    print("已写入仓库地址:", slug)
    print("GitHub Pages 地址:", pages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
