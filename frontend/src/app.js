const API_BASE_URL = "http://127.0.0.1:8001/api";

const state = {
  messages: [],
  currentFacts: {},
  intake: null,
  searchResponse: null,
  base: null,
  results: [],
};

const views = {
  search: document.querySelector("#search-view"),
  intake: document.querySelector("#intake-view"),
  results: document.querySelector("#results-view"),
  compare: document.querySelector("#compare-view"),
};

const form = document.querySelector("#search-form");
const answerForm = document.querySelector("#answer-form");
const queryInput = document.querySelector("#query");
const answerInput = document.querySelector("#answer");
const intakeDomainEl = document.querySelector("#intake-domain");
const missingFieldsEl = document.querySelector("#missing-fields");
const questionListEl = document.querySelector("#question-list");
const detectedTypeEl = document.querySelector("#detected-type");
const statutesEl = document.querySelector("#related-statutes");
const baseCaseEl = document.querySelector("#base-case");
const resultsEl = document.querySelector("#results");
const compareBoardEl = document.querySelector("#compare-board");
const compareSummaryEl = document.querySelector("#compare-summary");

const queryTypeLabels = {
  statute: "조문",
  case_no: "사건번호",
  natural: "자연어",
};

const groupLabels = {
  statute_related: "관련 조문 판례",
  fact_similar: "사실관계 유사 판례",
  different_decision_point: "판단 사유가 다른 판례",
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await startIntake(queryInput.value);
});

answerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const answer = answerInput.value.trim();
  if (!answer) return;
  state.messages.push({ role: "user", content: answer });
  answerInput.value = "";
  await runIntake();
});

document.querySelectorAll("[data-query]").forEach((button) => {
  button.addEventListener("click", async () => {
    queryInput.value = button.dataset.query;
    await startIntake(button.dataset.query);
  });
});

document.querySelectorAll("[data-action='back-search']").forEach((button) => {
  button.addEventListener("click", () => showView("search"));
});

document.querySelector("[data-action='back-results']").addEventListener("click", () => showView("results"));
document.querySelector("[data-action='search-anyway']").addEventListener("click", async () => {
  await runSearch(buildFallbackSearchQuery());
});

async function startIntake(query) {
  const content = query.trim();
  if (!content) return;
  state.messages = [{ role: "user", content }];
  state.currentFacts = {};
  state.intake = null;
  setLoading("사건 정보를 확인하고 있습니다.");
  showView("intake");
  await runIntake();
}

async function runIntake() {
  try {
    setLoading("부족한 정보를 판단하고 있습니다.");
    const response = await postJson("/intake", {
      messages: state.messages,
      current_facts: state.currentFacts,
    });
    state.intake = response;
    state.currentFacts = response.extracted_facts || {};

    if (response.status === "ready") {
      await runSearch(response.search_query || buildFallbackSearchQuery());
      return;
    }

    renderIntake(response);
    showView("intake");
  } catch (error) {
    renderError("문진 처리 중 오류가 발생했습니다. 백엔드와 Gemini API 설정을 확인해주세요.", error);
    showView("intake");
  }
}

async function runSearch(query) {
  try {
    setLoading("관련 판례를 검색하고 있습니다.");
    const response = await postJson("/search", {
      query,
      query_type: "auto",
    });
    state.searchResponse = response;
    state.base = response.base_precedent;
    state.results = flattenResults(response.results);
    renderResults(response);
    showView("results");
  } catch (error) {
    resultsEl.innerHTML = renderErrorCard("검색 중 오류가 발생했습니다. 백엔드 서버 상태를 확인해주세요.", error);
    showView("results");
  }
}

function renderIntake(intake) {
  intakeDomainEl.textContent = intake.domain || "미분류";
  missingFieldsEl.innerHTML = intake.missing_fields?.length
    ? intake.missing_fields.map((field) => `<span>${escapeHtml(field)}</span>`).join("")
    : "<span>추가 확인 없음</span>";
  questionListEl.innerHTML = intake.follow_up_questions?.length
    ? intake.follow_up_questions.map((question, index) => `<p><strong>Q${index + 1}.</strong> ${escapeHtml(question)}</p>`).join("")
    : "<p>충분한 정보가 모였습니다. 검색으로 이동합니다.</p>";
}

function renderResults(response) {
  detectedTypeEl.textContent = queryTypeLabels[response.detected_query_type] || response.detected_query_type;
  statutesEl.innerHTML = response.related_statutes?.length
    ? response.related_statutes.map((statute) => `<span>${escapeHtml(statute)}</span>`).join("")
    : "<span>관련 조문 정보 없음</span>";

  baseCaseEl.innerHTML = response.base_precedent
    ? `
      <div class="section-title">
        <p class="eyebrow">기준 판례</p>
        <h3>${escapeHtml(response.base_precedent.case_no)} · ${escapeHtml(response.base_precedent.case_name)}</h3>
      </div>
      ${renderCompactMeta(response.base_precedent)}
      <div class="inline-actions">
        <a href="${escapeAttribute(response.base_precedent.source_url)}" target="_blank" rel="noreferrer">공식 원문 열기</a>
      </div>
    `
    : `
      <div class="section-title">
        <p class="eyebrow">기준 판례</p>
        <h3>기준 판례 없이 관련 후보를 표시합니다.</h3>
      </div>
    `;

  resultsEl.innerHTML = state.results.length
    ? state.results.map((item) => renderResultCard(item)).join("")
    : `<p class="empty-state">검색 결과가 없습니다. 사건 설명이나 조문을 조금 더 구체적으로 입력해주세요.</p>`;

  document.querySelectorAll("[data-compare-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const clicked = state.results.find((item) => item.id === button.dataset.compareId);
      renderCompare(clicked);
      showView("compare");
    });
  });
}

function renderResultCard(item) {
  return `
    <article class="result-card">
      <div class="card-kicker">${escapeHtml(groupLabels[item.group] || item.result_label)}</div>
      <div class="case-topline">
        <strong>${escapeHtml(item.case_no)}</strong>
        <span>${escapeHtml(item.decision_date)}</span>
      </div>
      <h3>${escapeHtml(item.case_name)}</h3>
      <p>${escapeHtml(item.legal_issue_summary)}</p>
      ${renderCompactMeta(item)}
      <div class="card-actions">
        <button type="button" data-compare-id="${escapeAttribute(item.id)}">비교 보기</button>
        <a href="${escapeAttribute(item.source_url)}" target="_blank" rel="noreferrer">원문</a>
      </div>
    </article>
  `;
}

function renderCompare(clicked) {
  const base = state.base || state.results[0];
  if (!base) return;
  const comparisons = uniqueById([clicked, ...state.results.filter((item) => item.id !== clicked?.id)]).slice(0, 3);
  const columns = [base, ...comparisons.filter((item) => item.id !== base.id)].slice(0, 4);

  compareBoardEl.innerHTML = columns
    .map((item, index) => renderCompareColumn(index === 0 ? "기준 판례" : `비교 판례 ${index}`, item, base))
    .join("");
  compareSummaryEl.innerHTML = renderCompareSummary(base, comparisons);
}

function renderCompareColumn(title, item, base) {
  const statutes = item.referenced_statutes || [];
  const commonStatutes = (base.referenced_statutes || []).filter((statute) => statutes.includes(statute));
  const outcome = formatOutcomeLabel(item.outcome_label);
  return `
    <article class="compare-column ${title === "기준 판례" ? "base-column" : ""}">
      <p class="eyebrow">${title}</p>
      <h3>${escapeHtml(item.case_no)}</h3>
      <p class="case-name">${escapeHtml(item.case_name)}</p>
      <dl>
        <dt>참조 조문</dt><dd>${statutes.map(escapeHtml).join(", ") || "없음"}</dd>
        <dt>공통 조문</dt><dd>${commonStatutes.length ? commonStatutes.map(escapeHtml).join(", ") : "없음"}</dd>
        <dt>쟁점</dt><dd>${escapeHtml(item.legal_issue_summary)}</dd>
        <dt>사실관계</dt><dd>${escapeHtml(item.fact_summary)}</dd>
        <dt>판단 사유</dt><dd>${escapeHtml(item.decision_point)}</dd>
        <dt>판결 결과</dt><dd>${escapeHtml(outcome)}</dd>
      </dl>
      <a href="${escapeAttribute(item.source_url)}" target="_blank" rel="noreferrer">공식 원문 열기</a>
    </article>
  `;
}

function renderCompareSummary(base, comparisons) {
  const rows = comparisons
    .filter((item) => item.id !== base.id)
    .map((item) => {
      const commonStatutes = (base.referenced_statutes || []).filter((statute) => (item.referenced_statutes || []).includes(statute));
      return `
        <tr>
          <td><a href="${escapeAttribute(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(item.case_no)}</a></td>
          <td>${commonStatutes.length ? commonStatutes.map(escapeHtml).join(", ") : "없음"}</td>
          <td>${escapeHtml(item.decision_point)}</td>
          <td>${escapeHtml(formatOutcomeLabel(item.outcome_label))}</td>
        </tr>
      `;
    })
    .join("");

  return `
    <div class="summary-card">
      <div class="section-title">
        <p class="eyebrow">비교 요약</p>
        <h3>공통 조문과 판단 사유 차이</h3>
      </div>
      <table>
        <thead>
          <tr>
            <th>비교 판례</th>
            <th>공통 조문</th>
            <th>판단 사유</th>
            <th>판결 결과</th>
          </tr>
        </thead>
        <tbody>${rows || `<tr><td colspan="4">비교할 후보 판례가 없습니다.</td></tr>`}</tbody>
      </table>
      <p class="notice compact">
        판결 결과 요약은 검색 보조 정보입니다. 사실관계와 법원의 판단 이유는 공식 원문에서 직접 확인해야 합니다.
      </p>
    </div>
  `;
}

function renderCompactMeta(item) {
  const outcome = formatOutcomeLabel(item.outcome_label);
  return `
    <dl class="meta-list">
      <dt>참조 조문</dt><dd>${(item.referenced_statutes || []).map(escapeHtml).join(", ") || "없음"}</dd>
      <dt>판단 사유</dt><dd>${escapeHtml(item.decision_point)}</dd>
      <dt>판결 결과</dt><dd>${escapeHtml(outcome)}</dd>
    </dl>
  `;
}

function formatOutcomeLabel(value) {
  const label = String(value ?? "").trim();
  if (!label || label === "원문 확인 필요") {
    return "구조화 결과 없음";
  }
  return label;
}

function buildFallbackSearchQuery() {
  const facts = state.intake?.extracted_facts ? JSON.stringify(state.intake.extracted_facts) : "";
  return [state.messages.map((message) => message.content).join(" "), facts].filter(Boolean).join("\n");
}

async function postJson(path, payload) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function flattenResults(results) {
  return Object.values(results || {}).flat();
}

function setLoading(message) {
  questionListEl.innerHTML = `<p class="empty-state">${escapeHtml(message)}</p>`;
}

function renderError(message, error) {
  questionListEl.innerHTML = renderErrorCard(message, error);
}

function renderErrorCard(message, error) {
  return `<p class="empty-state">${escapeHtml(message)}<br />${escapeHtml(error?.message || "")}</p>`;
}

function showView(name) {
  Object.entries(views).forEach(([key, element]) => {
    element.classList.toggle("hidden", key !== name);
  });
  window.scrollTo({ top: 0, behavior: "instant" });
}

function uniqueById(values) {
  const seen = new Set();
  return values.filter((item) => {
    if (!item || seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}
