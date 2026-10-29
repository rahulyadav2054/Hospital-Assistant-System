import { AGENTS, exampleFor } from "../agents.js";

/** Grid of AI agents in the welcome message: each tile starts the agent with an example goal. */
export default function AgentHub({ username, onAsk, disabled }) {
  return (
    <div className="mt-4" data-testid="agent-hub">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-semibold tracking-wider text-violet-700 uppercase">Your AI agents</span>
        <span className="text-[0.7rem] text-slate-500">they plan, use hospital tools and ask before acting</span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {AGENTS.map((a) => {
          const example = exampleFor(username, a.name);
          return (
            <button key={a.name} type="button" disabled={disabled} onClick={() => onAsk(example)}
              data-testid={`agent-tile-${a.name}`}
              className="group text-left border border-violet-200 hover:border-violet-500 hover:shadow-sm bg-gradient-to-br from-white to-violet-50 rounded-xl px-3 py-2 transition disabled:opacity-60">
              <div className="flex items-center gap-2">
                <span className="text-xl" aria-hidden="true">{a.icon}</span>
                <span className="font-semibold text-slate-800">{a.title}</span>
                <span className="ml-auto text-[0.65rem] font-semibold text-violet-700 bg-violet-100 rounded-full px-2 py-0.5">AGENT</span>
              </div>
              <p className="text-xs text-slate-600 mt-1">{a.desc}</p>
              <p className="text-xs text-violet-700 mt-1 group-hover:underline">Try: "{example}" →</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Compact list for the sidebar. */
export function AgentList({ username, onAsk, disabled }) {
  return (
    <ul className="space-y-1" data-testid="sidebar-agents">
      {AGENTS.map((a) => (
        <li key={a.name}>
          <button type="button" disabled={disabled} onClick={() => onAsk(exampleFor(username, a.name))}
            className="w-full text-left text-sm rounded-lg px-2 py-1.5 hover:bg-violet-50 flex items-center gap-2 disabled:opacity-60"
            title={a.desc}>
            <span aria-hidden="true">{a.icon}</span>
            <span>{a.title}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
