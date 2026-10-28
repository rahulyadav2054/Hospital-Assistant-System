import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth.jsx";

const DEMO_USERS = [
  { username: "asha", label: "Asha Verma", hint: "Gold plan · cardiology appointment" },
  { username: "rahul", label: "Rahul Mehta", hint: "Basic plan · pre-op tests pending" },
  { username: "meera", label: "Meera Iyer", hint: "Silver plan · glucose & HbA1c results" },
  { username: "john", label: "John D'Souza", hint: "Expired insurance policy" },
  { username: "staff1", label: "Kavya (Front Desk)", hint: "Staff role" },
];

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.status === 429 ? "Too many attempts. Please wait a minute." : err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-full flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <div className="text-sm font-semibold tracking-wider text-brand-500 uppercase">City Care Hospital</div>
          <h1 className="text-2xl font-bold text-brand-900 mt-1">Patient Services Assistant</h1>
        </div>

        <form onSubmit={submit} className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium mb-1">Username</label>
            <input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
              className="w-full border border-slate-300 rounded-lg px-3 py-2" required />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium mb-1">Password</label>
            <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password" className="w-full border border-slate-300 rounded-lg px-3 py-2" required />
          </div>
          {error && <p role="alert" className="text-sm text-red-700 bg-red-50 rounded-md px-3 py-2">{error}</p>}
          <button type="submit" disabled={busy}
            className="w-full bg-brand-700 hover:bg-brand-600 text-white font-medium rounded-lg py-2 disabled:opacity-60">
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <section className="mt-6" aria-label="Demo accounts">
          <h2 className="text-sm font-semibold text-slate-600 mb-2">Demo accounts (password: demo123)</h2>
          <div className="grid gap-2">
            {DEMO_USERS.map((u) => (
              <button key={u.username} type="button"
                onClick={() => { setUsername(u.username); setPassword("demo123"); }}
                className="text-left bg-white border border-slate-200 hover:border-brand-500 rounded-lg px-3 py-2">
                <span className="font-medium">{u.label}</span>
                <span className="block text-xs text-slate-500">{u.hint}</span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
