# 财报复核工作台 · Report Evidence Workbench

用中文查询英文财报，核对回答中的金额、期间、单位和出处。工作台会展示原始答复、PDF 物理页码与引文，方便检查某个数字取自哪一行。

Ask questions in Chinese against an English earnings release. Inspect a recorded answer and its source row offline, or upload your own report and run the reader locally with Ollama.

## 先看一道题 / Quick start

打开[在线逐题查看器](https://shuboyu0520.github.io/report-evidence-workbench/evidence-review.html#cohort=wyndham-replay&case=W14)，可以对照同一道题的两次答复，再到公告原页检查金额、期间和指引版本。下载仓库后，也可打开[离线查看器](docs/evidence-review.html)，或用 Python 3.10 以上版本在仓库目录运行以下命令。

```shell
python scripts/inspect_eval.py --cohort wyndham-replay --case W14
```

温德姆把 2026 年全年调整后 EBITDA 的指引下限提高了多少？公告第 5 页并排印着两组区间，旧版未能选出单元格。按更新栏读取，全年指引为 **740–745 百万美元**，此前为 **735–745 百万美元**。这两组数值共用上限，只检查上限无法识别取错栏。[温德姆原始公告](https://investor.wyndhamhotels.com/news-events/press-releases/detail/432/wyndham-hotels-resorts-reports-strong-third-quarter)

[![温德姆全年调整后 EBITDA 指引的首次拒答、复测答案与原表](docs/evidence-review-preview.png)](https://shuboyu0520.github.io/report-evidence-workbench/evidence-review.html#cohort=wyndham-replay&case=W14)

```shell
python scripts/inspect_eval.py
python scripts/inspect_eval.py --cohort hyatt --failed
```

第一条显示评测概况，第二条列出新公司首测的失败样例。[逐题存档 JSON](evaluation/showcase.json) · [已上线的台积电联读案例](https://shuboyu0520.github.io/report-evidence-workbench/reader.html) · [三分钟实录](https://shuboyu0520.github.io/report-evidence-workbench/)

## 冻结评测 / Evaluation results

| 场景 | 查数与指引 | 披露状态 |
| --- | ---: | ---: |
| Booking，原题修复后复测 | 14/14 | 4/4 |
| Expedia，新公司首次作答 | 2/14 | 4/4 |
| Expedia，同一 PDF 与题目修复后复测 | 14/14 | 4/4 |
| Hilton，上一轮冻结后首次作答 | 3/14 | 4/4 |
| Hilton，同一 PDF 与题目修复后复测 | 14/14 | 4/4 |
| Wyndham，上一轮冻结后首次作答 | 3/14 | 4/4 |
| Wyndham，同一 PDF 与题目修复后复测 | 14/14 | 4/4 |
| Hyatt，本轮冻结后首次作答 | 3/14 | 4/4 |

Booking 同一组 14 道查数与指引题依次通过 2、10、14 道。最后一次修复涉及单季自由现金流、调整后 EBITDA、报告口径间夜增幅和固定汇率总预订额增幅。

Expedia 首测的 12 道漏答中，11 道未选出合格原表单元格，1 道在最终校验时把会计括号负数读成正数。修复后复测通过 12/12 道实际值和 2/2 道指引。另以原 PDF 回放 Booking、Airbnb、Uber、高通、台积电的 76 道既有题，答复、引文和状态逐题一致。[12 道漏答的原因与原表](evaluation/expedia-failure-review.md) · [76 道回放记录](evaluation/expedia-repair-regression.json)

希尔顿首测有 3 道错答、8 道拒答。修复后，特许经营与授权费收入、自有酒店业务收入分别定位到 815 和 304 百万美元，利息费用定位到利润表的 −184 百万美元。另 8 道均通过原页核验。用前 6 家公司的 94 道题回放，答复、引文、页码与验证状态逐题一致。[希尔顿 11 道题的原因与结果](evaluation/hilton-failure-review.md) · [94 道历史回放](evaluation/hilton-repair-regression.json)

温德姆首测通过 **3/12 道实际值**，分别为 GAAP 摊薄每股收益 1.33 美元、集团净利润 99 百万美元、单季自由现金流 100 百万美元。**两道全年指引均未通过**。其余 11 道有原表答案的问题都停在原表取数阶段，系统没有选出符合条件的单元格，最终拒答。披露判断通过 4/4。[温德姆原始公告](https://investor.wyndhamhotels.com/news-events/press-releases/detail/432/wyndham-hotels-resorts-reports-strong-third-quarter) · [11 道拒答与原表](https://shuboyu0520.github.io/report-evidence-workbench/evidence-review.html#cohort=wyndham&filter=failed)

温德姆的 11 道漏答经原题复测全部通过，覆盖合并利润表、分部表、地区运营表及全年更新指引。另回放 7 家公司的 112 道历史题，答案、引文、页码及验证状态逐题一致。[逐题根因与结果](evaluation/wyndham-failure-review.md) · [112 道历史回归](evaluation/wyndham-repair-regression.json)

新公司首测只上传凯悦新闻室的 8 页官方公告。实际值答对 2/12，分别是新开客房 3,808 间和 A 类普通股回购 147 百万美元。全年指引答对 1/2，正确读出调整后 EBITDA 为 1,170–1,200 百万美元。披露判断通过 4/4。其余 11 道均拒答，其中 7 道未选出合格单元格，1 道未识别正文的同比期间，2 道将截至日期的月日当作待校验的数字，1 道因附加引文不连续而丢弃了正确的 RevPAR 区间。[凯悦原公告](https://newsroom.hyatt.com/Q3-2026-Earnings-Results) · [11 道拒答及原文](https://shuboyu0520.github.io/report-evidence-workbench/evidence-review.html#cohort=hyatt&filter=failed)

*Wyndham is a replay of the same questions. Hyatt was evaluated once on preregistered questions with the frozen reader and the eight-page newsroom release. Disclosure questions are scored separately.*

<a id="run-reader"></a>
## 上传自己的报告 / Run the reader

安装 Python 3.12–3.14、uv 和 Ollama。启动 Ollama 服务后，在仓库根目录打开 PowerShell。

```powershell
ollama pull qwen3:4b-instruct
ollama pull qwen3-embedding:0.6b
$env:OLLAMA_MODEL='qwen3:4b-instruct'
$env:OLLAMA_EMBED_MODEL='qwen3-embedding:0.6b'
uv sync --frozen
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

打开[本机阅读器](http://127.0.0.1:8000/reader)，在「用自己的资料提问」中上传带文本层的 PDF 或 UTF-8 TXT，填写发布日期。选择主资料与研究截止日，提问后可查看原页引文、回答状态，并下载该次分析的输入与调用记录。

## 复现模型评测 / Reproduce a run

运行 `git rev-parse HEAD:app` 可查看应用目录的 Git 对象。模型摘要、推理参数、运行时间与历史回放数量见[本轮冻结记录](evaluation/wyndham-repair-release.json)。[上一轮冻结记录](evaluation/hilton-wyndham-release.json)保留了温德姆首测时的环境。

将[温德姆季度公告所附 PDF](https://investor.wyndhamhotels.com/news-events/press-releases/detail/432/wyndham-hotels-resorts-reports-strong-third-quarter)和[凯悦新闻室公告 PDF](https://newsroom.hyatt.com/Q3-2026-Earnings-Results?asPDF=1)分别保存为 `wyndham.pdf` 和 `hyatt.pdf`。保持 Ollama 运行，选择尚未存在的输出目录。

```shell
uv run python -m scripts.evaluate_reader --fixture evaluation/wyndham-reader-blind.json --file wyndham.pdf --out replay-wyndham
uv run python -m scripts.grade_wyndham_replay --fixture evaluation/wyndham-reader-blind.json --pdf wyndham.pdf --raw replay-wyndham/results.json --output replay-wyndham/graded.json
uv run python -m scripts.evaluate_reader --fixture evaluation/hyatt-reader-blind.json --file hyatt.pdf --out replay-hyatt
```

脚本核验 PDF 哈希，逐题调用上传与问答接口，并保存首次响应。复核时检查原表行列、符号、期间、单位和指引版本。[温德姆题集](evaluation/wyndham-reader-blind.json) · [凯悦题集](evaluation/hyatt-reader-blind.json) · [凯悦首测登记](evaluation/hyatt-preregistration.json)

## 贡献失败样例 / Contribute a case

欢迎提交可以复查的错答或漏答。请带上原始问题、研究截止日、发行人公开 PDF、物理页码和原答，说明判分依据。代码调整可附最小复现以及同题修复前后的结果。[贡献指南](CONTRIBUTING.md)
