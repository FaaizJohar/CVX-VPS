import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Loading";

export default function LoginPage() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    <div className="relative flex min-h-full items-center justify-center overflow-hidden px-4">
      {/* Backdrop */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div
          className="absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage:
              "linear-gradient(to right, rgba(148,163,184,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.05) 1px, transparent 1px)",
            backgroundSize: "44px 44px",
          }}
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 60% 45% at 50% 38%, rgba(99,102,241,0.10), transparent 70%)",
          }}
        />
      </div>

      <div className="animate-fade-up relative w-full max-w-sm">
        <div className="mb-10 text-center">
          <div
            aria-hidden
            className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-lg border border-cvx-border bg-cvx-panel shadow-lg shadow-black/20"
          >
            <span className="font-mono text-lg font-semibold tracking-tight text-cvx-text">
              C<span className="text-cvx-accent">V</span>X
            </span>
          </div>
          <h1 className="sr-only">CVX sign in</h1>
          <p className="text-xs uppercase tracking-[0.3em] text-cvx-faint">
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
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••"
                className="pr-16"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-cvx-faint transition-colors hover:text-cvx-muted"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </div>

          {error && (
            <p
              role="alert"
              className="animate-fade-up rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2 text-xs leading-relaxed text-cvx-danger"
            >
              {error}
            </p>
          )}

          <Button type="submit" variant="primary" disabled={busy} className="w-full">
            {busy ? (
              <>
                <Spinner /> Authenticating…
              </>
            ) : (
              "Sign in"
            )}
          </Button>
        </form>

        <p className="mt-6 text-center text-[11px] text-cvx-faint">
          Full control. Clean experience.
        </p>
      </div>
    </div>
  );
}
