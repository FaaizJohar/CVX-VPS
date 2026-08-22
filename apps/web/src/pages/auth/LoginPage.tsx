import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function LoginPage() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.post("/api/v1/auth/login", { email, password });
      await refresh();
      navigate("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-10 text-center">
          <h1 className="font-mono text-3xl font-semibold tracking-tight">CVX</h1>
          <p className="mt-2 text-xs uppercase tracking-[0.3em] text-cvx-faint">
            VPS Infrastructure Control
          </p>
        </div>

        <form onSubmit={onSubmit} className="panel space-y-4 p-6">
          <div className="space-y-1.5">
            <label htmlFor="email" className="stat-label">Email</label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="password" className="stat-label">Password</label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••"
            />
          </div>

          {error && (
            <p className="rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2 text-xs text-cvx-danger">
              {error}
            </p>
          )}

          <Button type="submit" variant="primary" disabled={busy} className="w-full">
            {busy ? "Authenticating…" : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-center text-[11px] text-cvx-faint">
          Full control. Clean experience.
        </p>
      </div>
    </div>
  );
}
