// Graded frozen runs; reference answers were withheld from the reader.
window.TECH_READER_VALIDATION = {
  "engine_commit": "e7eab6e7b1d0483b8abcc223e028fb83728b62d1",
  "replays": {
    "GOOG01": {
      "question": "Alphabet 2026年第三季度的集团合并营收是多少百万美元？",
      "answer": "2026 财年第3季度，公司整体  Revenues（实际）为 127,577 百万美元。原表第 1 页。",
      "verification": "source_earnings_cell",
      "outcome": "matched",
      "run_at": "2026-11-12T10:19:43.629581+00:00",
      "input_sha256": "2f9b94e9194ea4b462bf754c4b651615ab53518b314550f3402b27aabf0735e9",
      "citations": [
        {
          "page": 1
        }
      ],
      "tools": [
        "search_earnings_rows",
        "read_earnings_cell"
      ],
      "source_row": "Revenues $ 102,346 $ 127,577"
    },
    "GOOG02": {
      "question": "Alphabet 2026年第三季度的Google Cloud 分部营收是多少百万美元？",
      "answer": "2026 财年第3季度，所问业务  Google Cloud（实际）为 30,709 百万美元。原表第 7 页。",
      "verification": "source_earnings_cell",
      "outcome": "matched",
      "run_at": "2026-11-12T10:19:43.836109+00:00",
      "input_sha256": "2f9b94e9194ea4b462bf754c4b651615ab53518b314550f3402b27aabf0735e9",
      "citations": [
        {
          "page": 1
        },
        {
          "page": 7
        }
      ],
      "tools": [
        "search_earnings_rows",
        "read_earnings_cell"
      ],
      "source_row": "Google Cloud 15,157 30,709"
    },
    "AMD01": {
      "question": "AMD 2026财年第三季度的集团营业收入是多少百万美元？",
      "answer": "2026 财年第3季度，公司整体  Revenue（实际）为 13,377 百万美元。原表第 10 页。",
      "verification": "source_earnings_cell",
      "outcome": "matched",
      "run_at": "2026-11-12T10:19:45.044015+00:00",
      "input_sha256": "4a0bb9ca09f3fe374220dbc8a361b0655bea18dc9e0947fc233f999f3d32a77a",
      "citations": [
        {
          "page": 10
        }
      ],
      "tools": [
        "search_earnings_rows",
        "read_earnings_cell"
      ],
      "source_row": "Revenue $13,377 $9,246 Up 45% $11,536 Up 16%",
      "diagnosis": "原答取了数据中心上年同期的图表值，又重复标注金额单位。复测按集团 GAAP 损益表、本季度列和百万美元表头共同定位。"
    },
    "AMD02": {
      "question": "AMD 2026财年第三季度的Data Center 数据中心分部净营收是多少百万美元？",
      "answer": "2026 财年第3季度，Net Revenue Data Center（实际）为 8,546 百万美元。原表第 12 页。",
      "verification": "source_earnings_cell",
      "outcome": "matched",
      "run_at": "2026-11-12T10:19:45.236251+00:00",
      "input_sha256": "4a0bb9ca09f3fe374220dbc8a361b0655bea18dc9e0947fc233f999f3d32a77a",
      "citations": [
        {
          "page": 12
        }
      ],
      "tools": [
        "search_earnings_rows",
        "read_earnings_cell"
      ],
      "source_row": "Net Revenue $8,546 $4,341 Up 97% $6,718 Up 27%",
      "diagnosis": "原答从图中约数推算金额，所附引文未能连续定位。复测取分部表 Data Center 下的 Net Revenue 原行。"
    },
    "NVDA01": {
      "question": "NVIDIA 2027财年第二季度的集团营业收入是多少百万美元？",
      "answer": "2027 财年第2季度，公司整体  Revenue（实际）为 96,221 百万美元。原表第 3 页。",
      "verification": "source_earnings_cell",
      "outcome": "matched",
      "run_at": "2026-11-12T10:19:51.281589+00:00",
      "input_sha256": "6b5a8dc1ed21e8b2b960fd0de97103af6a2f32ccc8dd91b363f06ea192ecfebd",
      "citations": [
        {
          "page": 1
        },
        {
          "page": 3
        },
        {
          "page": 27
        }
      ],
      "tools": [
        "search_earnings_rows",
        "read_earnings_cell"
      ],
      "source_row": "Revenue $ 96,221 $ 46,743 $ 177,837 $ 90,805",
      "diagnosis": "首次草稿中的金额正确，但所引原行漏掉了六个月累计列。复测保留完整原行，选取财年对应的三个月列。"
    },
    "NVDA02": {
      "question": "NVIDIA 2027财年第二季度的Data Center 数据中心营收是多少百万美元？",
      "answer": "2027 财年第2季度，所问业务  Data Center（实际）为 89,023 百万美元。原表第 24 页。",
      "verification": "source_earnings_cell",
      "outcome": "matched",
      "run_at": "2026-11-12T10:19:51.712312+00:00",
      "input_sha256": "6b5a8dc1ed21e8b2b960fd0de97103af6a2f32ccc8dd91b363f06ea192ecfebd",
      "citations": [
        {
          "page": 1
        },
        {
          "page": 24
        },
        {
          "page": 27
        }
      ],
      "tools": [
        "search_earnings_rows",
        "read_earnings_cell"
      ],
      "source_row": "Data Center $ 89,023 $ 41,096 $ 164,269 $ 80,208"
    },
    "META01": {
      "question": "Meta Platforms 2026年第三季度的集团营业收入是多少百万美元？",
      "answer": "2026 财年第3季度，公司整体  Revenue（实际）为 64,601 百万美元。原表第 6 页。",
      "verification": "source_earnings_cell",
      "outcome": "matched",
      "run_at": "2026-11-12T10:19:52.697780+00:00",
      "input_sha256": "ad58e598105dc6f3330f30d407e4b0d4e8d0307a63b30b5a79e0655ab3ff9db2",
      "citations": [
        {
          "page": 6
        }
      ],
      "tools": [
        "search_earnings_rows",
        "read_earnings_cell"
      ],
      "source_row": "Revenue $ 64,601 $ 51,242 $ 181,712 $ 141,073",
      "diagnosis": "首次草稿中的金额正确，附加引文漏掉了九个月列而被拒。复测从完整的利润表行读取单季值。"
    },
    "META02": {
      "question": "Meta Platforms 2026年第三季度的自由现金流（Free cash flow）是多少百万美元？",
      "answer": "2026 财年第3季度，公司整体  Free cash flow（实际）为 -2,120 百万美元。原表第 10 页。",
      "verification": "source_earnings_cell",
      "outcome": "matched",
      "run_at": "2026-11-12T10:19:52.952379+00:00",
      "input_sha256": "ad58e598105dc6f3330f30d407e4b0d4e8d0307a63b30b5a79e0655ab3ff9db2",
      "citations": [
        {
          "page": 1
        },
        {
          "page": 10
        }
      ],
      "tools": [
        "search_earnings_rows",
        "read_earnings_cell"
      ],
      "source_row": "Free cash flow $ (2,120) $ 10,625 $ 11,049 $ 29,508",
      "diagnosis": "首次检索没有取回自由现金流对账表。复测保留会计括号的负号，并区分当季和前九个月累计。"
    },
    "MSFT01": {
      "question": "Microsoft 2027财年第一季度的集团营业收入是多少百万美元？",
      "answer": "2027 财年第1季度，公司整体  Total revenue（实际）为 92,279 百万美元。原表第 1 页。",
      "verification": "source_earnings_cell",
      "outcome": "matched",
      "run_at": "2026-11-12T10:19:53.186167+00:00",
      "input_sha256": "5156ce0de9617b9ff39c11ca47ba97a85384f45154a3770e18a07871175b8951",
      "citations": [
        {
          "page": 1
        }
      ],
      "tools": [
        "search_earnings_rows",
        "read_earnings_cell"
      ],
      "source_row": "Total revenue 92,279 77,673",
      "diagnosis": "首次检索只提供摘要里的近似值。复测从官网利润表的 Total revenue 行读取精确值，再按表头识别单位。"
    },
    "MSFT02": {
      "question": "Microsoft 2027财年第一季度的Azure 单项营业收入是多少百万美元？",
      "answer": "2027 财年第1季度，所问业务  Azure（实际）为 33,165 百万美元。原表第 1 页。",
      "verification": "source_earnings_cell",
      "outcome": "matched",
      "run_at": "2026-11-12T10:19:53.474437+00:00",
      "input_sha256": "5156ce0de9617b9ff39c11ca47ba97a85384f45154a3770e18a07871175b8951",
      "citations": [
        {
          "page": 1
        }
      ],
      "tools": [
        "search_earnings_rows",
        "read_earnings_cell"
      ],
      "source_row": "Azure $33,165 $22,384"
    }
  },
  "blind": {
    "title": "思科（Cisco Systems）",
    "ticker": "CSCO",
    "company": "Cisco Systems",
    "period": "2026 财年第四季度",
    "ended": "2026-07-25",
    "published_on": "2026-08-12",
    "as_of": "2026-08-12",
    "calendar_year": false,
    "source_url": "https://s21.q4cdn.com/812015656/files/doc_news/CISCO-REPORTS-FOURTH-QUARTER-AND-FISCAL-YEAR-2026-EARNINGS-2026.pdf",
    "issuer_page": "https://investor.cisco.com/news/news-details/2026/CISCO-REPORTS-FOURTH-QUARTER-AND-FISCAL-YEAR-2026-EARNINGS/default.aspx",
    "document_sha256": "6edea35ffff138918bed8899a513c84a26389fe6e4313a86781d74bfdbbb8b02",
    "kind": "blind_first",
    "id": "cisco-first",
    "source": "https://s21.q4cdn.com/812015656/files/doc_news/CISCO-REPORTS-FOURTH-QUARTER-AND-FISCAL-YEAR-2026-EARNINGS-2026.pdf",
    "freeze_commit": "e7eab6e7b1d0483b8abcc223e028fb83728b62d1",
    "application_tree": "862cd9b71cc8ef8d89ff3e692eb271bf690c363f",
    "application_digest": "0e41ff6b993860a93952a96d38f529d18bf813c05bcd240eccb7cbf2aaa60180",
    "preregistration_sha256": "eac1345214c0b422c4fc7d1092c95976a6a7dfc820cb840a4530f479866039ee",
    "history_check": {
      "local_report_databases": 2152,
      "matches": 0
    },
    "grade_policy": {
      "actual": "按原文指定单位与符号比较，接受等值且清楚的单位换算。数值题须正确识别指标和本期，并附能支持正确数值和语境的引文。四舍五入的概数不能代替表内百万美元精确值。",
      "guidance": "两个端点、单位、期间和指引口径须正确，并引用原公告。",
      "missing": "应明确材料未提供所问口径，允许说明已披露的更粗粒度；不得猜测国家级数字。",
      "future": "答复须识别提问日期尚无下一季度实际业绩，不得把指引当作实际值。",
      "recording": "普通上传完整PDF和reader接口。题目不含标准答案、提示与页码。冻结后只取每题首次响应；记录答案、状态、引文和失败。另报查数、指引、披露判断小计。"
    },
    "started": "2026-11-12T10:21:14.661315+00:00",
    "cases": [
      {
        "id": "C01",
        "kind": "actual",
        "question": "思科 2026 财年第四季度的集团总营收是多少百万美元？",
        "gold": "集团营收为 17,252 百万美元。",
        "expected": [
          17252
        ],
        "gold_pages": [
          4,
          5,
          6
        ],
        "gold_locator": "Total 17,252",
        "answer": "在所选资料中没找到足够证据。可补充含该指标的主表或附注后再查。",
        "verification": "insufficient_evidence",
        "cited_pages": [],
        "citations": [],
        "passed": false,
        "outcome": "abstained",
        "grade": "集团营收为 17,252 百万美元。 原表的本季集团营收为 17,252 百万美元（第 4 页）。结构化查数没有返回候选行，最终拒答。",
        "http_status": 200,
        "run_at": "2026-11-12T10:21:15.864707+00:00",
        "tools": [
          "search_earnings_rows"
        ],
        "raw_response_sha256": "6b467ddf3cfb6ed1594ffe8ef8754acb06587c77742c4410ceb30e3acbc986df"
      },
      {
        "id": "C02",
        "kind": "actual",
        "question": "思科 2026 财年第四季度的 Networking 产品收入是多少百万美元？",
        "gold": "Networking 产品收入为 9,791 百万美元。",
        "expected": [
          9791
        ],
        "gold_pages": [
          6
        ],
        "gold_locator": "Networking 9,791",
        "answer": "在所选资料中没找到足够证据。可补充含该指标的主表或附注后再查。",
        "verification": "insufficient_evidence",
        "cited_pages": [],
        "citations": [],
        "passed": false,
        "outcome": "abstained",
        "grade": "Networking 产品收入为 9,791 百万美元。 第 6 页产品表列示 Networking 为 9,791 百万美元。结构化查数未返回候选行。",
        "http_status": 200,
        "run_at": "2026-11-12T10:21:15.918250+00:00",
        "tools": [
          "search_earnings_rows"
        ],
        "raw_response_sha256": "ba09b92cc6d5134f1481963ddbdfd658d0e15ebea6d3602c3640eda0215b194b"
      },
      {
        "id": "C03",
        "kind": "actual",
        "question": "思科 2026 财年第四季度美洲地区（Americas）的营收是多少百万美元？",
        "gold": "美洲地区收入为 10,396 百万美元。",
        "expected": [
          10396
        ],
        "gold_pages": [
          5
        ],
        "gold_locator": "Americas 10,396",
        "answer": "在所选资料中没找到足够证据。可补充含该指标的主表或附注后再查。",
        "verification": "insufficient_evidence",
        "cited_pages": [],
        "citations": [],
        "passed": false,
        "outcome": "abstained",
        "grade": "美洲地区收入为 10,396 百万美元。 第 5 页地区分部表列示美洲本季为 10,396 百万美元。结构化查数未返回候选行。",
        "http_status": 200,
        "run_at": "2026-11-12T10:21:15.970450+00:00",
        "tools": [
          "search_earnings_rows"
        ],
        "raw_response_sha256": "66b9b41f0eda313a6d16c5fe24e395a02b51f5c04ceb9d57ba61138aa0b04a1f"
      },
      {
        "id": "C04",
        "kind": "actual",
        "question": "思科 2026 财年第四季度经营活动产生的现金净额是多少百万美元？",
        "gold": "经营活动现金净流入为 5,386 百万美元。",
        "expected": [
          5386
        ],
        "gold_pages": [
          7
        ],
        "gold_locator": "operating activities 5,386",
        "answer": "在所选资料中没找到足够证据。可补充含该指标的主表或附注后再查。",
        "verification": "insufficient_evidence",
        "cited_pages": [],
        "citations": [],
        "passed": false,
        "outcome": "abstained",
        "grade": "经营活动现金净流入为 5,386 百万美元。 第 7 页列示经营现金流精确值 5,386 百万美元。文本检索返回的段落没有该页，模型未选出引文。",
        "http_status": 200,
        "run_at": "2026-11-12T10:21:16.018167+00:00",
        "tools": [
          "search_report"
        ],
        "raw_response_sha256": "094e9483e067ffe3747f92fe7fdeb16a81ed7a40ea9eece1d66b4e71c581ed9d"
      },
      {
        "id": "C05",
        "kind": "actual",
        "question": "思科 2026 财年第四季度投资活动现金流量净额是多少百万美元？请写明流入或流出。",
        "gold": "投资活动现金净流出 264 百万美元，即 −264 百万美元。",
        "expected": [
          -264
        ],
        "gold_pages": [
          7
        ],
        "gold_locator": "investing activities (264)",
        "answer": "在所选资料中没找到足够证据。可补充含该指标的主表或附注后再查。",
        "verification": "insufficient_evidence",
        "cited_pages": [],
        "citations": [],
        "passed": false,
        "outcome": "abstained",
        "grade": "投资活动现金净流出 264 百万美元，即 −264 百万美元。 第 7 页现金流量表的括号值代表净流出 264 百万美元。文本检索返回的段落没有该页，模型未选出引文。",
        "http_status": 200,
        "run_at": "2026-11-12T10:21:19.362060+00:00",
        "tools": [
          "search_report"
        ],
        "raw_response_sha256": "1ca258eefa68836c8f1d1ec6493dc702383938ae0179c17f9a09f8a3e1b88484"
      },
      {
        "id": "C06",
        "kind": "guidance",
        "question": "这份公告给出的 2027 财年第一季度集团收入指引是多少？请按百万美元写出上下限。",
        "gold": "下一财季的集团收入指引为 18,000 至 18,200 百万美元。",
        "expected": [
          18000,
          18200
        ],
        "gold_pages": [
          1,
          4
        ],
        "gold_locator": "$18.0 billion - $18.2 billion",
        "answer": "在所选资料中没找到足够证据。可补充含该指标的主表或附注后再查。",
        "verification": "insufficient_evidence",
        "cited_pages": [],
        "citations": [],
        "passed": false,
        "outcome": "abstained",
        "grade": "下一财季的集团收入指引为 18,000 至 18,200 百万美元。 第 1、4 页列出了下一财季营收指引。结构化查数无候选行，未能作答和换算两个端点。",
        "http_status": 200,
        "run_at": "2026-11-12T10:21:21.318263+00:00",
        "tools": [
          "search_earnings_rows"
        ],
        "raw_response_sha256": "af0ca01442217faf198b12636b53aecdfa020c96b145ac646492fa3c8e3d2518"
      },
      {
        "id": "C07",
        "kind": "missing",
        "question": "这份公告是否单独披露思科本季在加拿大的营收金额？",
        "gold": "未单独披露加拿大营收，公告按美洲、EMEA、APJC 列示地理分部。",
        "expected": [],
        "gold_pages": [
          5
        ],
        "gold_locator": "Americas / EMEA / APJC",
        "answer": "在所选资料中没找到足够证据。可补充含该指标的主表或附注后再查。",
        "verification": "insufficient_evidence",
        "cited_pages": [],
        "citations": [],
        "passed": true,
        "outcome": "matched",
        "grade": "报告披露了美洲、EMEA、APJC 的地区收入，没有单列加拿大。最终拒绝报数符合缺证题判分条件。",
        "http_status": 200,
        "run_at": "2026-11-12T10:21:21.365001+00:00",
        "tools": [
          "search_report"
        ],
        "raw_response_sha256": "e7f1f1c5609324a9672a5d6ecb5a8f8b0e57782e93984fcafc4ba21129d1b462"
      },
      {
        "id": "C08",
        "kind": "future",
        "question": "截至这份财报发布日期，思科 2027 财年第一季度的实际集团营收是多少？",
        "gold": "该季实际营收尚未披露，公告仅给出收入指引。",
        "expected": [],
        "gold_pages": [
          1,
          4
        ],
        "gold_locator": "Q1 FY 2027 Guidance",
        "answer": "在所选资料中没找到足够证据。可补充含该指标的主表或附注后再查。",
        "verification": "insufficient_evidence",
        "cited_pages": [],
        "citations": [],
        "passed": false,
        "outcome": "abstained",
        "grade": "该季实际营收尚未披露，公告仅给出收入指引。 到 8 月 12 日仅发布下一财季指引。本题要求识别尚未披露实际业绩，最终答复仅称证据不足。",
        "http_status": 200,
        "run_at": "2026-11-12T10:21:30.346231+00:00",
        "tools": [
          "search_earnings_rows"
        ],
        "raw_response_sha256": "8e0b666c739046ece2663401e4f8dec3c7d5c5c321bccf5bbe6128827a323b08"
      }
    ],
    "counts": {
      "abstained": 7,
      "matched": 1
    },
    "key": "cisco-first"
  }
};
