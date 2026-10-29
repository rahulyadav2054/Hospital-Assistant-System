import { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";

const LEVEL = {
  warning: ["⚠️", "border-amber-300 bg-amber-50"],
  action: ["👉", "border-violet-300 bg-violet-50"],
  info: ["ℹ️", "border-slate-200 bg-white"],
};

/**
 * The Proactive Care Agent's inbox. It runs automatically at login and after every change, without being asked.
 * Each notification has a one-click action that starts the right agent.
 */
export default function NotificationBell({ refreshKey, onAsk, onFirstLoad }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const announced = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api("/me/notifications")
      .then((n) => {
        if (cancelled) return;
        setItems(n);
        if (!announced.current) {
          announced.current = true;
          onFirstLoad?.(n);
        }
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} data-testid="bell"
        className="relative text-sm bg-white/10 hover:bg-white/20 rounded px-3 py-1" aria-label={`Notifications (${items.length})`}>
        🔔
        {items.length > 0 && (
          <span className="absolute -top-1.5 -right-1.5 bg-red-500 text-white text-[0.65rem] font-bold rounded-full min-w-[1.1rem] h-[1.1rem] px-1 flex items-center justify-center" data-testid="bell-count">
            {items.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-[min(24rem,calc(100vw-2rem))] max-h-[70vh] overflow-y-auto bg-white text-slate-800 rounded-xl shadow-2xl border border-slate-200 z-40" data-testid="bell-panel">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
            <span aria-hidden="true">🔔</span>
            <div>
              <div className="font-semibold text-sm">Proactive Care Agent</div>
              <div className="text-xs text-slate-500">Checked your record automatically {loading ? "…" : "just now"}</div>
            </div>
            <button type="button" className="ml-auto text-slate-400 hover:text-slate-700" onClick={() => setOpen(false)} aria-label="Close">×</button>
          </div>
          {items.length === 0 && <p className="p-4 text-sm text-slate-500">Nothing needs your attention right now. ✅</p>}
          <ul className="p-2 space-y-2">
            {items.map((n) => {
              const [icon, cls] = LEVEL[n.level] ?? LEVEL.info;
              return (
                <li key={n.id} className={`border rounded-lg p-3 text-sm ${cls}`}>
                  <div className="font-medium">{icon} {n.title}</div>
                  <p className="text-slate-700 mt-0.5">{n.text}</p>
                  {n.action_prompt && (
                    <button type="button" onClick={() => { setOpen(false); onAsk(n.action_prompt); }}
                      className="mt-2 text-xs font-medium bg-violet-600 hover:bg-violet-700 text-white rounded-md px-3 py-1">
                      {n.action_label} →
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
