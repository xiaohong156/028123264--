# -*- coding: utf-8 -*-
"""端到端单元测试：数据审计、原因码、策略、Agent 隔离、技能规范。

运行：
    python -m pytest tests -q
或：
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from creditguard import schema  # noqa: E402
from creditguard.agent import CreditAgent  # noqa: E402
from creditguard.ml import data as D  # noqa: E402
from creditguard.ml.model import LinearScorecard  # noqa: E402
from creditguard.skills.registry import SkillRegistry  # noqa: E402


def sample_record(**overrides):
    rec = {
        "ID": 1, "LIMIT_BAL": 20000, "SEX": 2, "EDUCATION": 2, "MARRIAGE": 1, "AGE": 24,
        "PAY_0": 2, "PAY_2": 2, "PAY_3": -1, "PAY_4": -1, "PAY_5": -2, "PAY_6": -2,
        "BILL_AMT1": 3913, "BILL_AMT2": 3102, "BILL_AMT3": 689, "BILL_AMT4": 0,
        "BILL_AMT5": 0, "BILL_AMT6": 0,
        "PAY_AMT1": 0, "PAY_AMT2": 689, "PAY_AMT3": 0, "PAY_AMT4": 0, "PAY_AMT5": 0, "PAY_AMT6": 0,
    }
    rec.update(overrides)
    return rec


class TestAuditSkill(unittest.TestCase):
    def setUp(self):
        self.skill = SkillRegistry().discover().get("credit-data-audit")

    def test_ok_record(self):
        out = self.skill.apply({"records": [sample_record()]})
        self.assertEqual(out["counts"]["ok"], 1)
        self.assertTrue(out["batch_ok"])

    def test_missing_field_is_error(self):
        rec = sample_record()
        rec.pop("PAY_3")
        out = self.skill.apply({"records": [rec]})
        self.assertEqual(out["records"][0]["status"], "error")
        self.assertIn("missing:PAY_3", out["records"][0]["flags"])
        self.assertFalse(out["batch_ok"])

    def test_range_and_unknown_code(self):
        out = self.skill.apply({"records": [
            sample_record(AGE=15), sample_record(EDUCATION=9), sample_record(LIMIT_BAL=3000)]})
        statuses = [r["status"] for r in out["records"]]
        self.assertEqual(statuses[0], "error")   # 年龄越界
        self.assertEqual(statuses[1], "warn")    # 未定义教育编码
        self.assertEqual(statuses[2], "error")   # 额度低于下限


class TestReasonCodes(unittest.TestCase):
    def setUp(self):
        self.skill = SkillRegistry().discover().get("risk-reason-codes")

    def test_top_k_and_direction(self):
        feats = {f: 1.0 for f in schema.FEATURES}
        contrib = {f: 0.0 for f in schema.FEATURES}
        contrib.update({"delay2_cnt": 0.9, "util_mean": 0.5, "pay_ratio_mean": -0.7,
                        "limit_bal": -0.3, "age": 0.01})
        out = self.skill.apply({"features": feats, "contributions": contrib})
        self.assertLessEqual(len(out["risk_factors"]), 3)
        self.assertLessEqual(len(out["protective_factors"]), 2)
        self.assertEqual(out["risk_factors"][0]["feature"], "delay2_cnt")
        self.assertIn("推高", out["risk_factors"][0]["direction"])
        self.assertNotIn("拒绝", out["summary"])

    def test_low_confidence_flag(self):
        feats = {f: 1.0 for f in schema.FEATURES}
        contrib = {f: 0.0 for f in schema.FEATURES}
        out = self.skill.apply({"features": feats, "contributions": contrib})
        self.assertTrue(out["low_confidence"])


class TestPolicy(unittest.TestCase):
    def setUp(self):
        self.skill = SkillRegistry().discover().get("review-policy")
        self.thr = {"review_threshold": 0.37, "decline_threshold": 0.68}

    def test_auto_approve(self):
        out = self.skill.apply({"p": 0.1, "thresholds": self.thr, "audit_status": "ok"})
        self.assertEqual(out["action"], "自动通过")
        self.assertFalse(out["review_required"])

    def test_never_auto_declines(self):
        out = self.skill.apply({"p": 0.95, "thresholds": self.thr, "audit_status": "ok"})
        self.assertEqual(out["action"], "建议拒绝并人工确认")
        self.assertTrue(out["review_required"])

    def test_warn_forces_review(self):
        out = self.skill.apply({"p": 0.1, "thresholds": self.thr, "audit_status": "warn"})
        self.assertEqual(out["action"], "人工复核")

    def test_error_returns_back(self):
        out = self.skill.apply({"p": 0.9, "thresholds": self.thr, "audit_status": "error"})
        self.assertEqual(out["action"], "退回补件")


class TestModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = LinearScorecard.load(os.path.join(ROOT, "models", "logreg_v1.json"))

    def test_probabilities_in_range(self):
        (X, y), _, _, _ = D.prepare(save=False)
        p = self.card.predict_proba(X[self.card.features].values[:200])
        self.assertTrue(np.all((p >= 0) & (p <= 1)))
        self.assertEqual(len(self.card.features), len(schema.FEATURES))

    def test_contribution_sums_to_logit(self):
        (X, y), _, _, _ = D.prepare(save=False)
        x = X[self.card.features].values[0]
        contrib = sum(self.card.contributions(x).values())
        logit = self.card.logit(x.reshape(1, -1))[0]
        self.assertAlmostEqual(contrib + self.card.intercept, logit, places=6)


class TestAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = CreditAgent()

    def test_good_record_completes(self):
        res = self.agent.process(sample_record())
        self.assertEqual(res["status"], "done")
        self.assertIsNotNone(res["p"])
        self.assertIn(res["band"], ("A", "B", "C"))

    def test_bad_record_quarantined(self):
        rec = sample_record(AGE=12)
        res = self.agent.process(rec)
        self.assertEqual(res["status"], "rejected")
        self.assertEqual(res["final_action"], "退回补件")
        self.assertIsNone(res["p"])

    def test_high_risk_requires_review(self):
        res = self.agent.process(sample_record(PAY_0=8, PAY_2=8, PAY_3=8, PAY_4=8,
                                               PAY_5=8, PAY_6=8, BILL_AMT1=19000))
        self.assertTrue(res["review_required"])
        self.assertIn("人工", res["final_action"])

    def test_degraded_mode_when_model_missing(self):
        agent = CreditAgent(model_path=os.path.join(ROOT, "models", "no_such_model.json"))
        res = agent.process(sample_record())
        self.assertTrue(res["degraded"])
        self.assertIsNotNone(res["p"])


class TestSkillSpec(unittest.TestCase):
    def test_all_skills_pass_lint(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import skill_lint
        for path in skill_lint.iter_skills(skill_lint.SKILLS_DIR):
            ok, message = skill_lint.validate(path)
            self.assertTrue(ok, "%s: %s" % (path, message))


if __name__ == "__main__":
    unittest.main()
