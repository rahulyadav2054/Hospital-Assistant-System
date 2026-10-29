import { formatDate, formatINR, formatWhen } from "../utils/format.js";

const FLAG_STYLE = {
  high: "bg-red-50 text-red-700 border-red-200",
  low: "bg-amber-50 text-amber-800 border-amber-200",
  normal: "bg-emerald-50 text-emerald-700 border-emerald-200",
};
const FLAG_LABEL = { high: "▲ HIGH", low: "▼ LOW", normal: "NORMAL" };

function Card({ title, children, testId }) {
  return (
    <div className="border border-slate-200 rounded-lg bg-white p-3 mt-3" data-testid={testId}>
      <div className="text-[0.7rem] font-semibold tracking-wider text-slate-500 uppercase mb-1">{title}</div>
      {children}
    </div>
  );
}

/** Value, unit, reference range and flag - deliberately no interpretation text. */
export function LabResultCard({ data }) {
  return (
    <Card title="Lab result" testId="lab-card">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-medium">{data.test}</span>
        <span className="text-lg font-semibold">{data.value} <span className="text-sm font-normal">{data.unit}</span></span>
        <span className={`text-xs border rounded px-1.5 py-0.5 ${FLAG_STYLE[data.flag] ?? ""}`}>{FLAG_LABEL[data.flag] ?? data.flag}</span>
      </div>
      <div className="text-xs text-slate-500 mt-1">Ref {data.ref_range} {data.unit} · Collected {formatDate(data.date)}</div>
    </Card>
  );
}

export function AppointmentsCard({ data }) {
  return (
    <Card title="Appointments" testId="appointments-card">
      <ul className="divide-y divide-slate-100">
        {data.items.map((a) => (
          <li key={a.appointment_id} className="py-1.5 text-sm">
            <span className="font-medium">{a.department}</span> · {a.doctor}
            <div className="text-xs text-slate-500">{formatWhen(a.start)}{a.location ? ` · ${a.location}` : ""}</div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function CoverageCard({ data }) {
  return (
    <Card title="Coverage check" testId="coverage-card">
      <div className="flex items-center gap-2">
        <span className={`text-sm font-semibold border rounded px-2 py-0.5 ${data.covered
          ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-red-50 text-red-700 border-red-200"}`}>
          {data.covered ? "COVERED" : "NOT COVERED"}
        </span>
        <span className="font-medium">{data.procedure}</span>
        <span className="text-xs text-slate-500">({data.procedure_code})</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm mt-2">
        <dt className="text-slate-500">Plan</dt><dd>{data.plan}</dd>
        {data.covered && <><dt className="text-slate-500">Coverage</dt><dd>{data.coverage_pct}%</dd></>}
        {data.covered && <><dt className="text-slate-500">Prior authorization</dt><dd>{data.prior_auth_required ? "Required" : "Not required"}</dd></>}
        {data.est_patient_cost != null && <><dt className="text-slate-500">Est. your cost</dt><dd>{formatINR(data.est_patient_cost)}</dd></>}
      </dl>
      <ul className="list-disc pl-5 text-sm mt-2 text-slate-700">
        {data.reasons.map((r) => <li key={r}>{r}</li>)}
      </ul>
      <div className="text-xs text-slate-500 mt-2">Rule {data.rule_id ?? "—"} · Plan document {data.plan_doc_ref}</div>
    </Card>
  );
}

export function PendingTestsCard({ data }) {
  return (
    <Card title={`Pre-operative tests${data.procedure ? ` · ${data.procedure}` : ""}`} testId="pending-tests-card">
      <ul className="text-sm space-y-1">
        {data.items.map((t) => (
          <li key={t.name} className="flex items-center gap-2">
            <span aria-hidden="true">{t.status === "completed" ? "✅" : "⏳"}</span>
            <span className={t.status === "completed" ? "text-slate-500" : "font-medium"}>{t.name}</span>
            <span className="text-xs text-slate-500">
              {t.status === "completed" ? `done ${formatDate(t.completed_date)}` : "pending"}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function DepartmentCard({ data }) {
  return (
    <Card title="Department" testId="department-card">
      {data.items.map((d) => (
        <div key={d.department} className="text-sm py-1">
          <span className="font-medium">{d.department}</span>
          <div className="text-xs text-slate-500">{d.location} · {d.phone} · {d.hours}</div>
        </div>
      ))}
    </Card>
  );
}

/** Visit Planner: the day as a vertical timeline. */
export function VisitTimelineCard({ data }) {
  return (
    <Card title={`Your visit · ${formatDate(data.date)}`} testId="visit-timeline">
      <ol className="relative border-l-2 border-violet-200 ml-2 mt-1 space-y-3">
        {data.items.map((it, i) => (
          <li key={i} className="ml-4">
            <span className="absolute -left-[7px] mt-1.5 w-3 h-3 rounded-full bg-violet-500 border-2 border-white" aria-hidden="true" />
            <div className="text-sm"><span className="font-semibold">{it.time}</span> · {it.kind === "test" ? "🧪" : "🩺"} {it.title}</div>
            {it.location && <div className="text-xs text-slate-500">📍 {it.location}</div>}
          </li>
        ))}
      </ol>
    </Card>
  );
}

/** Proactive Care Agent: what needs attention, each with a one-click next step. */
export function NotificationsCard({ data, onAsk }) {
  const icon = { warning: "⚠️", action: "👉", info: "ℹ️" };
  if (!data.items.length) return <Card title="Needs attention"><p className="text-sm">Nothing right now. ✅</p></Card>;
  return (
    <Card title="Needs attention" testId="notifications-card">
      <ul className="space-y-2">
        {data.items.map((n) => (
          <li key={n.id} className="text-sm flex flex-wrap items-start gap-2">
            <span aria-hidden="true">{icon[n.level] ?? "ℹ️"}</span>
            <span className="flex-1 min-w-[12rem]"><span className="font-medium">{n.title}:</span> {n.text.replace(/\s*\[S\d+\]/g, "")}</span>
            {n.action_prompt && onAsk && (
              <button type="button" onClick={() => onAsk(n.action_prompt)}
                className="text-xs font-medium bg-violet-600 hover:bg-violet-700 text-white rounded-md px-2.5 py-1">
                {n.action_label} →
              </button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export const CARD_MAP = {
  lab_result: LabResultCard,
  appointments: AppointmentsCard,
  coverage: CoverageCard,
  pending_tests: PendingTestsCard,
  department: DepartmentCard,
  visit_timeline: VisitTimelineCard,
  notifications: NotificationsCard,
};
