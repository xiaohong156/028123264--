# -*- coding: utf-8 -*-
"""CreditGuard 单笔试算的本地 Web 演示（只用 Python 标准库，无额外依赖）。

启动：
    python web/server.py            # 默认 http://127.0.0.1:8000
    python web/server.py --port 8080

页面提供一张申请表：填 23 个字段 → 调用 CreditAgent → 返回违约概率、风险等级、
建议动作与原因码。适合在 GitHub Codespaces 或本机演示"可运行原型"。
"""
from __future__ import annotations

import argparse
import json
import os
import socketserver
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from creditguard.agent import CreditAgent  # noqa: E402

AGENT = CreditAgent()
WEB_ROOT = os.path.join(HERE, "static")

FIELDS = ["ID", "LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE",
          "PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6",
          "BILL_AMT1", "BILL_AMT2", "BILL_AMT3", "BILL_AMT4", "BILL_AMT5", "BILL_AMT6",
          "PAY_AMT1", "PAY_AMT2", "PAY_AMT3", "PAY_AMT4", "PAY_AMT5", "PAY_AMT6"]


def to_record(payload: dict) -> dict:
    """把前端提交的字符串统一转成数值，缺字段保持 None 交给审计技能处理。"""
    record = {}
    for key in FIELDS:
        raw = payload.get(key)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            value = float(raw)
            record[key] = int(value) if value.is_integer() else value
        except ValueError:
            record[key] = raw  # 故意保留非法值，让审计技能给出 non_numeric 标记
    return record


def serialize(result: dict) -> dict:
    reasons = result.get("reasons") or {}
    policy = result.get("policy") or {}
    return {
        "app_id": result.get("app_id"),
        "p": result.get("p"),
        "band": result.get("band"),
        "action": result.get("final_action") or result.get("action"),
        "policy_action": policy.get("action"),
        "rationale": policy.get("rationale"),
        "risk_factors": [x["text"] for x in reasons.get("risk_factors", [])],
        "protective_factors": [x["text"] for x in reasons.get("protective_factors", [])],
        "summary": reasons.get("summary"),
        "flags": result.get("flags", []),
        "audit_status": (result.get("audit") or {}).get("status"),
        "degraded": result.get("degraded", False),
        "thresholds": policy.get("thresholds"),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "CreditGuardDemo/1.0"

    def _send(self, code: int, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            path = "/index.html"
        file_path = os.path.join(WEB_ROOT, path.lstrip("/"))
        if not os.path.isfile(file_path):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        ctype = "text/html; charset=utf-8" if file_path.endswith(".html") else "text/plain; charset=utf-8"
        with open(file_path, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_POST(self):
        if urlparse(self.path).path != "/api/score":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, b'{"error":"invalid json"}', "application/json; charset=utf-8")
            return
        record = to_record(payload)
        try:
            result = AGENT.process(record, app_id=str(record.get("ID", "web-demo")))
            body = json.dumps(serialize(result), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        except Exception as exc:  # 演示页面不能因为单条异常而白屏
            body = json.dumps({"error": "%s: %s" % (type(exc).__name__, exc)},
                              ensure_ascii=False).encode("utf-8")
            self._send(500, body, "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        sys.stdout.write("[web] " + fmt % args + "\n")


class DemoServer(ThreadingHTTPServer):
    """Windows 上主机名含中文时，默认 server_bind 里的 getfqdn 会抛 UnicodeDecodeError，
    这里跳过反向 DNS，直接用监听地址作为 server_name。"""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = port


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    server = DemoServer((args.host, args.port), Handler)
    print("CreditGuard 演示已启动: http://%s:%d  (Ctrl+C 退出)" % (args.host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
