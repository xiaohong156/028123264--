# -*- coding: utf-8 -*-
"""技能：信贷申请数据审计（credit-data-audit）。

技能只负责"判断"，不负责"修复"：返回每条记录的状态与机器可读标记，
由 Agent 决定退回、补件还是带着标记继续评分。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from creditguard import schema

NAME = "credit-data-audit"
VERSION = "1.0.0"

REQUIRED = [c for c in schema.RAW_COLUMNS if c not in (schema.TARGET_RAW, "ID")]


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def audit_record(record: Dict[str, object]) -> Dict:
    """检查单条记录，返回 status / flags / 可用的数值字段。"""
    flags: List[str] = []
    errors: List[str] = []
    warnings: List[str] = []

    for col in REQUIRED:
        if record.get(col) is None or (isinstance(record.get(col), str) and not record.get(col).strip()):
            flags.append("missing:%s" % col)
            errors.append(col)

    def numeric(col):
        v = _to_float(record.get(col))
        if v is None and col in record and record.get(col) is not None:
            flags.append("non_numeric:%s=%r" % (col, record.get(col)))
            errors.append(col)
        return v

    limit = numeric("LIMIT_BAL")
    age = numeric("AGE")
    sex = numeric("SEX")
    edu = numeric("EDUCATION")
    marriage = numeric("MARRIAGE")

    if limit is not None:
        lo, hi = schema.RANGES["LIMIT_BAL"]
        if not lo <= limit <= hi:
            flags.append("range:LIMIT_BAL=%.0f" % limit)
            errors.append("LIMIT_BAL")
    if age is not None:
        lo, hi = schema.RANGES["AGE"]
        if not lo <= age <= hi:
            flags.append("range:AGE=%.0f" % age)
            errors.append("AGE")

    for col in schema.PAY_COLS:
        v = numeric(col)
        if v is not None:
            lo, hi = schema.PAY_RANGE
            if not lo <= v <= hi:
                flags.append("range:%s=%.0f" % (col, v))
                errors.append(col)

    for col in schema.BILL_COLS + schema.PAY_AMT_COLS:
        v = numeric(col)
        if v is None:
            continue
        lo, hi = schema.RANGES[col]
        if v < lo or v > hi:
            flags.append("range:%s=%.0f" % (col, v))
            warnings.append(col)  # 金额越界可能只是单位/录入问题，允许截断后继续

    if sex is not None and int(sex) not in schema.SEX_MAP:
        flags.append("unknown_code:SEX=%d" % int(sex))
        warnings.append("SEX")
    if edu is not None and int(edu) not in schema.EDU_MAP:
        flags.append("unknown_code:EDUCATION=%d" % int(edu))
        warnings.append("EDUCATION")
    if marriage is not None and int(marriage) not in schema.MARRIAGE_MAP:
        flags.append("unknown_code:MARRIAGE=%d" % int(marriage))
        warnings.append("MARRIAGE")

    if errors:
        status = "error"
    elif warnings:
        status = "warn"
    else:
        status = "ok"
    return {"status": status, "flags": flags, "error_fields": sorted(set(errors)),
            "warn_fields": sorted(set(warnings))}


def apply(payload: Dict) -> Dict:
    """payload: {"records": [...]} → 审计结果。"""
    records = payload.get("records") or []
    results = []
    seen = set()
    for idx, rec in enumerate(records):
        item = audit_record(rec)
        app_id = rec.get("ID")
        if app_id is not None:
            if app_id in seen:
                item["flags"].append("duplicate_id:%s" % app_id)
                if item["status"] == "ok":
                    item["status"] = "warn"
            seen.add(app_id)
        item["index"] = idx
        item["app_id"] = app_id
        results.append(item)

    counts = {"ok": 0, "warn": 0, "error": 0}
    for item in results:
        counts[item["status"]] += 1
    return {
        "skill": NAME,
        "version": VERSION,
        "counts": counts,
        "records": results,
        "batch_ok": counts["error"] == 0,
    }
