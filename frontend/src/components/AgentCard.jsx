import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { AGENT_BY_NAME } from "../agents.js";
import { CARD_MAP } from "./Cards.jsx";
import CitationChips from "./CitationChips.jsx";
import { StatusIcon } from "./LiveProgress.jsx";
import MessageBubble from "./MessageBubble.jsx";

const STEP_STYLE = {
  running: "border-violet-400 bg-violet-50 shadow-sm",
  done: "border-emerald-200 bg-white",
  warning: "border-amber-200 bg-amber-50/40",
  stopped: "border-slate-300 bg-slate-50",
};

// "warning" is not an error: the step found something the patient needs to act on.
const STEP_BADGE = {
  warning: ["Needs attention", "bg-amber-100 text-amber-800"],
  stopped: ["Stopped", "bg-slate-200 text-slate-700"],
};

const PHASES = ["Planning", "Using tools", "Verifying", "Done"];

function phaseOf({ live, steps, status }) {
  if (!live) return 3;
  if (/verif/i.test(status || "")) return 2;
  return steps.length ? 1 : 0;
}

/** The agent's steps as a vertical timeline. Used live (unverified) and for the final, verified answer. */
export function AgentSteps({ steps, onCite }) {
  return (
    <ol className="relative space-y-2 before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-0.5 before:bg-violet-100" data-testid="agent-steps">
      {steps.map((s) => (
        <li key={s.index} className={`relative ml-7 border rounded-lg px-3 py-2 reveal ${STEP_STYLE[s.status] ?? "bg-white"}`}
          data-testid={`agent-step-${s.index}`} data-status={s.status}>
          <span className="absolute -left-7 top-2 w-6 h-6 rounded-full bg-white border-2 border-violet-300 text-[0.7rem] font-bold text-violet-700 flex items-center justify-center">
            {s.index}
          </span>
          <div className="flex items-center gap-2 text-sm font-medium">
            <StatusIcon status={s.status} />
            <span>{s.title}</span>
            {STEP_BADGE[s.status] && (
              <span className={`ml-auto text-xs font-normal rounded-full px-2 py-0.5 ${STEP_BADGE[s.status][1]}`}>
                {STEP_BADGE[s.status][0]}
              </span>
            )}
          </div>
          {s.details?.length > 0 && (
            <div className="mt-1 pl-6 text-sm text-slate-700">
              <MessageBubble text={s.details.map((d) => `- ${d}`).join("\n")} onCite={onCite ?? (() => {})} />
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

/** One approval for the whole plan; the patient can untick items. Nothing happens until they press Approve. */
export function PlanApproval({ action, onDone }) {
  const [checked, setChecked] = useState(() => action.items.map(() => true));
  const [state, setState] = useState({ busy: false, result: null, error: "" });
  const selected = action.items.filter((_, i) => checked[i]).map((x) => x.index);

  async function approve() {
    setState({ busy: true, result: null, error: "" });
    try {
      const res = await api("/actions/confirm", {
        method: "POST", body: { pending_action_id: action.pending_action_id, selected },
      });
      setState({ busy: false, result: res, error: "" });
      onDone({ ok: true, message: res.message });
    } catch (e) {
      const msg = { 409: e.message, 410: "This plan expired. Please ask again.", 404: "This plan is no longer valid. Please ask again." }[e.status] ?? e.message;
      setState({ busy: false, result: null, error: msg });
      onDone({ ok: false, message: msg });
    }
  }

  async function cancel() {
    setState({ busy: true, result: null, error: "" });
    try {
      await api("/actions/cancel", { method: "POST", body: { pending_action_id: action.pending_action_id } });
    } catch { /* already gone */ }
    setState({ busy: false, result: { cancelled: true }, error: "" });
    onDone({ ok: false, message: "Plan cancelled. Nothing was booked or submitted." });
  }

  if (state.result?.cancelled) return <p className="text-sm text-slate-500 mt-3">Plan cancelled - nothing was changed.</p>;
  if (state.result) {
    return (
      <div className="mt-3 border border-emerald-200 bg-emerald-50 rounded-lg p-3 text-sm" data-testid="plan-done">
        <div className="font-semibold text-emerald-800 mb-1">✅ Approved - the agent completed it</div>
        <ul className="space-y-1">{state.result.results.map((r) => <li key={r.index}>✔ {r.message}</li>)}</ul>
      </div>
    );
  }
  return (
    <div className="mt-3 border-2 border-violet-500 rounded-lg p-3 bg-white" data-testid="plan-approval">
      <div className="flex items-center gap-2">
        <span aria-hidden="true">🛡️</span>
        <span className="font-semibold text-brand-900">{action.items.length === 1 ? "Proposed booking" : "Proposed plan"}</span>
        <span className="ml-auto text-[0.65rem] font-semibold text-violet-700 bg-violet-100 rounded-full px-2 py-0.5">NEEDS YOUR APPROVAL</span>
      </div>
      <p className="text-xs text-slate-500 mb-2 mt-1">The agent prepared this but has not changed anything. Untick anything you don't want.</p>
      <ul className="space-y-2">
        {action.items.map((it, i) => (
          <li key={it.index}>
            <label className="flex items-start gap-2 text-sm cursor-pointer">
              <input type="checkbox" className="mt-1" checked={checked[i]} disabled={state.busy}
                onChange={() => setChecked((c) => c.map((v, j) => (j === i ? !v : v)))} />
              <span><span className="font-medium">{it.label}</span><span className="block text-xs text-slate-500">{it.detail}</span></span>
            </label>
          </li>
        ))}
      </ul>
      {state.error && <p className="text-sm text-red-700 mt-2" role="alert">{state.error}</p>}
      <div className="flex gap-2 mt-3">
        <button type="button" onClick={approve} disabled={state.busy || selected.length === 0}
          className="bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium rounded-lg px-4 py-2 disabled:opacity-50">
          {state.busy ? "Saving…" : action.items.length === 1 ? "Approve booking"
            : selected.length === action.items.length ? "Approve all" : `Approve ${selected.length} selected`}
        </button>
        <button type="button" onClick={cancel} disabled={state.busy}
          className="border border-slate-300 hover:bg-slate-50 text-sm rounded-lg px-4 py-2">Cancel</button>
      </div>
    </div>
  );
}

function Elapsed({ since }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);
  return <span className="tabular-nums">{((now - since) / 1000).toFixed(1)}s</span>;
}

/** Live (while streaming) or final agent answer. */
export default function AgentCard({ name, title, icon, steps, live, status, startedAt, response, onOpenSource,
  onPlanDone, onAsk }) {
  const meta = AGENT_BY_NAME[name] ?? {};
  const onCite = response ? (id) => onOpenSource(response, id) : undefined;
  const phase = phaseOf({ live, steps, status });
  const done = steps.filter((s) => s.status !== "running").length;
  const pct = live ? Math.min(95, Math.round((done / (steps.length + 1)) * 100)) : 100;
  const tookMs = response?.latency_ms;

  return (
    <div className="bg-white border border-violet-200 rounded-2xl rounded-tl-sm shadow-sm overflow-hidden" data-testid="agent-card">
      <div className="bg-gradient-to-r from-violet-600 to-brand-700 text-white px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className={`text-xl ${live ? "animate-pulse" : ""}`} aria-hidden="true">{icon || meta.icon || "🤖"}</span>
          <div className="min-w-0">
            <div className="font-semibold leading-tight">{title}</div>
            <div className="text-[0.7rem] text-violet-100">
              {live ? <>Agent working · <Elapsed since={startedAt} /></> : `Agent finished · ${done} steps${tookMs ? ` · ${(tookMs / 1000).toFixed(1)}s` : ""}`}
            </div>
          </div>
          <span className="ml-auto text-[0.65rem] font-semibold bg-white/20 rounded-full px-2 py-0.5">AI AGENT</span>
        </div>
        <div className="flex gap-1 mt-2" aria-label="Agent phase">
          {PHASES.map((p, i) => (
            <span key={p} className={`text-[0.65rem] rounded-full px-2 py-0.5 ${i < phase ? "bg-white/30" : i === phase ? "bg-white text-violet-700 font-semibold" : "bg-white/10 text-violet-100"}`}>
              {i < phase ? "✓ " : ""}{p}
            </span>
          ))}
        </div>
        <div className="h-1 bg-white/20 rounded-full mt-2 overflow-hidden">
          <div className="h-full bg-white rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="px-4 py-3">
        {response?.agent?.summary && (
          <div className="mb-3 bg-violet-50 border border-violet-100 rounded-lg p-3">
            <div className="text-[0.7rem] font-semibold text-violet-700 uppercase mb-1">Summary</div>
            <MessageBubble text={response.agent.summary} onCite={onCite} animate />
          </div>
        )}
        <AgentSteps steps={steps} onCite={onCite} />
        {live && <p className="text-xs text-slate-500 mt-2 flex items-center gap-2"><span className="inline-block w-2 h-2 rounded-full bg-violet-500 animate-ping" />{status || "Planning the next step…"}</p>}
        {response?.cards?.map((c, i) => {
          const Card = CARD_MAP[c.type];
          return Card ? <Card key={i} data={c.data} onAsk={onAsk} /> : null;
        })}
        {response?.action_required?.type === "confirm_plan" && (
          <PlanApproval action={response.action_required} onDone={onPlanDone} />
        )}
        {response && <CitationChips citations={response.citations} onOpen={(id) => onOpenSource(response, id)} />}
        {response?.disclaimer && <p className="text-xs text-slate-500 mt-2">ⓘ {response.disclaimer}</p>}
      </div>
    </div>
  );
}
