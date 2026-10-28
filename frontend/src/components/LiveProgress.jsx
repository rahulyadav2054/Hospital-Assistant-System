/** Live view while an answer is being prepared: each tool call appears as it starts and gets ticked off. */
export default function LiveProgress({ live }) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm" data-testid="live-progress"
      aria-live="polite">
      <ul className="space-y-1 text-sm">
        {live.tools.map((t) => (
          <li key={t.seq} className="flex items-center gap-2 reveal">
            <StatusIcon status={t.status} />
            <span className={t.status === "running" ? "text-slate-800" : "text-slate-500"}>{t.label}</span>
          </li>
        ))}
        <li className="flex items-center gap-2 text-slate-500">
          <Spinner />
          <span>{live.status || (live.tools.length ? "Working…" : "Thinking…")}</span>
        </li>
      </ul>
    </div>
  );
}

export function Spinner() {
  return <span className="inline-block w-3.5 h-3.5 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" aria-hidden="true" />;
}

export function StatusIcon({ status }) {
  if (status === "running") return <Spinner />;
  const map = { done: ["✓", "text-emerald-600"], failed: ["!", "text-amber-600"], warning: ["!", "text-amber-600"],
    stopped: ["■", "text-slate-500"] };
  const [icon, cls] = map[status] ?? ["•", "text-slate-400"];
  return <span className={`w-3.5 text-center font-bold ${cls}`} aria-label={status}>{icon}</span>;
}
