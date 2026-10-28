export default function CitationChips({ citations, onOpen }) {
  if (!citations?.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-3" aria-label="Sources">
      <span className="text-xs text-slate-500 mr-1 self-center">Sources:</span>
      {citations.map((c) => (
        <button key={c.id} type="button" onClick={() => onOpen(c.id)} data-testid="citation-chip"
          className="text-xs bg-brand-50 border border-brand-100 text-brand-700 rounded-full px-2.5 py-0.5 hover:bg-brand-100">
          <span className="font-semibold">{c.id}</span>{" "}
          {c.source_type === "document" ? "📄" : "🗂️"} {c.title}
          {c.section ? ` §${c.section.split(" ")[0].replace(/\.$/, "")}` : ""}
        </button>
      ))}
    </div>
  );
}
