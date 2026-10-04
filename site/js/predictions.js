/* Predictions page: what a match model said before each match, and what happened.
 *
 * The model and every number about it come from Part 3 (../football-data-science):
 * its scripts/export_predictions.py writes the JSON, scripts/export_site_data.py
 * here copies it into site/data/predictions/. As on every page, nothing is computed
 * in this file (CLAUDE.md §9) — the scores, intervals, calibration bins and draw
 * rates were all written by Part 3's evaluation, and each match's probabilities by
 * the model before that match. This file picks, sorts, formats and draws.
 */

import {
  $, el, svg, segmented, syncSegmented, loadJSON, showError, showTip, hideTip, scale,
  ticks, prettyDate, startPage, setAnswer, highlight, setGuide, figureLabel,
  figureLeader, withTerms, asPercent, signed,
} from "./common.js";

const LEAGUE_ORDER = ["PL", "PD", "BL1", "SA", "FL1"];
const OUTCOME_CLASS = { H: "ahead", D: "even", A: "behind" };
const OUTCOME_WORD = { H: "home win", D: "draw", A: "away win" };

const state = { period: "holdout", league: "PL" };
let PRED = null;
const cache = new Map();

async function rowsFor(period, league) {
  const file = period === "holdout" ? `predictions/holdout_${league}.json` : "predictions/prospective.json";
  if (!cache.has(file)) cache.set(file, await loadJSON(file));
  // The prospective file holds every league; picking one is a filter, not a sum.
  return cache.get(file).filter((row) => row.league === league);
}

/* --- the probability bar --------------------------------------------------- */

/** Three segments whose widths are the three probabilities: drawing, not maths. */
function probBar(probs, result = null) {
  const bar = el("span", "probbar");
  ["H", "D", "A"].forEach((outcome, i) => {
    const part = el("i", `${OUTCOME_CLASS[outcome]}${outcome === result ? " hit" : ""}`);
    part.style.setProperty("--w", `${(probs[i] * 100).toFixed(1)}%`);
    bar.append(part);
  });
  return bar;
}

function probText(probs) {
  return probs.map((p) => asPercent(p)).join(" · ");
}

/* --- the calibration chart -------------------------------------------------- */

/** Predicted against observed, per probability bin: on the diagonal is calibrated. */
function drawCalibration(calibration, minMatches = 20) {
  const width = 520;
  const height = 300;
  const pad = { top: 14, right: 16, bottom: 34, left: 42 };
  const node = svg("svg", {
    class: "chart-svg", viewBox: `0 0 ${width} ${height}`, role: "img",
    "aria-label": "Predicted probability against how often it happened, for each outcome",
  });
  const x = scale([0, 0.9], [pad.left, width - pad.right]);
  const y = scale([0, 0.9], [height - pad.bottom, pad.top]);

  for (const value of ticks(0, 0.9, 4)) {
    node.append(svg("line", { class: "axis-line", x1: pad.left, x2: width - pad.right, y1: y(value), y2: y(value) }));
    node.append(Object.assign(
      svg("text", { class: "axis-text", x: pad.left - 8, y: y(value) + 3, "text-anchor": "end" }),
      { textContent: `${asPercent(value)}%` },
    ));
    node.append(Object.assign(
      svg("text", { class: "axis-text", x: x(value), y: height - pad.bottom + 16, "text-anchor": "middle" }),
      { textContent: `${asPercent(value)}%` },
    ));
  }
  node.append(svg("line", { class: "cal-diagonal", x1: x(0), y1: y(0), x2: x(0.9), y2: y(0.9) }));
  node.append(Object.assign(
    svg("text", { class: "axis-text", x: width - pad.right, y: height - 4, "text-anchor": "end" }),
    { textContent: "model said →" },
  ));
  node.append(Object.assign(
    svg("text", { class: "axis-text", x: pad.left, y: pad.top - 4 }),
    { textContent: "↑ happened" },
  ));

  const draw = (rows, filled) => {
    for (const outcome of ["H", "D", "A"]) {
      // A bin with a handful of matches is noise; it is left out, not merged.
      const points = rows.filter((r) => r.outcome === outcome && r.matches >= minMatches);
      if (filled && points.length > 1) {
        node.append(svg("path", {
          class: `cal-line ${OUTCOME_CLASS[outcome]}`,
          d: points.map((p, i) => `${i ? "L" : "M"}${x(p.predicted).toFixed(1)},${y(p.observed).toFixed(1)}`).join(" "),
        }));
      }
      for (const p of points) {
        const mark = svg("circle", {
          class: `${filled ? "cal-dot" : "cal-ring"} ${OUTCOME_CLASS[outcome]}`,
          cx: x(p.predicted), cy: y(p.observed), r: filled ? 4.5 : 4,
        });
        mark.addEventListener("pointerenter", (event) => showTip(
          `${filled ? PRED.model.label : PRED.baseline.label} · ${OUTCOME_WORD[outcome]}`,
          [["Bin", p.bin], ["Said", `${asPercent(p.predicted)}%`], ["Happened", `${asPercent(p.observed)}%`], ["Matches", String(p.matches)]],
          event.clientX, event.clientY,
        ));
        mark.addEventListener("pointerleave", hideTip);
        node.append(mark);
      }
    }
  };
  draw(calibration[PRED.baseline.key], false);
  draw(calibration[PRED.model.key], true);
  $("calibration")?.replaceChildren(node);

  const foot = $("calibration-foot");
  if (foot) {
    foot.replaceChildren(withTerms(
      `Filled dots: ${PRED.model.label}. Rings: ${PRED.baseline.label}. ` +
      `On the 2025/26 [[holdout|hold-out]]; bins with fewer than ${minMatches} matches are left out. ` +
      "A dot above the line means the outcome happened more often than the model said.",
    ));
  }
}

/* --- the guide ---------------------------------------------------------------- */

function guideFigure() {
  const node = svg("svg", {
    class: "chart-svg", viewBox: "0 0 160 64", role: "img",
    "aria-label": "A labelled example of a forecast bar",
  });
  // 52% home, 26% draw, 22% away — drawn with the same classes as the real bars.
  const segments = [[10, 72, "ahead"], [82, 36, "even"], [118, 32, "behind"]];
  for (const [x0, w, cls] of segments) {
    node.append(svg("rect", { class: `cal-seg ${cls}`, x: x0, y: 26, width: w, height: 9 }));
  }
  node.append(svg("rect", { class: "cal-hit", x: 10, y: 24, width: 72, height: 13 }));
  node.append(figureLeader(46, 24, 46, 14), figureLabel(46, 10, "home win 52%", "middle"));
  node.append(figureLeader(100, 37, 100, 48), figureLabel(100, 57, "draw 26%", "middle"));
  node.append(figureLeader(134, 24, 140, 14), figureLabel(150, 10, "away 22%", "end"));
  return node;
}

function guideExamples(rows) {
  if (!rows.length) {
    return [
      { subject: "Before kick-off", text: "Every forecast on this page was made with only what was known before the match: earlier results and earlier xG, never the match's own." },
      { subject: "Frozen", text: "A [[prospective|prospective]] forecast comes from a model whose settings and parameters were fixed before the match was played." },
      { subject: "No odds", text: "Gold holds no betting odds, so the comparison is with league base rates and an [[elo|Elo rating]], never with the market." },
    ];
  }
  // Selected, never composed: sorted on what the export provides.
  const byConfidence = [...rows].sort((a, b) => b.model_on_result - a.model_on_result);
  const surest = byConfidence[0];
  const surprise = byConfidence[byConfidence.length - 1];
  const draws = [...rows].sort((a, b) => b.model[1] - a.model[1]);
  const drawCall = draws[0];
  const name = (r) => `${r.home} ${r.score} ${r.away}`;
  return [
    { subject: name(surest), text: `The surest the model was of what then happened: **${asPercent(surest.model_on_result)}%** on a ${OUTCOME_WORD[surest.result]}, on ${prettyDate(surest.date)}.` },
    { subject: name(surprise), text: `The biggest surprise: the model gave the ${OUTCOME_WORD[surprise.result]} only **${asPercent(surprise.model_on_result)}%**. Surprises are expected — a forecast of 10% should come true about one time in ten.` },
    { subject: name(drawCall), text: `Its strongest draw call, **${asPercent(drawCall.model[1])}%** — the result was a ${OUTCOME_WORD[drawCall.result]}. Even here a draw was less likely than not: draws are hard to call (see the [[calibration|calibration]] chart).` },
  ];
}

/* --- the answer ---------------------------------------------------------------- */

function sentence(parts) {
  const fragment = document.createDocumentFragment();
  for (const part of parts) {
    fragment.append(typeof part === "string" ? withTerms(part) : part);
  }
  return fragment;
}

function verdictWords(comparison) {
  if (comparison.verdict === "cannot be distinguished") {
    return "a difference its own uncertainty cannot tell from zero";
  }
  return comparison.verdict;
}

function answerHoldout() {
  const h = PRED.holdout;
  const m = h.scores[PRED.model.key];
  const b = h.scores[PRED.baseline.key];
  const c = h.comparison;
  setAnswer({
    kicker: `Predictions · ${h.season} hold-out · ${h.matches.toLocaleString("en-GB")} matches it never saw`,
    sentence: sentence([
      "Forecasting every match of ", h.season, " before kick-off, the model scored ",
      highlight(m.rps.toFixed(4), "ahead"), ` on the [[rps|ranked probability score]] against ${PRED.baseline.label}'s `,
      highlight(b.rps.toFixed(4), "even"), ` — ${verdictWords(c)}.`,
    ]),
    meaning: [
      `Each row is three probabilities — home win, draw, away win — given before the match by **${PRED.model.label}**, which predicts each side's goals from the [[xg]] of earlier matches. It was picked because it scored best on 2024/25, the [[validation|validation season]]; 2025/26 was then scored once, as a [[holdout|hold-out]].`,
      `Lower is better on the [[rps|RPS]]: league base rates ${h.scores.base_rates.rps.toFixed(4)}, ${PRED.baseline.label} ${b.rps.toFixed(4)}, this model ${m.rps.toFixed(4)}. Against ${PRED.baseline.label} the difference is ${signed(c.difference, 4)}, with a 95% interval from ${signed(c.low, 4)} to ${signed(c.high, 4)}${c.verdict === "cannot be distinguished" ? " — it crosses zero, so neither can be called better" : ""}.`,
      `The chart below checks [[calibration|calibration]]: whether outcomes the model called at 60% happened about 60% of the time, against ${PRED.baseline.label}'s record on the same matches. It gave draws ${asPercent(h.draws[PRED.model.key].mean_predicted_draw)}% on average, and ${asPercent(h.draws[PRED.model.key].actual_draw_rate)}% of matches were draws.`,
    ],
    caveat: `${PRED.no_market} A probability is what the model expected before the match, not a verdict on who deserved to win.`,
  });
}

function answerProspective() {
  const p = PRED.prospective;
  if (p.status === "scored") {
    const m = p.scores[PRED.model.key];
    const b = p.scores[PRED.baseline.key];
    setAnswer({
      kicker: `Predictions · since the freeze · ${p.matches} matches`,
      sentence: sentence([
        "On ", highlight(String(p.matches), "ahead"), " matches played after it was frozen, the model scored ",
        highlight(m.rps.toFixed(4), "ahead"), ` on the [[rps|ranked probability score]] against ${PRED.baseline.label}'s `,
        highlight(b.rps.toFixed(4), "even"), ".",
      ]),
      meaning: [
        `This is the [[prospective|prospective test]]: the model was frozen on ${prettyDate(p.frozen_at.slice(0, 10))}, and every match here was played afterwards — nobody, and nothing in the model, could have seen it.`,
        `Against ${PRED.baseline.label}: ${signed(p.comparison.difference, 4)}, 95% interval ${signed(p.comparison.low, 4)} to ${signed(p.comparison.high, 4)} — ${verdictWords(p.comparison)}.`,
      ],
      caveat: p.caveat,
    });
    return;
  }
  const frozen = p.status === "waiting";
  setAnswer({
    kicker: "Predictions · since the freeze",
    sentence: sentence(frozen
      ? ["The model was frozen on ", highlight(prettyDate(p.frozen_at.slice(0, 10)), "ahead"),
        " and is waiting for matches played after ", highlight(prettyDate(p.scores_matches_after), "even"), " to reach a newer snapshot."]
      : ["No model has been ", highlight("frozen", "even"), " yet, so there is nothing to score prospectively."]),
    meaning: [
      "The [[prospective|prospective test]] scores a model fixed at one moment on matches played after it — the one test no care in a train/test split could have fooled.",
      frozen
        ? `It was fitted on ${p.trained_on.matches.toLocaleString("en-GB")} matches up to ${prettyDate(p.trained_on.last_match)}. Its card records the commit and a hash of the model, so what is scored later is provably what was frozen.`
        : "Part 3 freezes a model with `python -m football_ml.freeze`; this view fills in once a newer snapshot has matches after the freeze.",
    ],
    caveat: "Until then, the hold-out view is the model's track record.",
  });
}

/* --- the table ------------------------------------------------------------------ */

function drawRows(rows) {
  const body = $("rows");
  if (!body) return;
  if (!rows.length) {
    const cell = el("td", "state", "No matches in this view yet.");
    cell.colSpan = 6;
    const row = el("tr");
    row.append(cell);
    body.replaceChildren(row);
    return;
  }
  body.replaceChildren(...rows.map((r) => {
    const tr = el("tr");
    const name = el("td", "name");
    name.append(el("span", "", `${r.home} – ${r.away}`));
    const probs = el("td", "prob-col");
    probs.append(probBar(r.model, r.result), el("span", "probtxt", probText(r.model)));
    const onResult = el("td", "strong");
    onResult.append(el("i", `tri ${OUTCOME_CLASS[r.result]}`), `${asPercent(r.model_on_result)}%`);
    tr.append(
      name,
      el("td", "c-optional muted", prettyDate(r.date)),
      el("td", "", r.score),
      probs,
      el("td", "c-optional muted", probText(r.baseline)),
      onResult,
    );
    tr.addEventListener("pointerenter", (event) => showTip(
      `${r.home} ${r.score} ${r.away}`,
      [
        ["Result", OUTCOME_WORD[r.result]],
        [PRED.model.label, `${probText(r.model)} %`],
        [PRED.baseline.label, `${probText(r.baseline)} %`],
      ],
      event.clientX, event.clientY,
    ));
    tr.addEventListener("pointerleave", hideTip);
    return tr;
  }));
  const title = $("rows-title");
  if (title) title.textContent = `Match by match · ${PRED.leagues[state.league]}`;
}

/* --- page ------------------------------------------------------------------------- */

async function render() {
  syncSegmented($("league"), state.league);
  syncSegmented($("period"), state.period);
  const rows = await rowsFor(state.period, state.league);
  if (state.period === "holdout") answerHoldout(); else answerProspective();
  setGuide({
    figure: guideFigure(),
    caption: "One forecast: the bar is split into the three outcomes in proportion to the model's probabilities, and the outlined part is what happened.",
    examples: guideExamples(rows),
  });
  drawCalibration(PRED.holdout.calibration);
  drawRows(rows);
}

async function main() {
  try {
    await startPage({ page: "predictions.html", mart: "Part 3 · reports/match_outcome.json", container: $("rows") });
  } catch {
    return; // startPage has already shown the error in the page
  }
  try {
    PRED = await loadJSON("predictions/meta.json");
  } catch (error) {
    // The site's own data is there but Part 3's is not: say which export is missing.
    error.message = `${error.message}. The predictions come from Part 3 — run its export, then this one: ` +
      "(cd ../football-data-science && uv run python scripts/export_predictions.py) && uv run python scripts/export_site_data.py";
    showError($("rows"), error);
    return;
  }

  const leagues = LEAGUE_ORDER.filter((code) => code in PRED.leagues);
  state.league = leagues[0];
  segmented($("league"), leagues.map((code) => [code, code]), state.league, (value) => {
    state.league = value;
    render().catch((error) => showError($("rows"), error));
  });
  segmented($("period"), [["holdout", `${PRED.holdout.season}`], ["prospective", "Since freeze"]], state.period, (value) => {
    state.period = value;
    render().catch((error) => showError($("rows"), error));
  });

  const foot = $("foot");
  if (foot) foot.append(el("span", "", PRED.citation));

  await render().catch((error) => showError($("rows"), error));
}

main();
