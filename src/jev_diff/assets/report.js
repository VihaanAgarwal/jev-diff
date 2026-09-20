"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const own = (obj, key) => obj && Object.prototype.hasOwnProperty.call(obj, key) ? obj[key] : undefined;
  const text = (value) => typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const number = (value) => value == null ? "Absent" : String(value);
  const percent = (value) => `${Number((value * 100).toPrecision(6))}%`;
  const node = (tag, className, content) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (content != null) element.textContent = content;
    return element;
  };
  const append = (parent, tag, className, content) => {
    const element = node(tag, className, content);
    parent.append(element);
    return element;
  };
  const names = {
    threshold_crossed: "Gate crossed", choice_changed: "Label changed",
    distribution_shift: "Distribution shifted", question_changed: "Question changed",
    state_changed: "State changed", case_added: "Case added", case_removed: "Case removed",
    question_added: "Question added", question_removed: "Question removed", gate_changed: "Gate changed",
  };
  const plural = (count, singular, multiple = `${singular}s`) => `${count} ${count === 1 ? singular : multiple}`;
  let data;
  try {
    data = JSON.parse($("data").textContent);
  } catch {
    $("overview-text").textContent = "The embedded data could not be read. Generate the report again from your JSONL files.";
    return;
  }
  const { report, before, after, policy, candidate_policy: newPolicy } = data;
  const ids = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
  const changes = new Map(ids.map(id => [id, []]));
  const notices = new Map(ids.map(id => [id, []]));
  for (const item of report.changes) changes.get(item.case).push(item);
  for (const item of report.notices) notices.get(item.case).push(item);
  const rank = (id) => changes.get(id).some(c => c.kind === "threshold_crossed") ? 0 : changes.get(id).length ? 1 : 2;
  ids.sort((a, b) => rank(a) - rank(b));
  let selected;
  let visible = [];
  let shown = 0;
  const pageSize = 100;
  const summary = report.summary;
  $("overview-text").textContent = summary.changes
    ? `${plural(summary.changed_cases, "case")} with changes to inspect. Start with the gates, then check the underlying answers.`
    : "No changes flagged under the configured checks. Inspect any case to review its evidence.";
  for (const [label, name, count] of [
    ["Baseline", data.labels.baseline, summary.baseline_cases],
    ["Candidate", data.labels.candidate, summary.candidate_cases],
  ]) {
    const source = append($("sources"), "div", "source");
    append(source, "b", "", label);
    append(source, "code", "", name);
    append(source, "span", "", `(${plural(count, "case")})`);
  }
  for (const [count, label, attention] of [
    [summary.compared_answers, "answers compared", false],
    [summary.changes, "changes", true],
    [report.changes.filter(c => c.kind === "threshold_crossed").length, "gate crossings", true],
    [report.notices.length, "notices", false],
  ]) {
    const stat = append($("summary"), "div", `stat${attention && count ? " attention" : ""}`);
    append(stat, "strong", "", count);
    append(stat, "span", "", label);
  }
  $("download").disabled = false;
  $("download").addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2) + "\n"], { type: "application/json" }));
    const link = node("a");
    link.href = url;
    link.download = "jev-diff.json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  function description(change) {
    switch (change.kind) {
      case "threshold_crossed":
        return `${change.field}: ${number(change.before)} → ${number(change.after)}. ${change.before_side === "below" ? "Below" : "At or above"} the baseline gate; ${change.after_side === "below" ? "below" : "at or above"} the candidate gate.`;
      case "choice_changed": return `${change.before} → ${change.after}.`;
      case "distribution_shift": return `Distance ${number(change.distance)} exceeds the configured limit of ${number(change.limit)}.`;
      case "question_changed": return "Instructions, type, or criteria changed. Read both question definitions below.";
      case "gate_changed": return `${change.gate}: ${number(change.before)} → ${number(change.after)}.`;
      default: return "";
    }
  }

  function answerSide(parent, record, name, candidate) {
    const side = append(parent, "div", `answer-side${candidate ? " candidate" : ""}`);
    append(side, "div", "side-label", candidate ? "Candidate" : "Baseline");
    const answer = own(record?.response.answers, name);
    if (!answer) {
      append(side, "div", "answer-value", "Absent");
      return;
    }
    append(side, "div", "answer-value", answer.type === "choice" ? answer.choice : number(answer[answer.type]));
    append(side, "div", "answer-meta", answer.type === "noul" ? "Noul probability" : `Confidence ${number(answer.confidence)}`);
  }

  function gates(parent, old, next, name, question) {
    const left = own(policy, name) || {};
    const right = own(newPolicy, name) || {};
    const configured = [...new Set([...Object.keys(left), ...Object.keys(right)])].sort();
    for (const key of configured) {
      const field = key === "confidence" ? "confidence" : old.type;
      const max = field === "score" ? question.criteria.length - 1 : 1;
      const section = append(parent, "div", "gate");
      const heading = append(section, "div", "gate-heading");
      append(heading, "strong", "", `${field === "confidence" ? "Confidence" : "Value"} gate`);
      append(heading, "span", "", left[key] === right[key]
        ? `Threshold ${number(left[key])}`
        : `Threshold ${number(left[key])} → ${number(right[key])}`);
      for (const [answer, threshold, label] of [[old, left[key], "Baseline"], [next, right[key], "Candidate"]]) {
        const row = append(section, "div", `gate-row${label === "Candidate" ? " candidate" : ""}`);
        append(row, "span", "", label);
        const track = append(row, "div", "gate-track");
        track.setAttribute("aria-hidden", "true");
        if (threshold != null) append(track, "span", "gate-threshold").style.left = `${threshold / max * 100}%`;
        append(track, "span", "gate-point").style.left = `${answer[field] / max * 100}%`;
        const value = number(answer[field]);
        const comparison = threshold == null ? "no gate" : `${answer[field] >= threshold ? "≥" : "<"} ${number(threshold)}`;
        append(row, "span", "gate-result", `${value} ${comparison}`);
      }
      const scale = append(section, "div", "gate-scale");
      scale.setAttribute("aria-hidden", "true");
      append(scale, "span", "", "0");
      append(scale, "span", "", number(max));
    }
    if (!configured.length) append(parent, "p", "subtle-note", "No gates configured for this question.");
  }

  function distribution(parent, old, next, question) {
    const section = append(parent, "div", "distribution");
    append(section, "div", "evidence-label", old.type === "noul" ? "Probability" : "Answer distribution");
    const legend = append(section, "div", "legend");
    append(legend, "span", "", "Baseline");
    append(legend, "span", "candidate", "Candidate");
    const left = old.type === "noul" ? { Noul: old.noul } : old.probabilities;
    const right = next.type === "noul" ? { Noul: next.noul } : next.probabilities;
    for (const key of Object.keys(left)) {
      const row = append(section, "div", "probability");
      const label = append(row, "div", "label", key);
      if (old.type === "score") append(label, "small", "", text(question.criteria[Number(key)]));
      const bars = append(row, "div", "bars");
      bars.setAttribute("aria-hidden", "true");
      for (const [value, candidate] of [[left[key], false], [right[key], true]]) {
        const track = append(bars, "div", "bar");
        append(track, "div", `bar-fill${candidate ? " candidate" : ""}`).style.width = `${value * 100}%`;
      }
      const values = append(row, "div", "values");
      const a = append(values, "span", "", percent(left[key]));
      a.setAttribute("aria-label", `Baseline ${percent(left[key])}`);
      const b = append(values, "span", "", percent(right[key]));
      b.setAttribute("aria-label", `Candidate ${percent(right[key])}`);
    }
    append(section, "p", "subtle-note", `Distribution shift limit: ${number(data.max_tv)}. Bars show recorded probabilities.`);
  }

  function rawDetails(parent, title, left, right) {
    const details = append(parent, "details");
    append(details, "summary", "", title);
    const grid = append(details, "div", "raw");
    for (const [label, value] of [["Baseline", left], ["Candidate", right]]) {
      const column = append(grid, "div");
      append(column, "div", "side-label", label);
      append(column, "pre", "", value == null ? "Absent" : JSON.stringify(value, null, 2));
    }
    return details;
  }

  function showDetail(id) {
    const detail = $("detail");
    detail.replaceChildren();
    if (!id) {
      const empty = append(detail, "div", "empty");
      append(empty, "h2", "", "No matching cases");
      append(empty, "p", "", "Try another search or include all cases.");
      const reset = append(empty, "button", "", "Show all cases");
      reset.type = "button";
      reset.addEventListener("click", () => {
        $("search").value = "";
        $("filter").value = "all";
        updateList();
        $("search").focus();
      });
      return;
    }
    const left = own(before, id);
    const right = own(after, id);
    const items = changes.get(id);
    const caseNotices = notices.get(id);
    const stateChanged = items.some(c => c.kind === "state_changed");
    const header = append(detail, "div", "case-header");
    append(header, "p", "eyebrow", "CASE REVIEW");
    append(header, "h2", "", id);
    append(header, "p", "", items.length ? `${plural(items.length, "change")} to inspect` : "No changes flagged under the configured checks");
    if (stateChanged) append(detail, "p", "warning", "State digests differ. Answers were not compared for this case; the two runs received different state. Values below are evidence from each run, not a measured model regression.");
    if (!left || !right) append(detail, "p", "warning", !left ? "This case exists only in the candidate. No baseline answer is available to compare." : "This case is missing from the candidate. No candidate answer is available to compare.");
    if (caseNotices.length) {
      const box = append(detail, "div", "notices");
      for (const notice of caseNotices) {
        append(box, "p", "", notice.kind === "model_changed"
          ? `Model: ${notice.before} → ${notice.after}. A model change alone is a notice.`
          : `${notice.question}: ${notice.gate} gate moved from ${number(notice.before)} to ${number(notice.after)}.`);
      }
    }
    const questionNames = [...new Set([...Object.keys(left?.questions || {}), ...Object.keys(right?.questions || {})])].sort();
    const questionChanges = new Map(questionNames.map(name => [name, items.filter(c => c.question === name)]));
    questionNames.sort((a, b) => Number(!questionChanges.get(a).length) - Number(!questionChanges.get(b).length));
    let unchanged;
    const unchangedCount = questionNames.filter(name => !questionChanges.get(name).length).length;
    if (!stateChanged && unchangedCount && items.some(c => c.question !== null)) {
      unchanged = node("details", "unchanged-questions");
      append(unchanged, "summary", "", `${plural(unchangedCount, "question")} without flagged changes`);
    }
    for (const name of questionNames) {
      const a = own(left?.questions, name), b = own(right?.questions, name);
      const old = own(left?.response.answers, name), next = own(right?.response.answers, name);
      const found = questionChanges.get(name);
      const article = append(unchanged && !found.length ? unchanged : detail, "section", "question");
      const head = append(article, "div", "question-head");
      const title = append(head, "div", "question-title");
      append(title, "h3", "mono", name);
      append(title, "span", "pill", a && b && a.type !== b.type ? `${a.type} → ${b.type}` : (b || a).type);
      append(head, "p", "", text((b || a).instructions));
      if (found.length) {
        const findings = append(article, "div", "findings");
        for (const change of found) {
          const item = append(findings, "p", "finding");
          append(item, "strong", "", `${names[change.kind]}. `);
          item.append(document.createTextNode(description(change)));
        }
      }
      const evidence = append(article, "div", "evidence");
      const pair = append(evidence, "div", "answer-pair");
      answerSide(pair, left, name, false);
      answerSide(pair, right, name, true);
      const spaceChanged = a && b && (a.type !== b.type || JSON.stringify(a.criteria) !== JSON.stringify(b.criteria));
      if (spaceChanged) append(evidence, "p", "warning", "The type or criteria changed. Numeric comparisons were skipped because the answer spaces differ.");
      if (!stateChanged && !spaceChanged && old && next) {
        gates(evidence, old, next, name, b);
        distribution(evidence, old, next, b);
      }
      rawDetails(article, "Question definitions and recorded answers", a ? { question: a, answer: old } : null, b ? { question: b, answer: next } : null);
    }
    if (unchanged) detail.append(unchanged);
    const metadata = rawDetails(detail, "Model, state digest, and policy", left ? { model: left.response.model, state_hash: left.state_hash, policy } : null, right ? { model: right.response.model, state_hash: right.state_hash, policy: newPolicy } : null);
    metadata.className = "case-metadata";
  }

  function choose(id, navigate = false) {
    selected = id;
    for (const link of $("cases").querySelectorAll("a[data-case]")) {
      if (link.dataset.case === id) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
    showDetail(id);
    if (navigate && window.matchMedia("(max-width: 620px)").matches) {
      $("detail").focus();
      $("detail").scrollIntoView();
    }
  }

  function appendPage() {
    $("more-cases")?.remove();
    const fragment = document.createDocumentFragment();
    for (const id of visible.slice(shown, shown + pageSize)) {
      const items = changes.get(id);
      const link = append(fragment, "a", "case");
      // JSON also preserves escaped lone surrogates, which URI encoding rejects.
      link.href = `#case=${encodeURIComponent(JSON.stringify(id))}`;
      link.dataset.case = id;
      if (id === selected) link.setAttribute("aria-current", "true");
      const title = append(link, "div", "case-title");
      append(title, "code", "", id);
      if (items.length) append(title, "span", "count", items.length);
      const kinds = [...new Set(items.map(c => names[c.kind]))];
      append(link, "div", "case-subtitle", kinds.length ? kinds.join(" · ") : "No flagged changes");
    }
    shown = Math.min(shown + pageSize, visible.length);
    $("cases").append(fragment);
    if (shown < visible.length) {
      const more = append($("cases"), "button", "", `Show next ${Math.min(pageSize, visible.length - shown)} cases`);
      more.id = "more-cases";
      more.type = "button";
      more.addEventListener("click", () => {
        const firstNew = shown;
        appendPage();
        $("cases").querySelectorAll("a[data-case]")[firstNew]?.focus();
      });
    }
  }

  function updateList() {
    const search = $("search").value.trim().toLocaleLowerCase();
    const filter = $("filter").value;
    visible = ids.filter(id => {
      const recordNames = [...Object.keys(own(before, id)?.questions || {}), ...Object.keys(own(after, id)?.questions || {})];
      if (![id, ...recordNames].some(value => value.toLocaleLowerCase().includes(search))) return false;
      const items = changes.get(id);
      if (filter === "all") return true;
      if (filter === "changed") return !!items.length;
      if (filter === "unchanged") return !items.length;
      if (filter === "contract") return items.some(item => !["threshold_crossed", "choice_changed", "distribution_shift"].includes(item.kind));
      return items.some(item => item.kind === filter);
    });
    $("case-count").textContent = `${visible.length} / ${ids.length}`;
    $("cases").replaceChildren();
    shown = 0;
    if (!visible.includes(selected)) selected = visible[0];
    appendPage();
    if (!visible.length) append($("cases"), "p", "list-empty", "No cases match these filters.");
    choose(selected);
  }

  $("search").addEventListener("input", updateList);
  $("filter").addEventListener("change", updateList);
  $("cases").addEventListener("click", event => {
    const link = event.target.closest("a[data-case]");
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    choose(link.dataset.case, true);
    try { history.replaceState(null, "", link.getAttribute("href")); } catch { /* file viewers may restrict history */ }
  });
  $("cases").addEventListener("keydown", event => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) || event.target.tagName !== "A") return;
    const links = [...$("cases").querySelectorAll("a[data-case]")];
    let index = links.indexOf(event.target);
    if (index < 0) return;
    event.preventDefault();
    index = event.key === "Home" ? 0 : event.key === "End" ? links.length - 1 : Math.max(0, Math.min(links.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)));
    links[index].focus();
    choose(links[index].dataset.case);
  });
  function fromHash() {
    if (!location.hash.startsWith("#case=")) return;
    let id;
    try { id = JSON.parse(decodeURIComponent(location.hash.slice(6))); } catch { return; }
    if (!changes.has(id)) return;
    selected = id;
    $("filter").value = "all";
    $("search").value = "";
    updateList();
    while (shown < visible.indexOf(id) + 1) appendPage();
  }
  window.addEventListener("hashchange", fromHash);
  $("filter").value = summary.changes ? "changed" : "all";
  updateList();
  fromHash();
})();
