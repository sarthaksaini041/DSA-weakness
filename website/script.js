"use strict";
let data,
  current,
  visible = 6;
const $ = (id) => document.getElementById(id);
function node(tag, text, className) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (className) n.className = className;
  return n;
}
const percent = (n) => `${(n * 100).toFixed(1)}%`;
function chooseUser(handle) {
  const user = data.examples.find((x) => x.handle.toLowerCase() === handle.trim().toLowerCase());
  if (!user) {
    $("handle-error").textContent =
      "This handle is not in the saved examples. Choose one of the three listed handles; live lookup is not available.";
    return;
  }
  current = user;
  visible = 6;
  $("handle").value = user.handle;
  $("handle-error").textContent = "";
  $("user-summary").textContent =
    `${user.handle} · ${user.mode} · ${user.evidence_rows} evidence rows · Historical rating: ${user.historical_rating ?? "Not rated"} · Saved ${new Date(user.as_of).toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata" })}`;
  $("topics").replaceChildren();
  if (!user.topics.length)
    $("topics").append(
      node(
        "p",
        "No mature topic evidence is available. The suggestions below are for exploration, not diagnosed weaknesses.",
        "notice",
      ),
    );
  user.topics.forEach((t) => {
    const card = node("button", undefined, "topic");
    card.type = "button";
    card.setAttribute("aria-label", `Filter practice problems by ${t.topic}: ${t.status}`);
    card.append(
      node("h4", t.topic),
      node("span", t.status, `pill ${t.status === "Insufficient evidence" ? "sparse" : ""}`),
      node("span", `${t.accepted}/${t.attempts} accepted`, "topic-value"),
      node(
        "span",
        `${t.matched_attempts} matched attempts · ${t.reference_problems} comparison problems`,
        "small",
      ),
    );
    if (t.relative_gap !== null)
      card.append(
        node(
          "span",
          `Relative gap: ${(100 * t.relative_gap).toFixed(1)} percentage points`,
          "small",
        ),
      );
    card.append(
      node(
        "span",
        `Observed rate interval: ${percent(t.acceptance_interval[0])}–${percent(t.acceptance_interval[1])}`,
        "small",
      ),
    );
    card.addEventListener("click", () => {
      $("topic-filter").value = t.topic;
      visible = 6;
      renderProblems();
      $("topic-filter").focus();
    });
    $("topics").append(card);
  });
  const tags = [
    ...new Set([
      ...user.topics.map((t) => t.topic),
      ...user.recommendations.flatMap((p) => p.tags),
    ]),
  ].sort();
  $("topic-filter").replaceChildren(
    new Option("All topics", ""),
    ...tags.map((t) => new Option(t, t)),
  );
  resetFilters();
}
function resetFilters() {
  $("topic-filter").value = "";
  $("min-rating").value = current.difficulty_range[0];
  $("max-rating").value = current.difficulty_range[1];
  visible = 6;
  renderProblems();
}
function renderProblems() {
  const lower = Number($("min-rating").value),
    upper = Number($("max-rating").value),
    topic = $("topic-filter").value;
  $("range-note").textContent =
    `This saved example contains candidates rated ${current.difficulty_range[0]}–${current.difficulty_range[1]}. Filters narrow that window; they do not fetch new data.`;
  $("problems").replaceChildren();
  $("show-more").hidden = true;
  if (!$("min-rating").value || !$("max-rating").value || lower > upper || lower < 800) {
    $("filter-error").textContent =
      "Enter a minimum of at least 800 and a maximum at least as large as the minimum.";
    $("candidate-count").textContent = "Invalid difficulty range";
    return;
  }
  $("filter-error").textContent = "";
  const matches = current.recommendations.filter(
    (p) => p.rating >= lower && p.rating <= upper && (!topic || p.tags.includes(topic)),
  );
  $("candidate-count").textContent =
    `${matches.length} matching problems · showing ${Math.min(visible, matches.length)}`;
  if (!matches.length)
    $("problems").append(
      node(
        "p",
        "No saved candidates match these filters. Try another topic or reset the difficulty range.",
        "notice",
      ),
    );
  matches.slice(0, visible).forEach((p) => {
    const card = node("article", undefined, "problem"),
      meta = node("div", undefined, "meta");
    meta.append(node("span", `${p.problem_id} · Rating ${p.rating}`), node("span", p.kind));
    card.append(
      meta,
      node("h4", p.name),
      node("p", p.tags.join(" · ")),
      node(
        "p",
        p.predicted_acceptance === null
          ? "Probability withheld: insufficient evidence."
          : `${percent(p.predicted_acceptance)} estimated first-attempt acceptance · not a guarantee`,
      ),
      node("p", p.reason),
    );
    const link = node("a", "Open problem on Codeforces →");
    link.href = p.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    card.append(link);
    $("problems").append(card);
  });
  $("show-more").hidden = visible >= matches.length;
}
function renderResults() {
  const split = $("test-select").value,
    level = $("weight-select").value,
    result = data.tests[split],
    base = result.results[0],
    u = result.selected_uncertainty;
  $("test-summary").textContent =
    `${base.rows.toLocaleString()} rows · ${base.users} users · ${result.accepted.toLocaleString()} accepted · ${result.rejected.toLocaleString()} rejected. ${level === "user_average" ? "Each user contributes equally; ROC-AUC includes " + base.users_with_auc + " users." : "Each submission contributes equally; prolific users have more influence."}`;
  $("metrics").replaceChildren();
  result.results.forEach((r) => {
    const tr = node("tr");
    if (r.name === data.selected) tr.className = "selected";
    tr.append(node("td", r.name + (r.name === data.selected ? " · preselected" : "")));
    ["log_loss", "brier", "roc_auc", "precision", "recall", "f1"].forEach((k) =>
      tr.append(node("td", r[level][k] === null ? "N/A" : r[level][k].toFixed(4))),
    );
    $("metrics").append(tr);
  });
  $("uncertainty").textContent =
    `Selected-model user-averaged log loss: 95% interval ${u.log_loss_95_percent.map((v) => v.toFixed(4)).join(" to ")}. Paired model-minus-baseline difference: ${u.paired_difference.toFixed(4)}, interval ${u.paired_difference_95_percent.map((v) => v.toFixed(4)).join(" to ")}. ${u.paired_difference_95_percent[1] >= 0 ? "This interval includes no improvement." : "This interval favors the model within this cohort."} Based on 2,000 paired user-bootstrap resamples; recruitment bias and shared-problem dependence are not covered.`;
}
async function start() {
  try {
    const response = await fetch("data.json");
    if (!response.ok) throw Error("Unable to load data");
    data = await response.json();
    $("handles").replaceChildren(...data.examples.map((u) => new Option(u.handle, u.handle)));
    $("user-form").addEventListener("submit", (e) => {
      e.preventDefault();
      chooseUser($("handle").value);
    });
    $("filters").addEventListener("submit", (e) => e.preventDefault());
    ["topic-filter", "min-rating", "max-rating"].forEach((id) =>
      $(id).addEventListener("input", () => {
        visible = 6;
        renderProblems();
      }),
    );
    $("reset").addEventListener("click", resetFilters);
    $("show-more").addEventListener("click", () => {
      visible += 6;
      renderProblems();
    });
    ["test-select", "weight-select"].forEach((id) =>
      $(id).addEventListener("change", renderResults),
    );
    data.errors.forEach((e) => {
      const tr = node("tr");
      [
        e.analysis_id,
        e.problem_id,
        e.problem_tags.join(", "),
        percent(e.probability),
        e.target ? "Accepted" : "Rejected",
      ].forEach((v) => tr.append(node("td", v)));
      $("errors").append(tr);
    });
    chooseUser(data.examples[0].handle);
    renderResults();
    $("explorer").hidden = false;
    $("load-status").hidden = true;
  } catch (error) {
    $("load-status").textContent =
      "Saved examples could not be loaded. Reload the page, or use the repository reports below. For local preview, serve the website folder with an HTTP server.";
  }
}
start();
