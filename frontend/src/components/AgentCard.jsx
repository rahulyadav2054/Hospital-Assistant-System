import { useState } from "react";
import { api } from "../api/client.js";
import { CARD_MAP } from "./Cards.jsx";
import CitationChips from "./CitationChips.jsx";
import { StatusIcon } from "./LiveProgress.jsx";
import MessageBubble from "./MessageBubble.jsx";

const STEP_STYLE = {
  running: "border-brand-500 bg-brand-50",
  done: "border-emerald-200 bg-white",
  warning: "border-amber-200 bg-amber-50/40",
  stopped: "border-slate-300 bg-slate-50",
};

// "warning" is not an error: the step found something the patient needs to act on.
const STEP_BADGE = {
  warning: ["Needs attention", "bg-amber-100 text-amber-800"],
  stopped: ["Stopped", "bg-slate-200 text-slate-700"],
};

/** The agent's steps. Used live (details unverified, no citation links yet) and for the final answer. */
export function AgentSteps({ steps, onCite }) {
  return (
    <ol className="space-y-2" data-testid="agent-steps">
      {steps.map((s) => (
        <li key={s.index} className={`border rounded-lg px-3 py-2 reveal ${STEP_STYLE[s.status] ?? "bg-white"}`}
          data-testid={`agent-step-${s.index}`} data-status={s.status}>
          <div className="flex items-center gap-2 text-sm font-medium">
            <StatusIcon status={s.status} />
            <span className="text-slate-400">Step {s.index}</span>
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
        <div className="font-semibold text-emerald-800 mb-1">Plan approved</div>
        <ul className="space-y-1">{state.result.results.map((r) => <li key={r.index}>✅ {r.message}</li>)}</ul>
      </div>
    );
  }
  return (
    <div className="mt-3 border-2 border-brand-500 rounded-lg p-3" data-testid="plan-approval">
      <div className="font-semibold text-brand-900">{action.items.length === 1 ? "Proposed booking" : "Proposed plan"}</div>
      <p className="text-xs text-slate-500 mb-2">Nothing is booked or submitted until you approve. Untick anything you don't want.</p>
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
          className="bg-brand-700 hover:bg-brand-600 text-white text-sm font-medium rounded-lg px-4 py-2 disabled:opacity-50">
          {state.busy ? "Saving…" : action.items.length === 1 ? "Approve booking"
            : selected.length === action.items.length ? "Approve all" : `Approve ${selected.length} selected`}
        </button>
        <button type="button" onClick={cancel} disabled={state.busy}
          className="border border-slate-300 hover:bg-slate-50 text-sm rounded-lg px-4 py-2">Cancel</button>
      </div>
    </div>
  );
}

/** Live (while streaming) or final agent answer. */
export default function AgentCard({ title, steps, live, status, response, onOpenSource, onPlanDone }) {
  const onCite = response ? (id) => onOpenSource(response, id) : undefined;
  return (
    <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm" data-testid="agent-card">
      <div className="flex items-center gap-2 mb-2">
        <span aria-hidden="true">🤖</span>
        <span className="font-semibold text-brand-900">{title}</span>
        {live && <span className="text-xs text-brand-600 animate-pulse">working…</span>}
      </div>
      {response?.agent?.summary && (
        <div className="mb-3"><MessageBubble text={response.agent.summary} onCite={onCite} animate /></div>
      )}
      <AgentSteps steps={steps} onCite={onCite} />
      {live && status && <p className="text-xs text-slate-500 mt-2">{status}</p>}
      {response?.cards?.map((c, i) => {
        const Card = CARD_MAP[c.type];
        return Card ? <Card key={i} data={c.data} /> : null;
      })}
      {response?.action_required?.type === "confirm_plan" && (
        <PlanApproval action={response.action_required} onDone={onPlanDone} />
      )}
      {response && <CitationChips citations={response.citations} onOpen={(id) => onOpenSource(response, id)} />}
      {response?.disclaimer && <p className="text-xs text-slate-500 mt-2">ⓘ {response.disclaimer}</p>}
    </div>
  );
}
