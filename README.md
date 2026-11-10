# 财报复核工作台 · Report Evidence Workbench

用中文查询英文财报，核对回答中的金额、期间、单位和出处。工作台会展示原始答复、PDF 物理页码与引文，方便检查某个数字取自哪一行。

Ask questions in Chinese against an English earnings release. Inspect a recorded answer and its source row offline, or upload your own report and run the reader locally with Ollama.

## 先看一道题 / Quick start

打开[在线逐题查看器](https://shuboyu0520.github.io/report-evidence-workbench/evidence-review.html#cohort=expedia-replay&case=E09)，可以看到模型答了什么，以及引文位于原表的哪一页。下载仓库后，也可直接打开[离线查看器](docs/evidence-review.html)，或用 Python 3.10 以上版本在仓库目录运行以下命令。

```shell
python scripts/inspect_eval.py --cohort expedia-replay --case E09
```

Expedia 当季的自由现金流是多少？模型首次读到原表的 `$ (1,399)`，给出了正确的负数，旧版却在最终校验时丢掉了答复。E09 展示这次拒答和修复后的答案 **−1,399 百万美元**，可直接对照[原表第 14 页](https://s202.q4cdn.com/757635260/files/content_files/Q3-2026-Earnings-Release-Final.pdf#page=14)。

[![Expedia 自由现金流的原答、复测答复和第 14 页引文](docs/evidence-review-preview.png)](https://shuboyu0520.github.io/report-evidence-workbench/evidence-review.html#cohort=expedia-replay&case=E09)

```shell
python scripts/inspect_eval.py
python scripts/inspect_eval.py --cohort hilton --failed
```

第一条显示评测概况，第二条列出新公司首测的失败样例。[逐题存档 JSON](evaluation/showcase.json) · [已上线的台积电联读案例](https://shuboyu0520.github.io/report-evidence-workbench/reader.html) · [三分钟实录](https://shuboyu0520.github.io/report-evidence-workbench/)

## 冻结评测 / Evaluation results

| 场景 | 查数与指引 | 披露状态 |
| --- | ---: | ---: |
| Booking，原题修复后复测 | 14/14 | 4/4 |
| Expedia，新公司首次作答 | 2/14 | 4/4 |
| Expedia，同一 PDF 与题目修复后复测 | 14/14 | 4/4 |
| Hilton，本轮冻结后首次作答 | 3/14 | 4/4 |

Booking 同一组 14 道查数与指引题依次通过 2、10、14 道。最后一次修复涉及单季自由现金流、调整后 EBITDA、报告口径间夜增幅和固定汇率总预订额增幅。

Expedia 首测的 12 道漏答中，11 道未选出合格原表单元格，1 道在最终校验时把会计括号负数读成正数。修复后复测通过 12/12 道实际值和 2/2 道指引。另以原 PDF 回放 Booking、Airbnb、Uber、高通、台积电的 76 道既有题，答复、引文和状态逐题一致。[12 道漏答的原因与原表](evaluation/expedia-failure-review.md) · [76 道回放记录](evaluation/expedia-repair-regression.json)

冻结版本后，希尔顿 18 道题各运行一次。查数通过 3/12，指引通过 0/2，披露状态通过 4/4。11 道失败中有 8 道拒答、3 道错答：特许经营及授权费、酒店自营业务收入都被替换为集团总营收；利润表利息费用被替换为 EBITDA 调节表的正向加回。[希尔顿原始公告](https://ir.hilton.com/news-events/investor-news/detail/419/hilton-reports-third-quarter-results) · [希尔顿逐题评分](evaluation/hilton-first-20261110.json) · [早期评测](EVALUATION_HISTORY.md)

*Expedia is a repair replay. Hilton was run once on a previously untested issuer using preregistered questions. Lookup and guidance are scored separately from disclosure status.*

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

运行 `git rev-parse HEAD:app` 可查看应用目录的 Git 对象。模型摘要、推理参数、运行时间、题集指纹与历史回放数量见[本轮冻结记录](evaluation/expedia-hilton-release.json)。[前一轮冻结记录](evaluation/frozen-release-20261110.json)留存了 Expedia 首测的环境。

将 [Expedia 季报](https://s202.q4cdn.com/757635260/files/content_files/Q3-2026-Earnings-Release-Final.pdf)和[希尔顿季报](https://ir.hilton.com/_assets/_0dae474c42299bf06914d109d97c2a81/hilton/news/2026-10-27_Hilton_Reports_Third_Quarter_419.pdf)分别保存为 `expedia.pdf` 和 `hilton.pdf`，保持 Ollama 运行，选择尚未存在的输出目录。

```shell
uv run python -m scripts.evaluate_reader --fixture evaluation/expedia-reader-blind.json --file expedia.pdf --out replay-expedia
uv run python -m scripts.grade_expedia_replay --fixture evaluation/expedia-reader-blind.json --pdf expedia.pdf --raw replay-expedia/results.json --output replay-expedia/graded.json
uv run python -m scripts.evaluate_reader --fixture evaluation/hilton-reader-blind.json --file hilton.pdf --out replay-hilton
```

脚本核验 PDF 哈希，逐题调用上传与问答接口，并保存每题的首次响应。复核时检查原表行列、正负号、期间和单位。可以用预登记的范围核验一次新运行；已有首测记录会保留。[Expedia 题集](evaluation/expedia-reader-blind.json) · [希尔顿题集](evaluation/hilton-reader-blind.json) · [希尔顿首测登记](evaluation/hilton-preregistration.json)

## 贡献失败样例 / Contribute a case

欢迎提交可以复查的错答或漏答。请带上原始问题、研究截止日、发行人公开 PDF、物理页码和原答，说明判分依据。代码调整可附最小复现以及同题修复前后的结果。[贡献指南](CONTRIBUTING.md)
