interface ModeBadgeProps {
  mode?: string;
  className?: string;
}

/** LOCAL / NODE deployment-mode chip shown on VPS rows and headers. */
export function ModeBadge({ mode, className = "" }: ModeBadgeProps) {
  if (mode !== "local" && mode !== "node") return null;
  const isLocal = mode === "local";
  return (
    <span
      title={isLocal ? "Deployed on this machine (control plane host)" : "Deployed on an enrolled node"}
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
        isLocal
          ? "border-violet-500/40 bg-violet-500/10 text-violet-300"
          : "border-cvx-border bg-cvx-raised text-cvx-muted"
      } ${className}`}
    >
      {isLocal ? "LOCAL" : "NODE"}
    </span>
  );
}
