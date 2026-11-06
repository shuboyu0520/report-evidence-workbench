/* Evidence review UI. All report content is inserted as text, never markup. */
let reviewRevision = 0;
let reviewGeneration = 0;
let reviewReport = '';
const metricNames = {revenue:'营业收入',cost:'营业成本',net_profit:'净利润',operating_cash_flow:'经营现金流',total_assets:'总资产',total_liabilities:'总负债'};
const field = id => document.getElementById(id);
function updateReviewSummary() {
  const unit = field('metric-unit').value;
  const value = field('metric-value').value.trim();
  field('metric-review-summary').textContent = unit && value
    ? `将保存：${field('metric-year').value} 年 ${metricNames[field('metric-name').value]} ${value} ${unit}（${field('metric-currency').value}）。请与原文逐项核对。`
    : '请选择原文单位并填写数值，再核对保存内容。';
}
for (const id of ['metric-name','metric-year','metric-value','metric-unit','metric-currency','metric-page','metric-quote']) {
  field(id).addEventListener('input', () => {
    field('metric-confirmed').checked = false;
    updateReviewSummary();
  });
}
async function loadMetricReview() {
  const id = field('reports').value;
  const generation = ++reviewGeneration;
  if (reviewReport && reviewReport !== id) {
    field('metric-form').reset();
    updateReviewSummary();
  }
  reviewReport = '';
  field('metric-save').disabled = true;
  field('metric-list').replaceChildren();
  field('metric-history').replaceChildren();
  field('source-page').textContent = '';
  if (!id) {
    field('metric-status').textContent = '请先导入一份报告。';
    return;
  }
  try {
    const [report, changes] = await Promise.all([
      request('/reports/'+encodeURIComponent(id)),
      request('/reports/'+encodeURIComponent(id)+'/metrics/history')
    ]);
    if (generation !== reviewGeneration) return;
    reviewReport = id;
    reviewRevision = report.revision;
    field('metric-save').disabled = false;
    field('metric-status').textContent = '当前指标版本 '+reviewRevision+'。请选择已有指标，或填写一条新指标。';
    for (const metric of report.metrics) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `${metric.year} ${metricNames[metric.name]} · ${metric.value} ${metric.currency}（基本单位）`;
      button.onclick = () => {
        field('metric-name').value = metric.name;
        field('metric-year').value = metric.year;
        // Stored values are normalized; their source may use millions/billions.
        field('metric-value').value = '';
        field('metric-unit').value = '';
        field('metric-currency').value = metric.currency;
        field('metric-page').value = metric.page;
        field('metric-quote').value = metric.quote;
        field('metric-reason').value = '';
        field('metric-confirmed').checked = false;
        field('metric-status').textContent = '已选择指标。请按原文填写数值和单位；列表金额已换算为基本单位。';
        updateReviewSummary();
      };
      field('metric-list').append(button);
    }
    for (const change of changes) {
      const p = document.createElement('p');
      p.textContent = `版本 ${change.revision} · ${metricNames[change.metric_name]} ${change.year}：${change.previous?.value ?? '未录入'} → ${change.current.value} ${change.current.currency}。说明：${change.reason}`;
      field('metric-history').append(p);
    }
    if (!changes.length) field('metric-history').textContent = '尚无人工修订记录。';
  } catch (error) {
    if (generation === reviewGeneration) field('metric-status').textContent = error.message;
  }
}
field('reports').addEventListener('change', () => {
  field('metric-form').reset();
  updateReviewSummary();
  field('result').hidden = true;
  void loadMetricReview();
});
window.addEventListener('reports-loaded', loadMetricReview);
field('metric-reload').onclick = loadMetricReview;
field('read-page').onclick = async () => {
  const id = field('reports').value;
  const generation = reviewGeneration;
  if (!id) return;
  try {
    const page = await request(`/reports/${encodeURIComponent(id)}/pages/${Number(field('metric-page').value)}`);
    if (generation === reviewGeneration) field('source-page').textContent = page.text;
  } catch (error) {
    if (generation === reviewGeneration) field('source-page').textContent = error.message;
  }
};

// The initial reports response can finish before this external script loads.
void loadMetricReview();
field('metric-form').onsubmit = async event => {
  event.preventDefault();
  const id = reviewReport;
  if (!id || id !== field('reports').value) return;
  const generation = reviewGeneration;
  field('metric-save').disabled = true;
  const body = {
    name:field('metric-name').value,year:Number(field('metric-year').value),
    source_value:field('metric-value').value,source_unit:field('metric-unit').value,
    currency:field('metric-currency').value,page:Number(field('metric-page').value),
    quote:field('metric-quote').value,scope:'consolidated_annual',
    confirmed_by_user:field('metric-confirmed').checked,
    expected_revision:reviewRevision,reason:field('metric-reason').value
  };
  try {
    await request(`/reports/${encodeURIComponent(id)}/metrics`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if (generation !== reviewGeneration) return;
    field('result').hidden = true;
    window.dispatchEvent(new Event('metrics-updated'));
    await loadMetricReview();
    if (generation + 1 !== reviewGeneration || id !== field('reports').value) return;
    field('metric-status').textContent = '已保存修订。请重新分析，以便使用新指标。';
    field('metric-confirmed').checked = false;
  } catch (error) {
    if (generation === reviewGeneration) field('metric-status').textContent = error.message;
  } finally {
    if (reviewReport === field('reports').value && generation === reviewGeneration) field('metric-save').disabled = false;
  }
};
