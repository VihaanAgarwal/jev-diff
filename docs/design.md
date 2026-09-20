# Reviewing decisions

The person opening this file is checking a model, question, or policy change before shipping it. They need to find affected decisions, understand the evidence, and take the result back to their code. The report should feel like a precise code review: quiet, readable, and immediate.

The domain is baselines, candidates, confidence gates, typed answer spaces, state identity, and probability mass. The palette comes from a printed diff: paper, ink, gray annotations, blue candidate values, and amber review marks. Color indicates which run a value belongs to or where a change needs attention. Amber does not mean the candidate is wrong.

The signature is a pair of value tracks with each run's threshold drawn in place. That relationship also appears in the paired answers, distribution bars, numeric columns, raw definitions, and model metadata. Reading across should always mean baseline to candidate.

Three common dashboard patterns do not fit this job. A global sidebar would imply a larger application, so the left column is the actual case list. Metric cards would compete with the evidence, so counts sit on a single line. A verdict or health score would overstate what the data proves, so the report names concrete changes and skips comparisons when the answer spaces differ.

## Interface rules

- Use a 4px spacing unit, quiet borders, and surface fills. No shadows or decorative motion.
- Use system sans for explanations and system monospace for case IDs, labels, and values. All fonts stay local.
- Keep candidate values blue and baseline values gray in either color scheme. Mark thresholds in amber, with explicit numeric comparisons so color is never the only cue.
- Start with changed cases and prioritize gate crossings. Preserve every case through the All cases filter. Show the selected case's changed questions first and collapse unflagged questions when possible.
- Keep the case list visible while reading. Render it in batches of 100 to avoid creating thousands of links at once. Search still covers all case and question IDs.
- Make numeric gate comparisons exact in text. Probability percentages may be rounded for display; the original response is available in the evidence disclosure.
- On narrow screens, selecting a case moves focus to its evidence. All controls have accessible labels and visible keyboard focus.
- A report is immutable. It does not modify policies, upload traces, call a provider, or run application actions. JSON export is the comparison only; the HTML contains the evidence too.
- Embed data as JSON with HTML delimiters escaped. Construct dynamic content through text nodes. A content security policy permits only the bundled script and blocks network requests.

The generated example is deliberately labeled synthetic. It demonstrates the workflow and is not evidence of Jev accuracy, latency, or stability.
