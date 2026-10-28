import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Button, Field, Input } from "../components/ui";
import { useAuth } from "../lib/auth";

const DEMO = [
  ["pm.santos", "Portfolio manager (maker)"],
  ["pm.reyes", "Portfolio manager (checker)"],
  ["trader.lim", "Dealer"],
  ["compliance.cruz", "Compliance officer"],
  ["risk.tan", "Risk manager"],
  ["ops.garcia", "Operations"],
  ["admin", "Platform admin"],
];

export default function Login() {
  const { user, login } = useAuth();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/portfolio" replace />;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try { await login(u, p); } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="flex min-h-full items-center justify-center bg-bg p-6">
      <div className="grid w-full max-w-[880px] border border-line bg-panel md:grid-cols-[1fr_340px]">
        <form onSubmit={submit} className="p-8">
          <div className="flex items-baseline gap-3">
            <span className="text-[24px] font-bold text-[#3b82f6] italic">KFINTECH</span>
            <span className="text-[20px] font-semibold">mPower</span>
          </div>
          <div className="lbl mt-1">Investment management · compliance · portfolio analytics</div>
          <div className="mt-8 grid gap-4">
            <Field label="Username"><Input autoFocus autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} /></Field>
            <Field label="Password"><Input type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} /></Field>
            {err && <div className="border border-down/50 bg-down/10 px-3 py-2 text-[12px] text-down" role="alert">{err}</div>}
            <Button variant="primary" type="submit" disabled={busy || !u || !p} className="h-9">{busy ? "Signing in…" : "Sign in"}</Button>
          </div>
          <p className="mt-6 text-[11px] text-mute">Access is logged. Five failed attempts lock the account.</p>
        </form>
        <aside className="border-t border-line bg-panel-2 p-6 md:border-t-0 md:border-l">
          <div className="lbl">Demo users</div>
          <p className="mt-1 text-[11.5px] text-mute">Password: value of MPOWER_DEMO_PASSWORD (default in README)</p>
          <ul className="mt-3 space-y-1">
            {DEMO.map(([name, role]) => (
              <li key={name}><button type="button" onClick={() => setU(name)} className="flex w-full justify-between px-2 py-1 text-left hover:bg-raised">
                <span className="font-mono text-[12.5px]">{name}</span><span className="text-[11.5px] text-dim">{role}</span></button></li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}
