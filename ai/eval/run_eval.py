"""Run the evaluation set and write ai/eval/report.md.

Usage:  python -m ai.eval.run_eval
Uses a temporary, freshly seeded database so the real demo DB is never touched.
Mode follows AI_MODE / ANTHROPIC_API_KEY (offline when no key is set).
"""
import json
import os
import statistics
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="hospital-eval-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/eval.db".replace("\\", "/")

from ai.config import ai_mode  # noqa: E402
from ai.orchestrator import answer_query  # noqa: E402
from backend.app.chat_ctx import ctx_for  # noqa: E402
from backend.app.seed import seed  # noqa: E402
from backend.app.tools.registry import execute_tool  # noqa: E402

HERE = Path(__file__).parent
TARGETS = {"intent": 0.90, "facts": 0.90, "citation": 0.95, "not_found": 1.0}


def main():
    cases = [json.loads(line) for line in (HERE / "eval_set.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    rows, latencies = [], []
    for c in cases:
        seed(reset=True)  # every case starts from the same state
        r = answer_query(c["q"], ctx_for(c["user"]), [], execute_tool)
        latencies.append(r["latency_ms"])
        refs = [str(x["ref"]) for x in r["citations"]]
        if c["status"] == "not_found":
            row = {"intent_ok": r["intent"] == c["intent"] or r["intent"] == "out_of_scope",
                   "facts_ok": None, "cite_ok": None, "nf_ok": r["status"] == "not_found"}
        else:
            facts = all(s.lower() in r["answer"].lower() for s in c.get("must_contain", []))
            if "expect_action" in c:
                facts = facts and (r["action_required"] is not None) == c["expect_action"]
            row = {"intent_ok": r["intent"] == c["intent"], "facts_ok": facts and r["status"] == "ok",
                   "cite_ok": any(ref.startswith(c["must_cite"]) for ref in refs), "nf_ok": None}
        row.update({"q": c["q"], "user": c["user"], "intent": r["intent"], "status": r["status"],
                    "latency": r["latency_ms"], "mode": r["mode"]})
        rows.append(row)

    def rate(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return sum(vals) / len(vals), len(vals)

    metrics = {"intent": rate("intent_ok"), "facts": rate("facts_ok"), "citation": rate("cite_ok"),
               "not_found": rate("nf_ok")}
    median = statistics.median(latencies)

    by_mode ={m: sum(r["mode"] == m for r in rows) for m in sorted({r["mode"] for r in rows})}
    fallback_note = ""
    if ai_mode() != "offline" and by_mode.get("offline"):
        fallback_note = (f"\n**Warning:** {by_mode['offline']} case(s) fell back to the offline pipeline (API error or "
                         f"rate limit), so these scores are not purely {ai_mode()}.\n")
    lines = [f"# Evaluation report\n", f"Mode: **{ai_mode()}** - {len(cases)} cases - answered by: "
             + ", ".join(f"{m} {n}" for m, n in by_mode.items()) + "\n" + fallback_note,
             "| Metric | Result | Target | |", "|---|---|---|---|"]
    names = {"intent": "Intent accuracy", "facts": "Answer contains expected facts",
             "citation": "Correct citation present", "not_found": "Not-found precision"}
    for k, (v, n) in metrics.items():
        lines.append(f"| {names[k]} | {v:.0%} ({n} cases) | {TARGETS[k]:.0%} | {'PASS' if v >= TARGETS[k] else 'FAIL'} |")
    lines.append(f"| Median latency | {median:.0f} ms | < 6000 ms | {'PASS' if median < 6000 else 'FAIL'} |")
    lines += ["", "## Cases", "",
              "| # | User | Question | Mode | Intent | Status | Intent ok | Facts ok | Cited | Not-found ok |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    mark = {True: "yes", False: "**NO**", None: "-"}
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['user']} | {r['q']} | {r['mode']} | {r['intent']} | {r['status']} | "
                     f"{mark[r['intent_ok']]} | {mark[r['facts_ok']]} | {mark[r['cite_ok']]} | {mark[r['nf_ok']]} |")
    (HERE / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:lines.index("## Cases")]))
    failures = [r for r in rows if False in (r["intent_ok"], r["facts_ok"], r["cite_ok"], r["nf_ok"])]
    for r in failures:
        print("FAILED:", r["user"], "|", r["q"], "|", r["intent"], r["status"])


if __name__ == "__main__":
    main()
