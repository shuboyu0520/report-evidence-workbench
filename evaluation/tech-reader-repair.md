# 科技公司财报阅读 Agent：十道原题复测

复测沿用首次运行的四份官方 PDF、微软官网财报转写的 TXT、十个中文问题和同一模型配置。每次都从上传文件开始，经 FastAPI 的阅读接口提问。判定同时检查金额、单位、正负号及对应原表行。微软网页以表名定位，文本输入的第 1 页是逻辑分页。

| 原题 | 首次结果及原因 | 修复后核对的位置 |
| --- | --- | --- |
| AMD 集团营收 | 错答 `$4.3B百万美元`。检索窗口没带回集团总表，模型选了分部图的去年同期值。旧校验认可了原文里的数字，未校验它对应的业务、年份和单位。 | 第 10 页 GAAP 损益表，集团本季 **13,377 百万美元**。 |
| AMD 数据中心收入 | 拒答。检索窗口缺少原表精确值。草稿从图中约数推得 8,500，其引文无法在第 14 页连续定位。 | 第 12 页分部表，Data Center 的 Net Revenue 为 **8,546 百万美元**。 |
| 英伟达集团营收 | 拒答。模型从已获取的页首读到了正确数字，但引文漏掉了六个月累计列，无法回到原行。 | 第 3 页合并利润表，三个月列为 **96,221 百万美元**。报告的财年标签和日历截止日需分别读取。 |
| Meta 集团营收 | 拒答。草稿值正确，第 1 页引文有效，附加的第 6 页引文删掉九个月列，整条答复因引用不连续而被拒。 | 第 6 页利润表，三个月列为 **64,601 百万美元**。 |
| Meta 自由现金流 | 拒答。检索没有返回第 10 页，模型未提供证据。 | 第 10 页现金流对账表，单季 **−2,120 百万美元**，前九个月累计为正 11,049 百万美元。 |
| 微软集团营收 | 拒答。窗口内只有摘要近似值，草稿换算为 923 亿美元，数字校验未能从引文支持输出。 | 官网合并利润表 INCOME STATEMENTS 的 Total revenue 行为 **92,279 百万美元**。 |

修复前答对的四项为 Alphabet 集团营收、Google Cloud 分部营收、英伟达数据中心收入和微软 Azure 收入。在[项目演示](https://shuboyu0520.github.io/report-evidence-workbench/evidence-review.html#cohort=amd&case=AMD01)中切换题目，可查看前后答复和出处。

## 冻结后的新公司盲测

五家十道原题最初答对 4 道、答错 1 道、拒答 5 道，修复后 10 道全部答对且引文可定位。另用温德姆的 18 道旧题回归，前后答复、页码和引文一致。后端自动化测试通过 273 项。

新公司的题目、标准答案和原始 PDF 在修复前封存。在[冻结版本 e7eab6e](https://github.com/shuboyu0520/report-evidence-workbench/commit/e7eab6e7b1d0483b8abcc223e028fb83728b62d1)上首次读取思科 FY2026 Q4 公告，每题仅请求一次。[事先封存的题目](cisco-tech-blind-preregistered.json) · [逐题调用记录](cisco-tech-blind-first-trace.json) · [公开演示与原答](https://shuboyu0520.github.io/report-evidence-workbench/evidence-review.html#cohort=cisco-first&case=C01)

| 思科题型 | 首测答对 | 原答与原表核对 |
| --- | --- | --- |
| 已披露数值 | 0/5 | 全部拒答。集团营收题正确识别财季，扫描 13 页，找到 0 个可用单元格。合并利润表第 4 页列有 17,252 百万美元。两道现金流题均未召回第 7 页。 |
| 下一季指引 | 0/1 | 公告给出营收区间 18,000–18,200 百万美元，系统拒答。 |
| 披露判断 | 1/2 | 加拿大营收未单列，拒答正确。另一题询问下一季实际值，按预设标准应说明截至公告日尚未披露，系统只返回证据不足。 |

八题均返回证据不足，按预设标准计 **1/8**。公布的是首次运行结果。[思科官方公告](https://s21.q4cdn.com/812015656/files/doc_news/CISCO-REPORTS-FOURTH-QUARTER-AND-FISCAL-YEAR-2026-EARNINGS-2026.pdf)

## 复现

用 `scripts/serve_model_demo.py` 启动本机服务。`--inputs` 指向原始公告目录，文件名、SHA-256、实际请求与逐题核对条件见[原题清单](tech-reader-original-questions.json)。`--out` 使用新目录，保留完整响应以供独立评分。

```shell
python scripts/replay_tech_reports.py --inputs SOURCE_DIR --out RUN_DIR --api http://127.0.0.1:8187
python -m scripts.grade_tech_reports --inputs SOURCE_DIR --runs RUN_DIR
```
