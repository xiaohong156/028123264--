# -*- coding: utf-8 -*-
"""CreditGuard Agent：任务编排、状态管理、人机协作与审计日志。

一次申请的处理流程（每一步都有独立的状态与日志）：

    RECEIVED → AUDIT → [退回补件]
             → FEATURE → SCORE → EXPLAIN → POLICY
             → [REVIEW] → DECIDED → EXPORTED

设计原则
--------
* 每个步骤只做一件事，失败可定位：审计失败不会拖垮整批，
  单条记录失败会被隔离并在汇总里计数。
* 所有"建议拒绝"都必须经过人工确认；Agent 不会自动拒贷。
* 模型缺失时进入降级模式（规则评分），并在结果里显式标注，
  而不是静默失败。
* 全流程写 JSONL 事件日志，可直接作为审计材料。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

import numpy as np

from . import schema
from .ml import data as D
from .ml.model import LinearScorecard
from .skills.registry import SkillRegistry
from .tools import io as T

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
DEFAULT_MODEL = os.path.join(PROJECT_ROOT, "models", "logreg_v1.json")


class EventLogger:
    """把 Agent 的每一步写成 JSONL，便于复现与审计。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.records: List[Dict] = []
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            open(path, "a", encoding="utf-8").close()

    def log(self, app_id, step: str, status: str, detail: str = "", **extra):
        event = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "app_id": app_id,
            "step": step,
            "status": status,
            "detail": detail,
            **extra,
        }
        self.records.append(event)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _clamp(value: float, lo: float, hi: float) -> float:
    return float(min(max(value, lo), hi))


class CreditAgent:
    def __init__(self, model_path: str = DEFAULT_MODEL, skills_root: Optional[str] = None,
                 logger: Optional[EventLogger] = None):
        self.registry = SkillRegistry(skills_root).discover()
        self.logger = logger or EventLogger()
        self.model_path = model_path
        self.card: Optional[LinearScorecard] = None
        self.degraded = False
        try:
            self.card = LinearScorecard.load(model_path)
        except Exception as exc:  # 模型缺失/损坏 → 降级，而不是崩溃
            self.degraded = True
            self.logger.log("-", "LOAD_MODEL", "degraded", str(exc))

    # ------------------------------------------------------------------
    # 单条申请
    # ------------------------------------------------------------------
    def process(self, record: Dict, interactive: bool = False,
                reviewer: Optional[Callable[[Dict], Optional[str]]] = None,
                app_id: Optional[str] = None) -> Dict:
        t0 = time.time()
        app_id = app_id or str(record.get("ID", "unknown"))
        result = {
            "app_id": app_id,
            "degraded": self.degraded,
            "flags": [],
            "status": "received",
        }

        # 1) 数据审计
        audit = self.registry.get("credit-data-audit").apply({"records": [record]})
        rec_audit = audit["records"][0]
        result["audit"] = rec_audit
        result["flags"] = list(rec_audit["flags"])
        self.logger.log(app_id, "AUDIT", rec_audit["status"], ",".join(rec_audit["flags"]))
        if rec_audit["status"] == "error":
            result.update({
                "status": "rejected",
                "band": "C",
                "action": "退回补件",
                "p": None,
                "reasons": None,
                "review_required": True,
                "final_action": "退回补件",
                "latency_ms": round((time.time() - t0) * 1000, 1),
            })
            return result

        # 2) 特征
        try:
            feats = D.record_to_features(record)
        except Exception as exc:
            self.logger.log(app_id, "FEATURE", "error", str(exc))
            result.update({"status": "error", "action": "退回补件", "p": None,
                           "final_action": "退回补件", "error": str(exc)})
            return result
        result["features"] = feats
        self.logger.log(app_id, "FEATURE", "ok", "16 个特征构造完成")

        # 3) 打分
        if self.card is None:
            p = self._degraded_score(feats)
            self.logger.log(app_id, "SCORE", "degraded", "使用规则评分 p=%.3f" % p)
        else:
            x = np.array([[feats[f] for f in self.card.features]], dtype=float)
            # 缺失值用训练均值补齐（审计已保证主要字段可用，这里兜底）
            x = np.where(np.isnan(x), self.card.mean, x)
            p = float(self.card.predict_proba(x)[0])
            self.logger.log(app_id, "SCORE", "ok", "p=%.4f" % p)
        result["p"] = round(p, 4)

        # 4) 原因码
        if self.card is not None:
            x = np.array([[feats[f] for f in self.card.features]], dtype=float)
            contrib = self.card.contributions(x[0])
        else:
            contrib = {}
        reasons = self.registry.get("risk-reason-codes").apply(
            {"features": feats, "contributions": contrib})
        result["reasons"] = reasons
        result["risk_texts"] = [r["text"] for r in reasons["risk_factors"]]
        self.logger.log(app_id, "EXPLAIN", "ok", reasons["summary"])

        # 5) 策略
        thresholds = (self.card.thresholds if self.card else
                      {"review_threshold": 0.5, "decline_threshold": 0.8})
        policy = self.registry.get("review-policy").apply({
            "p": p, "thresholds": thresholds, "audit_status": rec_audit["status"]})
        result["policy"] = policy
        result["band"] = policy["band"]
        result["action"] = policy["action"]
        result["priority"] = policy["priority"]
        result["review_required"] = policy["review_required"]
        self.logger.log(app_id, "POLICY", "ok", policy["rationale"])

        # 6) 人工复核
        result["human"] = {"required": policy["review_required"], "reviewed": False}
        if policy["review_required"] and interactive:
            self._print_review_block(result)
            decision = reviewer(dict(result)) if reviewer else self._ask_reviewer(result)
            if decision:
                result["human"].update({"reviewed": True, "decision": decision})
                result["final_action"] = decision
                self.logger.log(app_id, "REVIEW", "ok", "人工结论: %s" % decision)
            else:
                result["final_action"] = "待人工复核"
                self.logger.log(app_id, "REVIEW", "skipped", "复核员未给出结论")
        elif policy["review_required"]:
            result["final_action"] = "待人工复核"
        else:
            result["final_action"] = policy["action"]

        result["status"] = "done"
        result["latency_ms"] = round((time.time() - t0) * 1000, 1)
        return result

    # ------------------------------------------------------------------
    # 批量
    # ------------------------------------------------------------------
    def run_batch(self, records: List[Dict], out_dir: str, interactive: bool = False,
                  reviewer: Optional[Callable[[Dict], Optional[str]]] = None) -> Dict:
        T.ensure_dir(out_dir)
        self.logger = EventLogger(os.path.join(out_dir, "events.jsonl"))
        results = []
        for i, rec in enumerate(records):
            res = self.process(rec, interactive=interactive, reviewer=reviewer,
                               app_id=str(rec.get("ID", "row-%d" % i)))
            results.append(res)
            if interactive:
                self._print_case(res)

        summary = self.summarize(results)
        rows = [{
            "app_id": r["app_id"],
            "p": r.get("p"),
            "band": r.get("band", ""),
            "action": r.get("action", ""),
            "priority": r.get("priority", 0),
            "risk_texts": r.get("risk_texts", []),
            "flags": r.get("flags", []),
            "human_decision": r.get("human", {}).get("decision", ""),
        } for r in results]

        T.write_jsonl(os.path.join(out_dir, "results.jsonl"), results)
        T.write_csv(os.path.join(out_dir, "review_queue.csv"), rows,
                    ["app_id", "p", "band", "action", "priority", "risk_texts", "flags", "human_decision"])
        T.write_json(os.path.join(out_dir, "summary.json"), summary)
        try:
            T.write_workbook(os.path.join(out_dir, "review_queue.xlsx"), rows)
        except Exception as exc:  # 缺少 openpyxl 时不影响主流程
            self.logger.log("-", "EXPORT_XLSX", "skipped", str(exc))
        with open(os.path.join(out_dir, "run_summary.md"), "w", encoding="utf-8") as f:
            f.write(self.render_markdown(summary, results))
        return {"results": results, "summary": summary, "out_dir": out_dir}

    # ------------------------------------------------------------------
    def summarize(self, results: List[Dict]) -> Dict:
        n = len(results)
        by_action: Dict[str, int] = {}
        by_band: Dict[str, int] = {}
        for r in results:
            action = r.get("final_action") or r.get("action") or "未知"
            by_action[action] = by_action.get(action, 0) + 1
            band = r.get("band") or "-"
            by_band[band] = by_band.get(band, 0) + 1
        scored = [r for r in results if r.get("p") is not None]
        return {
            "n": n,
            "by_action": by_action,
            "by_band": by_band,
            "scored": len(scored),
            "rejected_by_audit": n - len(scored),
            "mean_latency_ms": round(float(np.mean([r.get("latency_ms", 0) for r in results])), 1) if n else 0.0,
            "degraded": any(r.get("degraded") for r in results),
            "skills": self.registry.manifest(),
            "model": os.path.basename(self.model_path),
        }

    def render_markdown(self, summary: Dict, results: List[Dict]) -> str:
        lines = ["# 本批复核摘要", ""]
        lines.append("- 申请数：%d，成功评分 %d，退回补件 %d" % (
            summary["n"], summary["scored"], summary["rejected_by_audit"]))
        lines.append("- 平均单条耗时：%.1f ms" % summary["mean_latency_ms"])
        lines.append("- 动作分布：" + "，".join("%s %d" % (k, v) for k, v in summary["by_action"].items()))
        lines.append("")
        lines.append("| 申请号 | 违约概率 | 等级 | 建议动作 | 主要风险 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for r in results[:20]:
            p = "-" if r.get("p") is None else "%.1f%%" % (r["p"] * 100)
            lines.append("| %s | %s | %s | %s | %s |" % (
                r["app_id"], p, r.get("band", "-"), r.get("final_action", "-"),
                "；".join(r.get("risk_texts", [])) or "-"))
        lines.append("")
        lines.append("> 本摘要由 CreditGuard 生成，所有\"建议拒绝\"均需人工确认，不构成自动拒贷决定。")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def _degraded_score(self, feats: Dict[str, float]) -> float:
        """模型不可用时的兜底规则：只看逾期状态，输出粗概率。"""
        sev = _clamp(feats.get("pay_max", 0), 0, 8)
        cnt = _clamp(feats.get("delay2_cnt", 0), 0, 6)
        logit = -1.6 + 0.45 * sev + 0.35 * cnt
        return float(1.0 / (1.0 + np.exp(-logit)))

    def _print_review_block(self, result: Dict) -> None:
        """展示待复核案件的关键证据，供复核员判断。"""
        p = result.get("p") or 0.0
        print("\n--- 待复核：%s ---" % result["app_id"])
        print("违约概率 %.1f%% | 等级 %s | 建议 %s" % (p * 100, result.get("band"), result.get("action")))
        for t in result.get("risk_texts", []):
            print("  风险：" + t)
        print("  依据：" + result["policy"]["rationale"])

    def _ask_reviewer(self, result: Dict) -> Optional[str]:
        """命令行交互式复核；返回 None 表示复核员暂不处理。"""
        ans = input("复核结论 [a]通过 / [r]拒绝 / [s]稍后: ").strip().lower()
        mapping = {"a": "人工通过", "r": "人工拒绝", "s": None}
        return mapping.get(ans, None)

    def _print_case(self, result: Dict) -> None:
        p = "-" if result.get("p") is None else "%.1f%%" % (result["p"] * 100)
        print("[%s] p=%s 等级=%s 动作=%s" % (
            result["app_id"], p, result.get("band", "-"), result.get("final_action", "-")))
