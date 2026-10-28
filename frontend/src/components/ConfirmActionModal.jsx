import { useEffect, useState } from "react";
import { api } from "../api/client.js";

function secondsLeft(expiresAt) {
  return Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000));
}

/** Two-phase commit, step 2: nothing changes until the patient presses Confirm. */
export default function ConfirmActionModal({ action, onDone, onClose }) {
  const [left, setLeft] = useState(() => secondsLeft(action.expires_at));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setLeft(secondsLeft(action.expires_at)), 1000);
    return () => clearInterval(t);
  }, [action.expires_at]);

  async function confirm() {
    setBusy(true);
    try {
      const res = await api("/actions/confirm", { method: "POST", body: { pending_action_id: action.pending_action_id } });
      onDone({ ok: true, message: res.message });
    } catch (e) {
      const msg = {
        409: "That slot was just taken or can no longer be changed. Please ask again to see other slots.",
        410: "This confirmation expired. Please ask again.",
        404: "This request is no longer valid. Please ask again.",
      }[e.status] ?? e.message;
      onDone({ ok: false, message: msg });
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    try {
      await api("/actions/cancel", { method: "POST", body: { pending_action_id: action.pending_action_id } });
    } catch { /* already gone - nothing to undo */ }
    setBusy(false);
    onClose();
  }

  const mm = String(Math.floor(left / 60)).padStart(2, "0");
  const ss = String(left % 60).padStart(2, "0");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40">
      <div role="dialog" aria-modal="true" aria-labelledby="confirm-title"
        className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <h2 id="confirm-title" className="text-lg font-semibold text-brand-900">Confirm reschedule</h2>
        <p className="mt-3 text-slate-700">{action.summary}?</p>
        <p className="mt-2 text-xs text-slate-500">
          {left > 0 ? `This request expires in ${mm}:${ss}. ` : ""}Nothing changes until you confirm.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={cancel} disabled={busy}
            className="px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-50">Cancel</button>
          {/* Not disabled by the browser's clock (it can differ from the server's): the server decides,
              and answers 410 if the request really expired. */}
          <button type="button" onClick={confirm} disabled={busy}
            className="px-4 py-2 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-medium disabled:opacity-60">
            {busy ? "Saving…" : "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}
