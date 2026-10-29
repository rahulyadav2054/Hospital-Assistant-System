import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { formatWhen } from "../utils/format.js";
import { AgentList } from "./AgentHub.jsx";

export default function Sidebar({ user, refreshKey, open, onAsk, busy }) {
  const [appts, setAppts] = useState([]);
  const [tests, setTests] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user.role !== "patient") return;
    Promise.all([api("/me/appointments"), api("/me/pending-tests")])
      .then(([a, t]) => { setAppts(a); setTests(t); setError(""); })
      .catch((e) => setError(e.message));
  }, [user, refreshKey]);

  return (
    <aside className={`${open ? "block" : "hidden"} md:block w-full md:w-72 shrink-0 border-r border-slate-200 bg-white p-4 overflow-y-auto`}
      aria-label="My summary">
      {user.role !== "patient" ? (
        <div className="text-sm text-slate-600">
          <h2 className="font-semibold text-slate-800 mb-1">Staff view</h2>
          You can look up hospital policies, departments and free appointment slots. Patient lab results are not
          available to front-desk staff.
        </div>
      ) : (
        <>
          {error && <p className="text-sm text-red-700 mb-2">{error}</p>}
          <h2 className="text-xs font-semibold tracking-wider text-slate-500 uppercase mb-2">Upcoming</h2>
          <ul className="space-y-2 mb-6" data-testid="sidebar-appointments">
            {appts.length === 0 && <li className="text-sm text-slate-500">No upcoming appointments</li>}
            {appts.map((a) => (
              <li key={a.appointment_id} data-testid={`appt-${a.appointment_id}`} className="text-sm">
                <div className="font-medium">{a.department}</div>
                <div className="text-xs text-slate-500">{formatWhen(a.start)} · {a.doctor}</div>
              </li>
            ))}
          </ul>
          <h2 className="text-xs font-semibold tracking-wider text-violet-700 uppercase mb-1">🤖 Your AI agents</h2>
          <div className="mb-6"><AgentList username={user.username} onAsk={onAsk} disabled={busy} /></div>
          <h2 className="text-xs font-semibold tracking-wider text-slate-500 uppercase mb-2">Pending tests</h2>
          <ul className="space-y-1.5" data-testid="sidebar-tests">
            {tests.length === 0 && <li className="text-sm text-slate-500">None</li>}
            {tests.map((t) => (
              <li key={t.order_id} className="text-sm" data-testid={`test-${t.order_id}`}>
                {t.scheduled_at ? "📅" : "⏳"} {t.description}
                {t.scheduled_at && (
                  <div className="text-xs text-emerald-700 pl-5">Booked {formatWhen(t.scheduled_at)}</div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  );
}
