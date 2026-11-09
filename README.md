# 财报复核工作台 · Report Evidence Workbench

用中文查询英文财报，核对回答中的金额、期间、单位和出处。工作台会展示原始答复、PDF 物理页码与引文，方便检查某个数字取自哪一行。

Ask questions in Chinese against an English earnings release. Inspect a recorded answer and its source row offline, or upload your own report and run the reader locally with Ollama.

## 先看一道题 / Quick start

在包含本页的仓库目录中，可用浏览器直接打开 [离线评测查看器](docs/evidence-review.html)。也可用 Python 3.10 或更高版本运行以下命令。查看存档只用 Python 标准库。

```shell
python scripts/inspect_eval.py --cohort booking --case B14
```

B14 问的是 Booking 对第四季度**固定汇率口径总预订额同比增幅**的指引。原表第 3 页给出的区间是 **4% 至 6%**。打开这条记录，可以对照问题、作答和引文，检查系统是否选中了正确的指引行。

[![逐题查看 Booking B14 的上版答复、复测答复与 PDF 第 3 页的引文](docs/evidence-review-preview.png)](docs/evidence-review.html#cohort=booking&case=B14)

```shell
python scripts/inspect_eval.py
python scripts/inspect_eval.py --cohort expedia --failed
```

第一条显示评测概况，第二条列出新公司首测的失败样例。[逐题存档 JSON](evaluation/showcase.json) · [已上线的台积电联读案例](https://shuboyu0520.github.io/report-evidence-workbench/reader.html) · [三分钟实录](https://shuboyu0520.github.io/report-evidence-workbench/)

## 冻结评测 / Evaluation results

| 场景 | 查数与指引 | 披露状态 |
| --- | ---: | ---: |
| Booking，原题修复后复测 | 14/14 | 4/4 |
| Expedia，新公司首次作答 | 2/14 | 4/4 |

Booking 同一组 14 道查数与指引题依次通过 2、10、14 道。最后一次修复涉及单季自由现金流、调整后 EBITDA、报告口径间夜增幅和固定汇率总预订额增幅。

代码冻结后，对同业新公司 Expedia 只做一次首测。12 道查数通过 2 道，2 道指引均未通过。12 道有答案却拒答的题中，11 道未选出符合条件的原表单元格，1 道检索到了正确的自由现金流原页并生成了正确草稿，最终仍返回证据不足。[Booking 官方公告](https://www.bookingholdings.com/wp-content/uploads/2026/11/Q3-26-BKNG-Earnings-Release-Final.pdf) · [Expedia 官方公告](https://s202.q4cdn.com/757635260/files/content_files/Q3-2026-Earnings-Release-Final.pdf) · [早期评测及逐题记录](EVALUATION_HISTORY.md)

*Booking was a replay of known questions. Expedia was evaluated once with the frozen engine. Lookup and guidance, and disclosure status, have separate denominators.*

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

在本轮版本中运行 `git rev-parse HEAD:app` 会得到 `b1a1a10002c4be77f7a7b6948206d53995309fda`。这个 Git 对象可用于核对应用源码版本。模型摘要、推理参数和历史回放数量见[冻结记录](evaluation/frozen-release-20261110.json)。

将上面两份官方 PDF 分别保存到仓库根目录的 `booking.pdf` 和 `expedia.pdf`，保持 Ollama 运行，从新的输出目录开始。

```shell
uv run python -m scripts.evaluate_reader --fixture evaluation/booking-reader-blind.json --file booking.pdf --out replay-booking
uv run python -m scripts.evaluate_reader --fixture evaluation/expedia-reader-blind.json --file expedia.pdf --out replay-expedia
```

脚本核验 PDF 哈希，逐题调用上传与问答接口，把本次结果保存在各目录的 `results.json`。从存档查看器可以查阅原先冻结的首答和独立判分。要核验一次新运行，需按各题集的原页、金额、单位、期间及披露规则重新评分。[Booking 题集](evaluation/booking-reader-blind.json) · [Expedia 题集](evaluation/expedia-reader-blind.json)

## 贡献失败样例 / Contribute a case

欢迎提交可以复查的错答或漏答。请带上原始问题、研究截止日、发行人公开 PDF、物理页码和原答，说明判分依据。代码调整可附最小复现以及同题修复前后的结果。[贡献指南](CONTRIBUTING.md)
