/** Developer panel (Debug button in the header): shows how the last answer was produced - useful for debugging and for judges. */
export default function DebugPanel({ response, onClose }) {
  return (
    <aside className="fixed bottom-4 right-4 z-30 w-[min(28rem,calc(100vw-2rem))] max-h-[60vh] overflow-auto bg-slate-900 text-slate-100 rounded-lg shadow-xl p-4 text-xs font-mono"
      aria-label="Debug panel" data-testid="debug-panel">
      <div className="flex justify-between items-center mb-2">
        <span className="font-semibold text-sm">Debug · last response</span>
        <button type="button" onClick={onClose} className="text-slate-400 hover:text-white" aria-label="Close debug panel">×</button>
      </div>
      {!response ? <p>No response yet.</p> : (
        <>
          <dl className="grid grid-cols-[6rem_1fr] gap-y-1 mb-3">
            <dt className="text-slate-400">intent</dt><dd>{response.intent}</dd>
            <dt className="text-slate-400">status</dt><dd>{response.status}</dd>
            <dt className="text-slate-400">mode</dt>
            <dd>{response.mode}{response.fallback_reason ? ` (fallback: ${response.fallback_reason})` : ""}</dd>
            <dt className="text-slate-400">latency</dt><dd>{response.latency_ms} ms</dd>
            <dt className="text-slate-400">tools</dt>
            <dd>{response.tool_calls.map((t, i) => <div key={i}>{t.ok ? "✓" : "✗"} {t.name}</div>)}</dd>
          </dl>
          <pre className="whitespace-pre-wrap break-words text-slate-300">{JSON.stringify(response, null, 2)}</pre>
        </>
      )}
    </aside>
  );
}
