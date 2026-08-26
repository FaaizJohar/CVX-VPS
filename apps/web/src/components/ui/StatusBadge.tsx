const statusStyles: Record<string, string> = {
  running: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  online: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  completed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  active: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  available: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  stopped: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
  offline: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
  frozen: "bg-sky-500/10 text-sky-400 border-sky-500/30",
  pending: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  maintenance: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  reserved: "bg-sky-500/10 text-sky-400 border-sky-500/30",
  provisioning: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  creating: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  warning: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  critical: "bg-red-500/10 text-red-400 border-red-500/30",
  error: "bg-red-500/10 text-red-400 border-red-500/30",
  failed: "bg-red-500/10 text-red-400 border-red-500/30",
  disabled: "bg-zinc-500/10 text-zinc-500 border-zinc-600/40",
  assigned: "bg-blue-500/10 text-blue-400 border-blue-500/30",
};

export function StatusBadge({ status }: { status: string }) {
  const style = statusStyles[status.toLowerCase()] ?? "bg-cvx-raised text-cvx-muted border-cvx-border";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium ${style}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status.toUpperCase()}
    </span>
  );
}
