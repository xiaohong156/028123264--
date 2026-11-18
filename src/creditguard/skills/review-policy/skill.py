# -*- coding: utf-8 -*-
"""技能：复核策略（review-policy）。

输入模型概率与数据质量标记，输出风险分级与建议动作。核心约束：
任何"建议拒绝"都必须人工确认，Agent 不自动拒贷。
"""
from __future__ import annotations

from typing import Dict

NAME = "review-policy"
VERSION = "1.0.0"

NEAR_THRESHOLD = 0.02


def apply(payload: Dict) -> Dict:
    """payload: p / thresholds / audit_status"""
    p = float(payload["p"])
    thresholds = payload["thresholds"]
    review_thr = float(thresholds["review_threshold"])
    decline_thr = float(thresholds["decline_threshold"])
    audit_status = payload.get("audit_status", "ok")

    if audit_status == "error":
        return {
            "skill": NAME, "version": VERSION,
            "band": "C", "action": "退回补件", "review_required": True,
            "priority": 999, "rationale": "输入数据存在字段缺失或越界，无法可靠评分。",
        }

    if p >= decline_thr:
        band, action, priority = "C", "建议拒绝并人工确认", 100 + (p - decline_thr) * 100
        rationale = "违约概率 %.1f%% 超过建议拒绝线 %.1f%%。" % (p * 100, decline_thr * 100)
    elif p >= review_thr:
        band, action, priority = "B", "人工复核", 50 + (p - review_thr) * 100
        rationale = "违约概率 %.1f%% 进入复核区间（复核线 %.1f%%）。" % (p * 100, review_thr * 100)
    elif abs(p - review_thr) <= NEAR_THRESHOLD:
        band, action, priority = "B", "人工复核", 40
        rationale = "违约概率 %.1f%% 接近复核线，边界情形转人工。" % (p * 100)
    else:
        band, action, priority = "A", "自动通过", 0
        rationale = "违约概率 %.1f%% 低于复核线 %.1f%%。" % (p * 100, review_thr * 100)

    if audit_status == "warn" and action == "自动通过":
        # 数据有疑点不允许走快速通道
        band, action, priority = "B", "人工复核", max(priority, 30)
        rationale += " 但数据存在质量标记，强制转人工。"

    return {
        "skill": NAME,
        "version": VERSION,
        "band": band,
        "action": action,
        "review_required": action != "自动通过",
        "priority": round(float(priority), 2),
        "rationale": rationale,
        "thresholds": {"review": review_thr, "decline": decline_thr},
    }
