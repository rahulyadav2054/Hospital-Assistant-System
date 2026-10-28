import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { formatDate } from "../utils/format.js";

/** Side drawer showing the exact text behind a citation. */
export default function SourceDrawer({ citation, onClose }) {
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setDoc(null);
    setError("");
    if (citation?.source_type === "document") {
      api(`/sources/${encodeURIComponent(citation.ref)}`).then(setDoc).catch((e) => setError(e.message));
    }
  }, [citation]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!citation) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Source">
      <button type="button" className="absolute inset-0 bg-slate-900/30" onClick={onClose} aria-label="Close source" />
      <aside className="relative w-full max-w-md h-full bg-white shadow-xl p-6 overflow-y-auto">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold text-brand-500 uppercase tracking-wide">
              Source {citation.id} · {citation.source_type === "document" ? "Hospital document" : "Your hospital record"}
            </div>
            <h2 className="text-lg font-semibold text-brand-900 mt-1">{citation.title}</h2>
            {citation.section && <div className="text-sm text-slate-600">Section {citation.section}</div>}
          </div>
          <button type="button" onClick={onClose} className="text-slate-500 hover:text-slate-800 text-xl" aria-label="Close">×</button>
        </div>

        {citation.source_type === "document" ? (
          <div className="mt-4">
            {error && <p className="text-sm text-red-700">{error}</p>}
            {!doc && !error && <p className="text-sm text-slate-500">Loading…</p>}
            {doc && (
              <>
                <div className="text-xs text-slate-500 mb-3">
                  {doc.doc_id} · version {doc.version} · effective {formatDate(doc.effective_date)}
                </div>
                <blockquote className="whitespace-pre-line border-l-4 border-brand-500 bg-brand-50 p-3 text-sm leading-relaxed">
                  {doc.text}
                </blockquote>
              </>
            )}
          </div>
        ) : (
          <dl className="mt-4 text-sm space-y-2">
            <div><dt className="text-slate-500">Record</dt><dd className="font-medium">{citation.ref}</dd></div>
            {citation.date && <div><dt className="text-slate-500">Date</dt><dd>{formatDate(citation.date)}</dd></div>}
            <p className="text-slate-500 pt-2">This information comes directly from your hospital record.</p>
          </dl>
        )}
      </aside>
    </div>
  );
}
