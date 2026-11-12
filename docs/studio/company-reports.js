'use strict';

// Official report readings. Historical model evaluations live in evidence-review-data.js.
(() => {
  function reading(id, question, answer, grade, quote, page, section) {
    return {id, kind: 'actual', question, answer, grade, citations: [{quote, page, section}]};
  }

  window.ISSUER_REPORTS = {
    alphabet: {
      title: '谷歌（Alphabet）', ticker: 'GOOGL / GOOG', period: '2026 年第三季度', ended: '2026-09-30',
      revenueMillions: 127577,
      source: 'https://s206.q4cdn.com/479360582/files/doc_news/2026/Oct/28/attachments/2026q3-alphabet-earnings-release.pdf',
      cases: [
        reading('GOOG01', '谷歌母公司 Alphabet 本季的合并营收是多少？', '集团营收为 127,577 百万美元。',
          '财报以百万美元列示。按 2026 年列读数，左侧 102,346 为去年同期。',
          'Revenues $ 102,346 $ 127,577', 1),
        reading('GOOG02', '其中 Google Cloud 贡献了多少营收？', 'Google Cloud 分部营收为 30,709 百万美元。',
          '第 2 页同时列出收入与营业利润。在 Revenues 表内找到 Google Cloud，再读本期列。',
          'Google Cloud 15,157 30,709', 2)
      ]
    },
    amd: {
      title: 'AMD（超威半导体）', ticker: 'AMD', period: '2026 财年第三季度', ended: '2026-09-26',
      revenueMillions: 13377,
      source: 'https://ir.amd.com/financial-information/sec-filings/content/0000002488-26-000188/attachments/AMD_Q3_2026_Earnings_Slides_FINAL.pdf',
      cases: [
        reading('AMD01', 'AMD 本季的集团营收是多少？', '集团营收为 13,377 百万美元。',
          'GAAP 损益摘要把本期放在第一列，9,246 是去年同期收入。',
          'Revenue $13,377 $9,246 Up 45%', 10),
        reading('AMD02', 'AMD 数据中心分部本季实现了多少净营收？', '数据中心分部净营收为 8,546 百万美元。',
          '分部表内选 Data Center 的 Net Revenue 行。其下的 Operating Income 是营业利润。',
          'Net Revenue $8,546 $4,341 Up 97%', 12)
      ]
    },
    nvidia: {
      title: '英伟达（NVIDIA）', ticker: 'NVDA', period: '2027 财年第二季度', ended: '2026-07-26',
      revenueMillions: 96221,
      source: 'https://investor.nvidia.com/files/doc_financials/2027/NVDA-2027-Q2-10Q-Final-including-exhibits.pdf',
      cases: [
        reading('NVDA01', '英伟达本财季的集团营收是多少？', '集团营收为 96,221 百万美元。',
          '本表分别列出本季、上季及去年同期。读取截至 7 月 26 日的三个月。',
          'Revenue $ 96,221 $ 81,615 $ 46,743', 27),
        reading('NVDA02', '英伟达本季的数据中心收入是多少？', '数据中心收入为 89,023 百万美元。',
          '在按终端市场披露的表内读取 Data Center 本期收入。该金额包含在集团总收入中。',
          'Data Center $ 89,023 $ 75,246 $ 41,096', 27)
      ]
    },
    meta: {
      title: 'Meta Platforms', ticker: 'META', period: '2026 年第三季度', ended: '2026-09-30',
      revenueMillions: 64601,
      source: 'https://s21.q4cdn.com/399680738/files/content_files/Meta-09-30-2026-Exhibit-99-1_FINAL.pdf',
      cases: [
        reading('META01', 'Meta 本季的集团营收是多少？', '集团营收为 64,601 百万美元。',
          '财务摘要在 Revenue 行同时给出本季、去年同期和同比增幅。',
          'Revenue $ 64,601 $ 51,242 26 %', 1),
        reading('META02', 'Meta 本季自由现金流是正还是负？金额是多少？', '本季自由现金流为负 2,120 百万美元。',
          '现金流对账表把负数放在括号内。取三个月列，同表的 11,049 是前九个月累计值。',
          'Free cash flow $ (2,120)', 10)
      ]
    },
    microsoft: {
      title: '微软（Microsoft）', ticker: 'MSFT', period: '2027 财年第一季度', ended: '2026-09-30',
      revenueMillions: 92279,
      source: 'https://www.microsoft.com/en-us/investor/earnings/fy-2027-q1/press-release-webcast',
      cases: [
        reading('MSFT01', '微软本财季的集团总营收是多少？', '集团总营收为 92,279 百万美元。',
          '合并利润表以百万美元列示，Total revenue 行的 2026 列对应本季。下方摘录按原表列序排列。',
          'Total revenue · 92,279 · 77,673', null, 'INCOME STATEMENTS'),
        reading('MSFT02', '微软单独披露的 Azure 本季收入是多少？', 'Azure 产品收入为 33,165 百万美元。',
          '在产品与服务收入表读取 Azure 行。包括其他云服务的 Microsoft Cloud 汇总数属于另一口径。',
          'Azure · $33,165 · $22,384', null, 'PRODUCT AND SERVICE OFFERINGS REVENUE')
      ]
    }
  };
})();
