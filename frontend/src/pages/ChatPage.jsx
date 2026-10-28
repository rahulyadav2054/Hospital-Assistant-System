import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat } from "../api/client.js";
import AgentCard from "../components/AgentCard.jsx";
import ConfirmActionModal from "../components/ConfirmActionModal.jsx";
import DebugPanel from "../components/DebugPanel.jsx";
import LiveProgress from "../components/LiveProgress.jsx";
import Reply from "../components/Reply.jsx";
import Sidebar from "../components/Sidebar.jsx";
import SourceDrawer from "../components/SourceDrawer.jsx";
import { useAuth } from "../hooks/useAuth.jsx";

// Suggestions per demo account, so every chip matches that patient's records.
const SUGGESTIONS = {
  asha: [
    "What are visiting hours for ICU patients?",
    "How do I schedule an MRI scan?",
    "What are my upcoming appointments?",
    "Am I covered for knee replacement under my insurance plan?",
    "What is my cholesterol level?",
    "Reschedule my cardiology appointment",
    "Get me ready for my surgery",
    "Do you have treatment information for proton beam therapy?",
  ],
  rahul: [
    "Get me ready for my surgery",
    "My doctor recommended surgery. What pre-operative tests are still pending?",
    "Is gallbladder surgery covered?",
    "What were my CBC results?",
    "What are my upcoming appointments?",
    "Reschedule my general surgery appointment",
    "What should I do before discharge?",
  ],
  meera: [
    "What is my latest blood sugar reading?",
    "Show my HbA1c trend",
    "Is knee replacement covered for me?",
    "Reschedule my endocrinology appointment",
    "Which department treats diabetes?",
  ],
  john: [
    "Am I covered for knee replacement?",
    "What are my upcoming appointments?",
    "How do I schedule an MRI scan?",
  ],
  patient: [
    "What are visiting hours for ICU patients?",
    "How do I schedule an MRI scan?",
    "What are my upcoming appointments?",
    "What are my latest lab results?",
  ],
  staff: [
    "What are visiting hours for ICU patients?",
    "Which department handles knees?",
    "How do I schedule an MRI scan?",
  ],
};

function newSessionId() {
  return (crypto.randomUUID?.() ?? `s-${Date.now()}-${Math.random().toString(16).slice(2)}`);
}

export default function ChatPage() {
  const { user, logout } = useAuth();
  const [sessionId] = useState(newSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastResponse, setLastResponse] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const [source, setSource] = useState(null);
  const [debug, setDebug] = useState(false);
  const [toast, setToast] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey && e.key.toLowerCase() === "d") {
        e.preventDefault();
        setDebug((d) => !d);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(t);
  }, [toast]);

  const newId = () => `${Date.now()}-${Math.random()}`;
  const addMessage = (m) => setMessages((ms) => [...ms, { id: newId(), ...m }]);
  const updateMessage = (id, fn) => setMessages((ms) => ms.map((m) => (m.id === id ? fn(m) : m)));

  /** Apply one streamed progress event to the live view of an answer. */
  function applyEvent(live, type, ev) {
    if (type === "tool") {
      const others = live.tools.filter((t) => t.seq !== ev.seq);
      return { ...live, tools: [...others, ev].sort((a, b) => a.seq - b.seq) };
    }
    if (type === "step") {
      const others = live.steps.filter((s) => s.index !== ev.index);
      return { ...live, steps: [...others, ev].sort((a, b) => a.index - b.index) };
    }
    if (type === "agent") return { ...live, agent: ev.title };
    if (type === "status") return { ...live, status: ev.text };
    return live;
  }

  async function send(text) {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    setInput("");
    addMessage({ role: "user", text: message });
    const id = newId();
    setMessages((ms) => [...ms, { id, role: "assistant", live: { tools: [], steps: [], agent: null, status: "" } }]);
    setBusy(true);
    try {
      const r = await streamChat({ message, session_id: sessionId },
        (type, ev) => updateMessage(id, (m) => ({ ...m, live: applyEvent(m.live, type, ev) })));
      setLastResponse(r);
      updateMessage(id, (m) => ({ ...m, live: null, response: r }));
      if (r.action_required?.type === "confirm_reschedule") setPendingAction(r.action_required);
    } catch (e) {
      const errText = e.status === 429 ? "You are sending messages too quickly. Please wait a moment." : e.message;
      updateMessage(id, (m) => ({ ...m, live: null, response: { status: "error", answer: errText } }));
    } finally {
      setBusy(false);
    }
  }

  const openSource = useCallback((response, id) => {
    const c = response.citations?.find((x) => x.id === id);
    if (c) setSource(c);
  }, []);
  const closeSource = useCallback(() => setSource(null), []);

  function onActionDone({ ok, message }) {
    setPendingAction(null);
    setToast({ ok, message });
    addMessage({ role: "system", text: ok ? `✅ ${message}` : `⚠️ ${message}` });
    if (ok) setRefreshKey((k) => k + 1);
  }

  function onPlanDone({ ok, message }) {
    setToast({ ok, message });
    addMessage({ role: "system", text: ok ? `✅ ${message}` : `⚠️ ${message}` });
    if (ok) setRefreshKey((k) => k + 1);
  }

  function onActionClosed() {
    setPendingAction(null);
    addMessage({ role: "system", text: "Reschedule cancelled. Your appointment was not changed." });
  }

  const suggestions = SUGGESTIONS[user.username] ?? SUGGESTIONS[user.role] ?? SUGGESTIONS.patient;

  return (
    <div className="h-full flex flex-col">
      <header className="bg-brand-700 text-white px-4 py-3 flex items-center gap-3"
        style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))" }}>
        <button type="button" className="md:hidden text-xl" onClick={() => setSidebarOpen((o) => !o)}
          aria-label="Toggle summary">☰</button>
        <div className="flex-1 min-w-0">
          <div className="font-semibold truncate">City Care Hospital · Patient Assistant</div>
        </div>
        <span className="text-sm hidden sm:inline">{user.name}</span>
        <button type="button" onClick={() => setDebug((d) => !d)} aria-pressed={debug} data-testid="debug-toggle"
          className={`text-sm rounded px-3 py-1 ${debug ? "bg-white text-brand-700" : "bg-white/10 hover:bg-white/20"}`}>
          Debug
        </button>
        <button type="button" onClick={logout} className="text-sm bg-white/10 hover:bg-white/20 rounded px-3 py-1">
          Sign out
        </button>
      </header>

      <div className="flex-1 flex flex-col md:flex-row min-h-0">
        <Sidebar user={user} refreshKey={refreshKey} open={sidebarOpen} />

        <main className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 overflow-y-auto px-4 py-6" aria-live="polite">
            <div className="max-w-3xl mx-auto space-y-4">
              <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
                <p>Hi {user.name?.split(" ")[0]}, how can I help today?</p>
                <div className="flex flex-wrap gap-2 mt-3">
                  {suggestions.map((s) => (
                    <button key={s} type="button" onClick={() => send(s)} disabled={busy}
                      className="text-xs bg-brand-50 hover:bg-brand-100 border border-brand-100 text-brand-700 rounded-full px-3 py-1 disabled:opacity-60">
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              {messages.map((m) => {
                if (m.role === "user") {
                  return (
                    <div key={m.id} className="flex justify-end">
                      <div className="bg-brand-700 text-white rounded-2xl rounded-tr-sm px-4 py-2 max-w-[85%] whitespace-pre-wrap">{m.text}</div>
                    </div>
                  );
                }
                if (m.role === "system") {
                  return <div key={m.id} className="text-center text-sm text-slate-600" data-testid="system-message">{m.text}</div>;
                }
                if (m.live) {
                  return (
                    <div key={m.id} className="max-w-[92%]">
                      {m.live.agent
                        ? <AgentCard title={m.live.agent} steps={m.live.steps} live status={m.live.status} />
                        : <LiveProgress live={m.live} />}
                    </div>
                  );
                }
                return (
                  <div key={m.id} className="max-w-[92%]">
                    <Reply r={m.response} onOpenSource={openSource} onPlanDone={onPlanDone} />
                  </div>
                );
              })}
              <div ref={endRef} />
            </div>
          </div>

          <form onSubmit={(e) => { e.preventDefault(); send(); }}
            className="border-t border-slate-200 bg-white px-4 pt-3"
            style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}>
            <div className="max-w-3xl mx-auto flex gap-2">
              <label htmlFor="chat-input" className="sr-only">Your question</label>
              <input id="chat-input" data-testid="chat-input" value={input} onChange={(e) => setInput(e.target.value)}
                placeholder="Type your question…" maxLength={2000} autoComplete="off"
                className="flex-1 border border-slate-300 rounded-lg px-3 py-2" />
              <button type="submit" data-testid="send" disabled={busy || !input.trim()}
                className="bg-brand-700 hover:bg-brand-600 text-white font-medium rounded-lg px-5 disabled:opacity-50">
                Send
              </button>
            </div>
            <p className="max-w-3xl mx-auto text-[0.7rem] text-slate-500 mt-2">
              This assistant does not provide medical advice. In an emergency call 108.
            </p>
          </form>
        </main>
      </div>

      {pendingAction && <ConfirmActionModal action={pendingAction} onDone={onActionDone} onClose={onActionClosed} />}
      {source && <SourceDrawer citation={source} onClose={closeSource} />}
      {debug && <DebugPanel response={lastResponse} onClose={() => setDebug(false)} />}
      {toast && (
        <div role="status" className={`fixed top-16 left-1/2 -translate-x-1/2 z-50 rounded-lg px-4 py-2 shadow-lg text-white ${toast.ok ? "bg-emerald-600" : "bg-amber-600"}`}>
          {toast.message}
        </div>
      )}
    </div>
  );
}
