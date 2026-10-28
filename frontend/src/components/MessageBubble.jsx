/** **bold** markdown (LLMs use it for emphasis) -> <strong>; everything else stays plain text. */
function withBold(text, key) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    /^\*\*[^*]+\*\*$/.test(p) ? <strong key={`${key}-${i}`}>{p.slice(2, -2)}</strong> : <span key={`${key}-${i}`}>{p}</span>);
}

/** Renders an answer: bullets / numbered steps, with [S1] tags turned into clickable citation markers. */
function withCitations(text, onCite, keyPrefix) {
  const parts = text.split(/(\[S\d+\])/g);
  return parts.map((p, i) => {
    const m = p.match(/^\[(S\d+)\]$/);
    if (!m) return <span key={`${keyPrefix}-${i}`}>{withBold(p, `${keyPrefix}-${i}`)}</span>;
    return (
      <button key={`${keyPrefix}-${i}`} type="button" onClick={() => onCite(m[1])}
        className="align-super text-[0.65rem] font-semibold text-brand-600 hover:underline mx-0.5"
        aria-label={`Open source ${m[1]}`}>
        {m[1]}
      </button>
    );
  });
}

export default function MessageBubble({ text, onCite, animate = false }) {
  // animate: blocks appear one after another (the verified answer "types itself in").
  const reveal = (i) => (animate ? { className: "reveal", style: { animationDelay: `${i * 90}ms` } } : {});
  const lines = text.split("\n");
  const blocks = [];
  let list = null;
  lines.forEach((line, i) => {
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*(\d+)\.\s+(.*)$/);
    if (bullet || numbered) {
      const type = bullet ? "ul" : "ol";
      if (!list || list.type !== type) {
        list = { type, items: [] };
        blocks.push(list);
      }
      list.items.push(bullet ? bullet[1] : numbered[2]);
      return;
    }
    list = null;
    if (line.trim()) blocks.push({ type: "p", text: line });
  });

  return (
    <div className="space-y-2 leading-relaxed">
      {blocks.map((b, i) => {
        if (b.type === "p") return <p key={i} {...reveal(i)}>{withCitations(b.text, onCite, i)}</p>;
        const Tag = b.type;
        return (
          <Tag key={i} className={`${b.type === "ol" ? "list-decimal" : "list-disc"} pl-5 space-y-1`}>
            {b.items.map((item, j) => (
              <li key={j} {...reveal(i + j)}>{withCitations(item, onCite, `${i}-${j}`)}</li>
            ))}
          </Tag>
        );
      })}
    </div>
  );
}
