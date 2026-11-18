# -*- coding: utf-8 -*-
"""技能：风险原因码（risk-reason-codes）。

把线性评分卡的"对数几率贡献"翻译成业务话术。技能只描述证据，
不下结论——是否通过、是否拒绝由策略技能和人工复核决定。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from creditguard import schema

NAME = "risk-reason-codes"
VERSION = "1.0.0"

MIN_ABS = 0.15
MAX_RISK = 3
MAX_PROTECTIVE = 2
# 与 delay2_cnt 相关系数 0.98，边际系数方向不稳定，容易产生
# "逾期 0 个月推高风险"这类反直觉话术；模型保留该特征，但原因码不使用。
UNSTABLE = {"delay_cnt"}


def _fmt(feature: str, value: float) -> str:
    """把特征值写进自然语言模板。数值特征按单位格式化。"""
    label = schema.FEATURE_LABELS.get(feature, feature)
    if feature in ("sex", "edu", "marriage"):
        mapping = {"sex": {1: "男", 2: "女"},
                   "edu": {1: "研究生", 2: "大学", 3: "高中", 4: "其他"},
                   "marriage": {1: "已婚", 2: "未婚", 3: "其他"}}
        return "%s：%s" % (label, mapping[feature].get(int(round(value)), "未知"))
    if feature in ("util", "util_mean", "util_max", "pay_ratio", "pay_ratio_mean", "bill_trend"):
        return "%s：%.0f%%" % (label, value * 100)
    if feature in ("delay_cnt", "delay2_cnt", "zero_pay_cnt"):
        return "%s：%.0f 个月" % (label, value)
    if feature in ("pay_max", "pay_trend"):
        return "%s：%.0f 期" % (label, value)
    if feature == "age":
        return "%s：%.0f 岁" % (label, value)
    if feature == "limit_bal":
        return "%s：%.0f 元" % (label, value)
    return "%s：%.0f 元" % (label, value)


def apply(payload: Dict) -> Dict:
    """payload: features / contributions / min_abs"""
    features: Dict[str, float] = payload.get("features", {})
    contrib: Dict[str, float] = payload.get("contributions", {})
    min_abs = float(payload.get("min_abs", MIN_ABS))

    pairs = [(f, v) for f, v in contrib.items()
             if abs(v) >= min_abs and f in features and f not in UNSTABLE]
    risky = sorted([p for p in pairs if p[1] > 0], key=lambda x: -x[1])[:MAX_RISK]
    protective = sorted([p for p in pairs if p[1] < 0], key=lambda x: x[1])[:MAX_PROTECTIVE]

    def build(items):
        out = []
        for f, c in items:
            out.append({
                "feature": f,
                "label": schema.FEATURE_LABELS.get(f, f),
                "text": _fmt(f, features[f]),
                "contribution": round(float(c), 4),
                "direction": "推高风险" if c > 0 else "降低风险",
            })
        return out

    risk_factors = build(risky)
    protective_factors = build(protective)
    total_abs = sum(abs(c) for _, c in pairs)
    low_confidence = total_abs < 0.3

    if risk_factors:
        summary = "主要风险来自%s。" % "、".join(x["label"] for x in risk_factors)
    else:
        summary = "未发现显著的风险推高因素。"
    if protective_factors:
        summary += "同时，%s 起到一定缓冲作用。" % "、".join(
            x["label"] for x in protective_factors)

    return {
        "skill": NAME,
        "version": VERSION,
        "risk_factors": risk_factors,
        "protective_factors": protective_factors,
        "summary": summary,
        "low_confidence": low_confidence,
        "note": "贡献值为模型对数几率上的边际作用，不代表因果影响。",
    }
