export function EmergencyBanner({ text }) {
  return (
    <div role="alert" data-testid="emergency-banner"
      className="bg-red-600 text-white rounded-lg p-4 font-medium shadow-sm">
      <div className="text-lg font-bold mb-1">🚨 Possible emergency</div>
      {text}
    </div>
  );
}

export function NotFoundNotice({ text }) {
  return (
    <div data-testid="not-found" className="bg-slate-100 border border-slate-200 text-slate-700 rounded-lg p-3">
      <span aria-hidden="true">🔎 </span>{text}
    </div>
  );
}

export function UnauthorizedNotice({ text }) {
  return (
    <div data-testid="unauthorized" className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg p-3">
      <span aria-hidden="true">🔒 </span>{text}
    </div>
  );
}

export function ErrorNotice({ text }) {
  return (
    <div role="alert" className="bg-red-50 border border-red-200 text-red-800 rounded-lg p-3">{text}</div>
  );
}
