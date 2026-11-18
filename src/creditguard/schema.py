# -*- coding: utf-8 -*-
"""字段模式（schema）：UCI 信用卡违约数据的 23 个特征 + 标签。

这里集中定义三件事，避免各模块各写一份、逐渐漂移：
1. 原始列名与中文含义（报告、界面、原因码都要用）；
2. 合法取值范围（数据审计技能据此判断异常）；
3. 类别编码的已知取值（EDUCATION/MARRIAGE 存在未文档化的 0/5/6）。
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# 原始列名（UCI 原始表；镜像 CSV 的第 1 行是表头）
RAW_COLUMNS: List[str] = [
    "ID",
    "LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE",
    "PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6",
    "BILL_AMT1", "BILL_AMT2", "BILL_AMT3", "BILL_AMT4", "BILL_AMT5", "BILL_AMT6",
    "PAY_AMT1", "PAY_AMT2", "PAY_AMT3", "PAY_AMT4", "PAY_AMT5", "PAY_AMT6",
    "default payment next month",
]

TARGET_RAW = "default payment next month"
TARGET = "default"

# 模型真正使用的 16 个特征（由原始字段派生，见 ml/data.py:build_features）
FEATURES: List[str] = [
    "limit_bal", "age", "sex", "edu", "marriage",
    "pay_max", "delay_cnt", "delay2_cnt", "pay_trend",
    "bill_mean", "pay_amt_mean", "zero_pay_cnt", "util", "util_mean", "util_max",
    "pay_ratio", "pay_ratio_mean", "bill_trend",
]

FEATURE_LABELS: Dict[str, str] = {
    "limit_bal": "授信额度",
    "age": "年龄",
    "sex": "性别",
    "edu": "教育程度",
    "marriage": "婚姻状况",
    "pay_max": "近半年最严重逾期状态",
    "pay_mean": "近半年平均逾期状态",
    "delay_cnt": "近半年逾期月数（≥1期）",
    "delay2_cnt": "近半年严重逾期月数（≥2期）",
    "pay_trend": "逾期状态变化（最近一期减最早一期）",
    "bill_mean": "近半年平均账单金额",
    "pay_amt_mean": "近半年平均还款金额",
    "zero_pay_cnt": "近半年零还款月数",
    "util": "当期额度使用率",
    "util_mean": "近半年平均额度使用率",
    "util_max": "近半年最高额度使用率",
    "pay_ratio": "当期还款覆盖率",
    "pay_ratio_mean": "近半年平均还款覆盖率",
    "bill_trend": "账单金额变化趋势",
}

# 特征单位/量纲，用于把原因码写成人能读的句子
FEATURE_UNITS: Dict[str, str] = {
    "limit_bal": "元", "age": "岁", "pay_max": "期", "pay_mean": "期",
    "delay_cnt": "个月", "delay2_cnt": "个月", "pay_trend": "期",
    "bill_mean": "元", "pay_amt_mean": "元", "zero_pay_cnt": "个月",
    "util": "", "util_mean": "", "util_max": "", "pay_ratio": "",
    "pay_ratio_mean": "", "bill_trend": "",
}

# 数值字段的合法区间（闭区间）；超出即视为异常输入
RANGES: Dict[str, Tuple[float, float]] = {
    "LIMIT_BAL": (10_000, 1_000_000),
    "AGE": (18, 100),
    "BILL_AMT1": (-1_000_000, 5_000_000),
    "BILL_AMT2": (-1_000_000, 5_000_000),
    "BILL_AMT3": (-1_000_000, 5_000_000),
    "BILL_AMT4": (-1_000_000, 5_000_000),
    "BILL_AMT5": (-1_000_000, 5_000_000),
    "BILL_AMT6": (-1_000_000, 5_000_000),
    "PAY_AMT1": (0, 5_000_000),
    "PAY_AMT2": (0, 5_000_000),
    "PAY_AMT3": (0, 5_000_000),
    "PAY_AMT4": (0, 5_000_000),
    "PAY_AMT5": (0, 5_000_000),
    "PAY_AMT6": (0, 5_000_000),
}

PAY_COLS = ["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]
BILL_COLS = ["BILL_AMT%d" % i for i in range(1, 7)]
PAY_AMT_COLS = ["PAY_AMT%d" % i for i in range(1, 7)]

PAY_RANGE = (-2, 8)  # -2 表示无消费记录，8 表示押账 8 期以上

# 类别编码 → 中文（含未文档化编码，统一并入"其他"）
EDU_MAP = {1: "研究生", 2: "大学", 3: "高中", 4: "其他", 0: "其他", 5: "其他", 6: "其他"}
MARRIAGE_MAP = {1: "已婚", 2: "未婚", 3: "其他", 0: "其他"}
SEX_MAP = {1: "男", 2: "女"}

# 数值特征的展示精度
DISPLAY_DIGITS = 2


def normalize_columns(columns: List[str]) -> List[str]:
    """容忍表头差异：去掉空格/下划线、统一小写后匹配原始列名。

    UCI 原表表头是 "default payment next month"，很多镜像写成
    "default.payment.next.month" 或 "default_payment_next_month"。
    """
    def key(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.lower())

    known = {key(c): c for c in RAW_COLUMNS}
    out = []
    for col in columns:
        out.append(known.get(key(col), col))
    return out
