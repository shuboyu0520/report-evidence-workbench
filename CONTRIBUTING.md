# 提交可复查的财报案例 / Contributing

一个可复现的失败案例通常只需一份公告和一个问题。先在[离线查看器](docs/evidence-review.html)或 [JSON 存档](evaluation/showcase.json)查找相同的问题。

## 报告一次失败

在 Issue 中填入下面几项。若要复查某个已有样例，可直接附上公司和题号，例如 `booking/B14`。

| 项目 | 填写内容 |
| --- | --- |
| 资料与日期 | 公司、发行人公开 PDF 链接、资料发布日期、提问时采用的研究截止日。原文件可能替换时附 SHA-256。 |
| 如何复现 | 完整中文问题、代码版本、模型名、从上传到提问的操作或命令。用到检索或推理参数时一起附上。 |
| 首次答复 | 完整原答、回答状态、返回的物理页码与引文。可附导出的工具轨迹。 |
| 原页核对 | PDF 从 1 开始计算的页码、行名、列名、币种、单位与期间。指引题请写明上下限、同比口径及实际或预期。 |
| 为什么判错 | 给出可复核的预期值，指出错行、错列、精度、符号、口径或漏答。缺证题请说明这份资料提供到哪个范围。 |

For an English issue, provide the exact question, cutoff date, issuer PDF and physical page, expected row and column, and the reader’s original output. Please specify the unit and period. A link to a public source lets another contributor verify the result.

## 提交修复

说明改动覆盖的报表表示方式，例如季度列跨行或括号表示负数。附一个能捕获回归的用例，以及原题修复前后的答复、原页引文和判分。把已见问题的复测标为同题回放。若提出新公司盲测，在首次调用前记录题面、样本范围、PDF 哈希和验收条件，保留第一次运行的全部回答和技术失败。

在仓库根目录准备环境后可运行 `uv run pytest -q`。[本机阅读器与模型复现步骤](README.md#run-reader)
