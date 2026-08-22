import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { VPS } from "@/types";

type Phase = "locked" | "authenticating" | "granted" | "denied";

const AUTH_STEPS = [
  "Establishing secure channel",
  "Verifying credentials",
  "Authorizing access",
  "Opening workspace",
];

export default function VPSUnlockPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [phase, setPhase] = useState<Phase>("locked");
  const [stepIdx, setStepIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const { data: vps } = useQuery({
    queryKey: ["vps", id],
    queryFn: () => api.get<VPS>(`/api/v1/vps/${id}`),
  });

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPhase("authenticating");
    setStepIdx(0);

    // Drive the progress display while the real request runs.
    const timer = setInterval(() => setStepIdx((i) => Math.min(i + 1, AUTH_STEPS.length - 1)), 220);
    try {
      await api.post("/api/v1/auth/verify-password", {
        email: "", // not used; identity comes from the session
        password,
      });
      sessionStorage.setItem(`cvx-unlock-${id}`, "1");
      setStepIdx(AUTH_STEPS.length - 1);
      await new Promise((r) => setTimeout(r, 350));
      setPhase("granted");
      await new Promise((r) => setTimeout(r, 700));
      navigate(`/app/vps/${id}/command`, { replace: true });
    } catch (err) {
      setPhase("denied");
      setError(err instanceof ApiError ? err.message : "Authentication failed.");
    } finally {
      clearInterval(timer);
    }
  }

  return (
    <div className="flex min-h-full flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm text-center">
        <p className="font-mono text-2xl font-semibold tracking-tight">CVX</p>

        <div className="mt-8">
          <p className="stat-label">Secure VPS</p>
          <h1 className="mt-1 font-mono text-lg">{vps?.name ?? "…"}</h1>
          <p className="mt-1 font-mono text-xs text-cvx-faint">
            {vps?.ipv4 ?? vps?.hostname ?? ""}
          </p>
        </div>

        {phase === "locked" || phase === "denied" ? (
          <form onSubmit={onSubmit} className="mt-10 space-y-4">
            <Input
              autoFocus
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your CVX password"
              className="text-center font-mono tracking-widest"
              required
            />
            {error && (
              <p className="rounded-md border border-cvx-danger/30 bg-cvx-danger/5 px-3 py-2 text-xs text-cvx-danger">
                ACCESS DENIED — {error}
              </p>
            )}
            <Button type="submit" variant="primary" className="w-full">
              Unlock
            </Button>
            <Link to="/app/vps" className="block pt-2 text-xs text-cvx-faint hover:text-cvx-muted">
              ← Back to servers
            </Link>
          </form>
        ) : phase === "authenticating" ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mx-auto mt-10 max-w-xs space-y-3 text-left"
          >
            {AUTH_STEPS.map((label, i) => (
              <div key={label} className="flex items-center gap-3 font-mono text-xs">
                <span className={i <= stepIdx ? "text-cvx-accent" : "text-cvx-faint"}>
                  {i < stepIdx ? "✓" : i === stepIdx ? "▸" : "·"}
                </span>
                <span className={i <= stepIdx ? "text-cvx-text" : "text-cvx-faint"}>{label}</span>
              </div>
            ))}
            <div className="h-1 overflow-hidden rounded bg-cvx-raised">
              <motion.div
                className="h-full bg-cvx-accent"
                initial={{ width: "0%" }}
                animate={{ width: `${((stepIdx + 1) / AUTH_STEPS.length) * 100}%` }}
                transition={{ ease: "easeOut", duration: 0.25 }}
              />
            </div>
          </motion.div>
        ) : (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-10">
            <p className="font-mono text-sm uppercase tracking-[0.3em] text-emerald-400">
              Access granted
            </p>
          </motion.div>
        )}
      </div>
    </div>
  );
}
