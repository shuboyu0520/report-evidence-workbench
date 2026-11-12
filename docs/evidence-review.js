'use strict';

(() => {
  const byId = (id) => document.getElementById(id);
  const kinds = {actual: '查数', guidance: '指引', future: '披露判断', missing: '缺证判断'};
  const states = {
    source_earnings_cell: '已定位原表行列',
    cited_draft: '附引文的模型答复',
    not_yet_disclosed: '报告期尚未结束',
    insufficient_evidence: '证据不足',
    tool_timeout: '检索超时',
    reviewed_evidence: '已核对证据卡'
  };
  const data = window.EVIDENCE_REVIEW;
  const issuers = {
    wyndham: ['温德姆酒店集团', 'WH'], hyatt: ['凯悦酒店集团', 'H'],
    hilton: ['希尔顿集团', 'HLT'], expedia: ['Expedia Group', 'EXPE'],
    booking: ['Booking Holdings', 'BKNG']
  };
  let visibleRows = [];
  let current = null;
  let searchText = '';

  function node(tag, value) {
    const item = document.createElement(tag);
    if (value !== undefined) item.textContent = value;
    return item;
  }

  function validArchive() {
    if (!data || data.schema_version !== 1) return false;
    if (!data.cohorts || !Object.keys(data.cohorts).length) return false;
    return Object.keys(data.cohorts).every((key) => {
      const cohort = data.cohorts?.[key];
      if (!cohort || !Array.isArray(cohort.cases) || !cohort.cases.length) return false;
      const ids = new Set();
      return cohort.cases.every((c) => {
        if (!c || typeof c.id !== 'string' || ids.has(c.id) || !Object.hasOwn(kinds, c.kind)
            || typeof c.passed !== 'boolean' || typeof c.question !== 'string'
            || typeof c.answer !== 'string' || !Array.isArray(c.citations)) return false;
        ids.add(c.id);
        return true;
      });
    });
  }

  function pageLink(source, page) {
    try {
      const url = new URL(source);
      if (url.protocol !== 'https:' || url.username || url.password) return null;
      if (page !== undefined && (!Number.isSafeInteger(page) || page < 1)) return null;
      url.hash = page === undefined ? '' : 'page=' + page;
      const link = node('a', page === undefined ? '打开官方 PDF' : '第 ' + page + ' 页');
      link.href = url.href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      return link;
    } catch {
      return null;
    }
  }

  function hashFor(cohort, filter, id) {
    const params = new URLSearchParams({cohort});
    if (id) params.set('case', id);
    if (filter !== 'all') params.set('filter', filter);
    return '#' + params.toString();
  }

  function change(cohort, filter, id) {
    const hash = hashFor(cohort, filter, id);
    if (location.hash !== hash) location.hash = hash;
    // Render synchronously for keyboard input; hashchange also handles Back and Forward.
    render();
  }

  function changed(row) {
    return typeof row.previous_answer === 'string' && row.previous_answer !== row.answer;
  }

  function rowsFor(key, filter) {
    return data.cohorts[key].cases.filter((row) => {
      if (filter === 'failed') return !row.passed;
      if (filter === 'changed') return changed(row);
      return true;
    });
  }

  function score(cases, types) {
    const subset = cases.filter((row) => types.includes(row.kind));
    return subset.filter((row) => row.passed).length + ' / ' + subset.length;
  }

  function answerBlock(label, answer, isCurrent, source, citations) {
    const section = node('section');
    section.className = 'answer-block' + (isCurrent ? ' current' : '');
    section.append(node('h3', label), node('p', answer));
    if (citations?.length) {
      const links = node('div');
      links.className = 'answer-sources';
      links.append('该答复所引原页');
      for (const page of new Set(citations.map(c => c.page))) {
        const link = pageLink(source, page);
        if (link) links.append(link);
      }
      section.append(links);
    }
    return section;
  }

  function renderDetail(row, cohort) {
    byId('case-number').textContent = row.id;
    byId('case-kind').textContent = kinds[row.kind];
    byId('case-verdict').textContent = row.passed ? '通过' : '未通过';
    byId('case-verdict').dataset.passed = String(row.passed);
    byId('case-verdict').classList.toggle('warn', !row.passed);
    byId('question').textContent = row.question;
    const isReplay = cohort.kind === 'same_set_replay';
    const answers = byId('answers');
    const comparison = isReplay && typeof row.previous_answer === 'string';
    answers.classList.toggle('comparison', comparison);
    answers.replaceChildren();
    answers.append(answerBlock(isReplay ? '同题复测答复' : '冻结版本首次答复', row.answer, true, cohort.source, row.citations));
    if (comparison) {
      const before = answerBlock('修复前原答', row.previous_answer, false, cohort.source, row.previous_citations);
      if (row.previous_grade && changed(row)) {
        const why = node('details');
        why.className = 'previous-grade';
        why.append(node('summary', '查看首测判定'), node('p', row.previous_grade));
        before.append(why);
      }
      const previous = node('details');
      previous.append(node('summary', '对照修复前的原答'), before);
      answers.append(previous);
    }
    byId('grade').textContent = row.grade || states[row.verification] || '';
    const gold = byId('gold-pages');
    const goldLinks = [...new Set(Array.isArray(row.gold_pages) ? row.gold_pages : [])]
      .map(page => pageLink(cohort.source, page)).filter(Boolean);
    gold.hidden = !goldLinks.length;
    gold.replaceChildren();
    if (goldLinks.length) gold.append(document.createTextNode('评分参考页　'), ...goldLinks);
    const hasGoldQuote = typeof row.gold_quote === 'string' && row.gold_quote.trim().length > 0;
    byId('gold-excerpt').hidden = !hasGoldQuote;
    byId('gold-excerpt').open = false;
    byId('gold-quote').textContent = hasGoldQuote ? row.gold_quote : '';
    const citations = byId('citations');
    citations.replaceChildren();
    byId('citation-count').textContent = row.citations.length + ' 处引文';
    for (const citation of row.citations) {
      if (!citation || typeof citation.quote !== 'string' || !citation.quote.trim()) continue;
      const item = node('div');
      item.className = 'citation';
      const validPage = Number.isSafeInteger(citation.page) && citation.page > 0;
      item.append(pageLink(cohort.source, citation.page) || node('span', validPage ? '第 ' + citation.page + ' 页' : '原文引文'));
      item.append(node('blockquote', citation.quote));
      citations.append(item);
    }
    if (!citations.childElementCount) {
      const notice = node('p', states[row.verification]
        ? '该题记录为“' + states[row.verification] + '”，答复未附引文。'
        : '该题答复未附引文。');
      citations.append(notice);
      const full = pageLink(cohort.source);
      if (full) citations.append(full);
    }
    byId('permalink').href = hashFor(current.cohort, 'all', row.id);
  }

  function showSearch() {
    const list = byId('search-results');
    list.replaceChildren();
    byId('search-status').textContent = '';
    if (!searchText) return;
    const terms = Studio.tokens(searchText);
    const ranked = visibleRows.map(row => ({
      row, score: row.id.toLowerCase() === searchText.toLowerCase() ? 1000 :
        2 * Studio.searchScore(searchText, row.question, terms) +
        Studio.searchScore(searchText, row.citations.map(c => c.quote).join(' '), terms)
    })).filter(hit => hit.score > 0).sort((a,b) => b.score-a.score);
    byId('search-status').textContent = ranked.length ? '找到 ' + ranked.length + ' 条相关记录，选择问题可核对答复与原页。' : '此批次和筛选下没有匹配记录。可换个指标或打开自己的财报。';
    for (const {row} of ranked.slice(0, 6)) {
      const button = node('button');
      button.type = 'button';
      button.className = 'result-button';
      button.append(node('small', row.id + '　'),document.createTextNode(row.question));
      button.onclick = () => {
        change(current.cohort, current.filter, row.id);
        byId('case-detail').scrollIntoView({block:'nearest'});
      };
      list.append(button);
    }
  }

  function render() {
    const params = new URLSearchParams(location.hash.slice(1));
    const requested = params.get('cohort');
    const key = Object.hasOwn(data.cohorts, requested) ? requested : Object.keys(data.cohorts)[0];
    const cohort = data.cohorts[key];
    const isReplay = cohort.kind === 'same_set_replay';
    const filter = ['all', 'failed', ...(isReplay ? ['changed'] : [])]
      .includes(params.get('filter')) ? params.get('filter') : 'all';
    visibleRows = rowsFor(key, filter);
    const id = params.get('case');
    const selected = visibleRows.find(row => row.id === id) ||
      (!requested && !id && visibleRows.find(row => row.id === 'W14')) || visibleRows[0];
    if (current && current.cohort !== key) {
      searchText = ''; byId('archive-query').value = '';
    }
    current = {cohort: key, filter, id: selected?.id};
    byId('copy-status').textContent = '';
    const [issuer, ticker] = issuers[key.split('-')[0]] || [cohort.title,''];
    byId('issuer-title').textContent = issuer;
    byId('issuer-meta').textContent = ticker + '　/　2026 Q3 业绩公告　·　' + (isReplay ? '同题复测' : '新公司首次盲测');
    byId('cohort-select').value = key;
    byId('lookup-score').textContent = score(cohort.cases, ['actual', 'guidance']);
    byId('status-score').textContent = score(cohort.cases, ['future', 'missing']);
    byId('score-bars').replaceChildren(...cohort.cases.filter(r=>['actual','guidance'].includes(r.kind)).map(row=>{
      const bar=node('i'); if(row.passed) bar.className='pass'; return bar;
    }));
    const changedOption = byId('result-filter').querySelector('[value="changed"]');
    changedOption.hidden = changedOption.disabled = !isReplay;
    byId('result-filter').value = filter;
    const select = byId('case-select');
    select.replaceChildren();
    for (const row of visibleRows) {
      select.add(new Option(row.id + ' · ' + row.question, row.id));
    }
    if (selected) select.value = selected.id;
    select.disabled = !selected;
    const index = visibleRows.indexOf(selected);
    byId('previous-case').disabled = index <= 0;
    byId('next-case').disabled = index < 0 || index >= visibleRows.length - 1;
    byId('case-detail').hidden = !selected;
    const status = byId('navigation-status');
    showSearch();
    if (!selected) {
      status.textContent = filter === 'failed' ? '此批次没有未通过的题目。' : '当前筛选没有匹配的题目。';
      byId('citations').replaceChildren(node('p','选择其他批次或筛选条件可查看原页引文。'));
      byId('citation-count').textContent = '';
      return;
    }
    const prefix = id && !cohort.cases.some(row => row.id === id) ? '档案中未找到该题号。' : '';
    status.textContent = prefix + '当前筛选共 ' + visibleRows.length + ' 题，正在查看 ' + selected.id + '。';
    renderDetail(selected, cohort);
  }

  if (!validArchive()) {
    byId('load-status').textContent = '无法载入本地评测记录。请确认本页与 evidence-review-data.js 位于同一目录，再刷新页面。';
    return;
  }
  byId('load-status').hidden = true;
  byId('review').hidden = false;
  for (const [key, cohort] of Object.entries(data.cohorts)) {
    const phase = cohort.kind === 'same_set_replay' ? '同题复测' : '新公司首测';
    const issuer = issuers[key.split('-')[0]]?.[0] || cohort.title;
    byId('cohort-select').add(new Option(issuer + ' · ' + phase,key));
  }
  byId('cohort-select').onchange = e=>change(e.target.value,'all');
  byId('find-case').onclick = () => {
    byId('archive-query').scrollIntoView({block:'center'});
    byId('archive-query').focus({preventScroll:true});
  };
  byId('archive-search').onsubmit = e=>{
    e.preventDefault(); searchText=byId('archive-query').value.trim(); showSearch();
  };
  byId('archive-query').addEventListener('input',e=>{
    if (!e.target.value.trim()) {searchText='';showSearch();}
  });
  byId('result-filter').addEventListener('change', e => {
    const filter = e.target.value;
    const rows = rowsFor(current.cohort, filter);
    const id = rows.some(row => row.id === current.id) ? current.id : rows[0]?.id;
    change(current.cohort, filter, id);
  });
  byId('case-select').addEventListener('change', e => change(current.cohort, current.filter, e.target.value));
  function step(direction) {
    const next = visibleRows[visibleRows.findIndex(row => row.id === current.id) + direction];
    if (next) change(current.cohort, current.filter, next.id);
  }
  byId('previous-case').addEventListener('click', () => step(-1));
  byId('next-case').addEventListener('click', () => step(1));
  byId('jump-source').addEventListener('click', () => {
    byId('evidence-panel').scrollIntoView({block:'start'});
    byId('evidence-panel').focus({preventScroll:true});
  });
  byId('copy-link').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(byId('permalink').href);
      byId('copy-status').textContent = '本题链接已复制。';
    } catch {
      byId('copy-status').textContent = '请使用“本题固定链接”的复制链接地址功能。';
      byId('permalink').focus();
    }
  });
  window.addEventListener('hashchange', render);
  render();
})();
