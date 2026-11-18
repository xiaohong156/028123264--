# 第三方组件与许可证清单

本项目代码以 Apache License 2.0 发布（见 `LICENSE`）。以下组件由第三方提供，
仅用于模型训练、评估、导出与报告生成。

| 组件 | 版本 | 许可证 | 来源 | 用途 | 修改情况 |
| --- | --- | --- | --- | --- | --- |
| Default of Credit Card Clients 数据集 | UCI dataset 350 | CC BY 4.0 | https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients | 训练/验证/测试数据 | 未修改，仅做特征派生 |
| anthropics/skills · skill-creator | commit 2c5958e | Apache-2.0 | https://github.com/anthropics/skills | SKILL.md 规范与 quick_validate.py 校验 | 未改原脚本；新增 UTF-8 适配封装（tools/skill_lint.py） |
| scikit-learn | 0.24.1 | BSD-3-Clause | https://scikit-learn.org | 标准化、逻辑回归、指标计算 | 未修改 |
| pandas | 1.2.4 | BSD-3-Clause | https://pandas.pydata.org | 数据处理 | 未修改 |
| numpy | 1.20.1 | BSD-3-Clause | https://numpy.org | 数值计算 | 未修改 |
| matplotlib | 3.3.4 | PSF/BSD 兼容 | https://matplotlib.org | 图表 | 未修改 |
| openpyxl | 3.1.5 | MIT | https://openpyxl.readthedocs.io | 复核清单 Excel 导出 | 未修改 |
| PyYAML | 5.4.1 | MIT | https://pyyaml.org | 解析技能 frontmatter | 未修改 |
| python-docx | 1.2.0 | MIT | https://python-docx.readthedocs.io | 生成报告 docx | 未修改 |

## 引用

- Yeh, I. C., & Lien, C. H. (2009). The comparisons of data mining techniques for the
  predictive accuracy of probability of default of credit card clients. *Expert Systems
  with Applications*, 36(2), 2473–2480.
- Anthropic. *Agent Skills*（Apache-2.0）. https://github.com/anthropics/skills
