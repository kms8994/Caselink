const API_BASE_URL = "http://127.0.0.1:8001/api";

const state = {
  messages: [],
  currentFacts: {},
  intake: null,
  searchResponse: null,
  base: null,
  results: [],
  queryType: "natural",
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
const queryTypeInput = document.querySelector("#query-type");
const queryHintEl = document.querySelector("#query-hint");
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
  auto: "자동",
  statute: "조문",
  case_no: "사건번호",
  natural: "텍스트 입력",
};

const domainLabels = {
  employment: "근로/임금",
  labor: "근로/임금",
  housing_lease: "주택임대차",
  lease: "임대차",
  damages: "손해배상",
  unjust_enrichment: "부당이득",
  debt: "채무",
  property: "물권",
  inheritance: "상속",
  unknown: "미분류",
};

const fieldLabels = {
  employment_type: "근로 형태",
  employment_duration: "근무 기간",
  payment_details: "임금 지급 내역",
  unpaid_amount: "미지급 금액",
  employer_details: "사업주 정보",
  work_schedule: "근무 일정",
  wage_amount: "약정 임금",
  contract_type: "계약 형태",
  dispute_type: "분쟁 유형",
  important_date: "중요 날짜",
  opposing_party: "상대방 주장",
  desired_outcome: "원하는 결과",
};

const queryTypeHints = {
  auto: "입력 내용을 보고 사건번호, 조문, 자연어 검색을 자동으로 판단합니다.",
  natural: "사건의 사실관계나 쟁점을 문장으로 입력해 유사 판례를 찾습니다.",
  statute: "예: 주택임대차보호법 제3조처럼 조문을 중심으로 검색합니다.",
  case_no: "예: 2024다268508처럼 사건번호로 기준 판례를 찾습니다.",
};

const queryTypePlaceholders = {
  auto: "예: 임대차보증금을 돌려받지 못했고 임차권등기와 대항력이 문제됩니다.",
  natural: "예: 임대인이 보증금을 반환하지 않은 상태에서 임차인이 계속 거주했습니다.",
  statute: "예: 주택임대차보호법 제3조",
  case_no: "예: 2024다268508",
};

const groupLabels = {
  statute_related: "관련 조문 판례",
  fact_similar: "사실관계 유사 판례",
  different_decision_point: "판단 사유가 다른 판례",
};

const groupDescriptions = {
  statute_related: "같거나 가까운 조문을 중심으로 확인할 후보입니다.",
  fact_similar: "사건의 사실관계가 비슷해 비교 검토가 필요한 후보입니다.",
  different_decision_point: "쟁점은 비슷하지만 법원이 본 판단 사유가 다른 후보입니다.",
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await startIntake(queryInput.value);
});

queryInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey) return;
  event.preventDefault();
  form.requestSubmit();
});

answerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const answers = [...document.querySelectorAll(".question-answer")]
    .map((textarea) => textarea.value.trim())
    .filter(Boolean);
  const answer = answers.join("\n\n");
  if (!answer) return;
  state.messages.push({ role: "user", content: answer });
  await runIntake();
});

questionListEl.addEventListener("keydown", (event) => {
  if (!event.target.classList.contains("question-answer")) return;
  if (event.key !== "Enter" || event.shiftKey) return;
  event.preventDefault();
  answerForm.requestSubmit();
});

document.querySelectorAll("[data-query-type]").forEach((button) => {
  button.addEventListener("click", () => setQueryType(button.dataset.queryType));
});

document.querySelectorAll("[data-action='back-search']").forEach((button) => {
  button.addEventListener("click", () => showView("search"));
});

document.querySelector("[data-action='back-results']").addEventListener("click", () => showView("results"));

setQueryType(queryTypeInput?.value || "natural");

async function startIntake(query) {
  const content = query.trim();
  if (!content) return;
  if (state.queryType === "statute" || state.queryType === "case_no") {
    await runSearch(content);
    return;
  }
  state.messages = [{ role: "user", content }];
  state.currentFacts = {};
  state.intake = null;
  setLoading("사건 정보를 확인하고 있습니다.");
  showView("intake");
  await runIntake();
}

async function runIntake() {
  try {
    setLoading("검색에 필요한 사실관계를 판단하고 있습니다.");
    const response = await postJson("/intake", {
      messages: state.messages,
      current_facts: state.currentFacts,
    });
    state.intake = response;
    state.currentFacts = response.extracted_facts || {};

    if (response.status === "ready") {
      await runSearch(response.search_query || buildSearchQueryFromMessages());
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
      query_type: state.queryType,
    });
    state.searchResponse = response;
    state.base = response.base_precedent;
    state.results = flattenResults(response.results);
    renderResults(response);
    showView("results");
  } catch (error) {
    baseCaseEl.classList.add("hidden");
    resultsEl.innerHTML = renderErrorCard("검색 중 오류가 발생했습니다. 백엔드 서버 상태를 확인해주세요.", error);
    showView("results");
  }
}

function renderIntake(intake) {
  intakeDomainEl.textContent = formatDomainLabel(intake.domain);
  missingFieldsEl.innerHTML = intake.missing_fields?.length
    ? intake.missing_fields.map((field) => `<span>${escapeHtml(formatFieldLabel(field))}</span>`).join("")
    : "<span>추가 확인 없음</span>";
  const questions = (intake.follow_up_questions || []).slice(0, 1);
  questionListEl.innerHTML = questions.length
    ? questions.map((question, index) => renderQuestion(question, index)).join("")
    : "<p>충분한 정보가 모였습니다. 검색으로 이동합니다.</p>";
}

function renderQuestion(question, index) {
  const id = `question-answer-${index}`;
  return `
    <section class="question-card">
      <label for="${id}"><strong>Q${index + 1}.</strong> ${escapeHtml(question)}</label>
      <textarea
        id="${id}"
        class="question-answer"
        rows="4"
        placeholder="답변을 입력하고 Enter를 누르면 검색합니다. 줄바꿈은 Shift+Enter입니다."
      ></textarea>
    </section>
  `;
}

function renderResults(response) {
  const hasResults = flattenResults(response.results).length > 0;
  detectedTypeEl.textContent = queryTypeLabels[response.detected_query_type] || response.detected_query_type;
  statutesEl.innerHTML = response.related_statutes?.length
    ? response.related_statutes.map((statute) => `<span>${escapeHtml(statute)}</span>`).join("")
    : "<span>관련 조문 정보 없음</span>";

  if (response.base_precedent && hasResults) {
    baseCaseEl.classList.remove("hidden");
    baseCaseEl.innerHTML = renderBaseCase(response.base_precedent);
  } else if (hasResults) {
    baseCaseEl.classList.remove("hidden");
    baseCaseEl.innerHTML = renderInputCase(response);
  } else {
    baseCaseEl.classList.add("hidden");
    baseCaseEl.innerHTML = "";
  }

  resultsEl.innerHTML = renderGroupedResults(response.results || {});

  document.querySelectorAll("[data-compare-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const clicked = state.results.find((item) => item.id === button.dataset.compareId);
      renderCompare(clicked);
      showView("compare");
    });
  });
}

function renderBaseCase(item) {
  return `
    <div class="section-title">
      <p class="eyebrow">기준 판례</p>
      <h3>${escapeHtml(item.case_no)}</h3>
    </div>
    <p class="case-name">${escapeHtml(item.case_name)}</p>
    ${renderCompactMeta(item)}
    <div class="inline-actions">
      <a href="${escapeAttribute(item.source_url)}" target="_blank" rel="noreferrer">공식 원문 열기</a>
    </div>
  `;
}

function renderInputCase(response) {
  return `
    <div class="section-title">
      <p class="eyebrow">입력 사건</p>
      <h3>입력한 사건 설명 기준</h3>
    </div>
    <p class="case-name">${escapeHtml(summarizeText(response.query, 180))}</p>
    <dl class="meta-list">
      <dt>입력 유형</dt><dd>${escapeHtml(queryTypeLabels[response.detected_query_type] || response.detected_query_type)}</dd>
      <dt>조문 후보</dt><dd>${(response.related_statutes || []).map(escapeHtml).join(", ") || "없음"}</dd>
    </dl>
  `;
}

function renderGroupedResults(results) {
  const nonEmptyGroups = Object.entries(groupLabels).filter(([group]) => (results[group] || []).length > 0);
  if (!nonEmptyGroups.length) {
    return `
      <section class="result-empty-state">
        <h3>관련 판례가 없습니다.</h3>
        <p>현재 입력과 충분히 관련 있는 판례를 찾지 못했습니다. 사건번호, 조문, 핵심 사실을 더 구체적으로 입력해보세요.</p>
      </section>
    `;
  }

  return nonEmptyGroups
    .map(([group, label]) => {
      const items = results[group] || [];
      return `
        <section class="result-section">
          <div class="result-section-header">
            <div>
              <h3>${escapeHtml(label)}</h3>
              <p>${escapeHtml(groupDescriptions[group])}</p>
            </div>
            <span>${items.length}건</span>
          </div>
          <div class="result-list">
            ${items.map((item) => renderResultCard(item)).join("")}
          </div>
        </section>
      `;
    })
    .join("");
}

function renderResultCard(item) {
  const issue = summarizeText(item.legal_issue_summary, 170);
  return `
    <article class="result-card">
      <div class="card-kicker">${escapeHtml(groupLabels[item.group] || item.result_label)}</div>
      <div class="case-topline">
        <strong>${escapeHtml(item.case_no)}</strong>
        <span>${escapeHtml(item.decision_date)}</span>
      </div>
      <h3>${escapeHtml(item.case_name)}</h3>
      <p>${escapeHtml(issue)}</p>
      ${renderCompactMeta(item)}
      <div class="card-actions">
        <button type="button" data-compare-id="${escapeAttribute(item.id)}">비교 보기</button>
        <a href="${escapeAttribute(item.source_url)}" target="_blank" rel="noreferrer">원문</a>
      </div>
    </article>
  `;
}

function renderCompare(clicked) {
  const base = state.base || buildInputCaseBase();
  if (!base || !clicked) return;
  const comparisons = clicked.id === base.id ? [] : [clicked];
  const columns = [base, ...comparisons];

  compareBoardEl.classList.toggle("is-pair", columns.length === 2);
  compareBoardEl.innerHTML = columns
    .map((item, index) => renderCompareColumn(index === 0 ? (item.isInputCase ? "입력 사건" : "기준 판례") : `비교 판례 ${index}`, item, base))
    .join("");
  compareSummaryEl.innerHTML = renderCompareSummary(base, comparisons);
}

function renderCompareColumn(title, item, base) {
  const statutes = item.referenced_statutes || [];
  const commonStatutes = (base.referenced_statutes || []).filter((statute) => statutes.includes(statute));
  const outcome = formatOutcomeLabel(item.outcome_label);
  const outcomeRow = outcome ? `<dt>판결 결과</dt><dd>${escapeHtml(outcome)}</dd>` : "";
  const sourceLink = item.source_url
    ? `<a href="${escapeAttribute(item.source_url)}" target="_blank" rel="noreferrer">공식 원문 열기</a>`
    : "";
  return `
    <article class="compare-column ${title === "기준 판례" || title === "입력 사건" ? "base-column" : ""}">
      <p class="eyebrow">${title}</p>
      <h3>${escapeHtml(item.case_no)}</h3>
      <p class="case-name">${escapeHtml(item.case_name)}</p>
      <dl>
        <dt>${item.isInputCase ? "조문 후보" : "참조 조문"}</dt><dd>${statutes.map(escapeHtml).join(", ") || "없음"}</dd>
        <dt>공통 조문</dt><dd>${commonStatutes.length ? commonStatutes.map(escapeHtml).join(", ") : "없음"}</dd>
        <dt>쟁점</dt><dd>${escapeHtml(summarizeText(item.legal_issue_summary, 180))}</dd>
        <dt>사실관계</dt><dd>${escapeHtml(extractFactBasis(item, 190))}</dd>
        <dt>판단 사유</dt><dd>${escapeHtml(extractDecisionBasis(item, 190))}</dd>
        ${outcomeRow}
      </dl>
      ${sourceLink}
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
          <td>${escapeHtml(extractDecisionBasis(item, 170))}</td>
          <td>${escapeHtml(formatOutcomeLabel(item.outcome_label) || "요약 없음")}</td>
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
      ${renderComparisonEvidence(base, comparisons)}
      <p class="notice compact">
        판결 결과 요약은 검색 보조 정보입니다. 사실관계와 법원의 판단 이유는 공식 원문에서 직접 확인해야 합니다.
      </p>
    </div>
  `;
}

function renderComparisonEvidence(base, comparisons) {
  const evidenceCards = comparisons
    .filter((item) => item.id !== base.id)
    .map((item) => {
      const commonStatutes = (base.referenced_statutes || []).filter((statute) => (item.referenced_statutes || []).includes(statute));
      const basisRows = [
        ["공통 조문", commonStatutes.length ? commonStatutes.join(", ") : "공통 조문 없음"],
        ["기준 사실관계", extractFactBasis(base, 210)],
        ["비교 사실관계", extractFactBasis(item, 210)],
        ["기준 판단 사유", extractDecisionBasis(base, 210)],
        ["비교 판단 사유", extractDecisionBasis(item, 210)],
      ];

      return `
        <article class="evidence-card">
          <div class="case-topline">
            <strong>${escapeHtml(item.case_no)}</strong>
            <span>${escapeHtml(item.case_name)}</span>
          </div>
          <dl>
            ${basisRows
              .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`)
              .join("")}
          </dl>
        </article>
      `;
    })
    .join("");

  if (!evidenceCards) return "";
  return `
    <section class="comparison-evidence" aria-label="비교 근거">
      <div class="section-title">
        <p class="eyebrow">비교 근거</p>
        <h3>비교에 사용한 원문 발췌 항목</h3>
      </div>
      <div class="evidence-list">
        ${evidenceCards}
      </div>
    </section>
  `;
}

function buildInputCaseBase() {
  const response = state.searchResponse;
  if (!response) return null;
  return {
    id: "__input_case__",
    case_no: "입력 사건",
    case_name: summarizeText(response.query, 120),
    referenced_statutes: response.related_statutes || [],
    legal_issue_summary: response.query,
    fact_summary: response.query,
    decision_point: "입력 사건은 법원의 판단 사유가 없는 사용자 설명입니다. 후보 판례의 판단 사유와 대조해 검토하세요.",
    outcome_label: "",
    source_url: "",
    isInputCase: true,
  };
}

function renderCompactMeta(item) {
  const outcome = formatOutcomeLabel(item.outcome_label);
  const outcomeRow = outcome ? `<dt>판결 결과</dt><dd>${escapeHtml(outcome)}</dd>` : "";
  return `
    <dl class="meta-list">
      <dt>참조 조문</dt><dd>${(item.referenced_statutes || []).map(escapeHtml).join(", ") || "없음"}</dd>
      <dt>판단 사유</dt><dd>${escapeHtml(summarizeText(item.decision_point, 150))}</dd>
      ${outcomeRow}
    </dl>
  `;
}

function setQueryType(type) {
  state.queryType = type || "natural";
  if (queryTypeInput) queryTypeInput.value = state.queryType;
  if (queryHintEl) queryHintEl.textContent = queryTypeHints[state.queryType] || queryTypeHints.natural;
  queryInput.placeholder = queryTypePlaceholders[state.queryType] || queryTypePlaceholders.natural;
  document.querySelectorAll("[data-query-type]").forEach((button) => {
    button.classList.toggle("is-selected", button.dataset.queryType === state.queryType);
  });
}

function formatDomainLabel(value) {
  const key = String(value ?? "").trim();
  return domainLabels[key] || key || "미분류";
}

function formatFieldLabel(value) {
  const key = String(value ?? "").trim();
  return fieldLabels[key] || key.replaceAll("_", " ") || "추가 정보";
}

function summarizeText(value, maxLength = 160) {
  const text = cleanText(value);
  if (!text || text.length <= 2) return "요약 없음";
  return text.length > maxLength ? `${text.slice(0, maxLength).trim()}...` : text;
}

function extractFactBasis(item, maxLength = 190) {
  const factText = cleanText(item?.fact_summary);
  const issueText = cleanText(item?.legal_issue_summary);
  const source = isWeakFactText(factText) && issueText !== "요약 없음" ? issueText : factText;
  return excerptText(source, maxLength);
}

function extractDecisionBasis(item, maxLength = 190) {
  const decisionText = cleanText(item?.decision_point ?? item);
  const issueText = cleanText(item?.legal_issue_summary);
  const source = isWeakDecisionText(decisionText) && issueText !== "요약 없음" ? issueText : decisionText;
  return excerptText(source, maxLength);
}

function excerptText(value, maxLength = 190) {
  const text = cleanText(value);
  if (!text || text === "요약 없음") return text;
  if (text.length <= maxLength) return text;

  const clipped = text.slice(0, maxLength);
  const naturalEndings = ["다. ", "된다. ", "한다. ", "여부 ", "사건]", "사건】"];
  const boundary = naturalEndings
    .map((marker) => clipped.lastIndexOf(marker))
    .filter((index) => index >= Math.floor(maxLength * 0.55))
    .sort((left, right) => right - left)[0];

  if (boundary !== undefined) {
    const marker = naturalEndings.find((ending) => clipped.startsWith(ending, boundary)) || "";
    return `${clipped.slice(0, boundary + marker.length).trim()}...`;
  }

  const commaBoundary = Math.max(clipped.lastIndexOf(", "), clipped.lastIndexOf("，"), clipped.lastIndexOf("] "));
  if (commaBoundary >= Math.floor(maxLength * 0.65)) {
    return `${clipped.slice(0, commaBoundary + 1).trim()}...`;
  }

  return `${clipped.trim()}...`;
}

function isWeakFactText(text) {
  if (!text || text === "요약 없음") return true;
  const proceduralSignals = ["【원 고】", "【피 고】", "소송대리인", "【주 문】", "【변론종결】", "【원심판결】"];
  return proceduralSignals.some((signal) => text.includes(signal)) && !/(계약|매수|임대|소유|지급|손해|근무|임금|보증금|공사|분양)/.test(text.slice(0, 220));
}

function isWeakDecisionText(text) {
  if (!text || text === "요약 없음") return true;
  if (text.length < 60) return true;
  if (/^\[?\d+\]?\s*[^가-힣A-Za-z]*[^.。！？]{0,40}\d{4}\.\s*\d{1,2}\.?$/.test(text)) return true;
  return false;
}

function cleanText(value) {
  const boilerplate = [
    "국가법령정보센터 자바스크립트를 지원하지 않아 일부 기능을 사용할 수 없습니다.",
    "본문 바로가기",
    "판례정보 본문",
    "판결요지 참조조문 참조판례 전문",
    "관련자료 판례체계도 첨부파일",
    "점자뷰어 화면내검색 팝업여부",
    "카카오톡 페이스북 트위터 라인 주소복사",
  ];
  let text = String(value ?? "").replace(/\s+/g, " ").trim();
  text = text.replace(/판례\s*>\s*[^|]+?\|\s*/g, "");
  boilerplate.forEach((phrase) => {
    text = text.replaceAll(phrase, "");
  });
  text = text.replace(/\s+/g, " ").trim();
  return text || "요약 없음";
}

function formatOutcomeLabel(value) {
  const label = String(value ?? "").trim();
  if (!label || label === "원문 확인 필요" || label === "구조화 결과 없음") {
    return "";
  }
  return label;
}

function buildSearchQueryFromMessages() {
  return state.messages.map((message) => message.content).join("\n\n");
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
