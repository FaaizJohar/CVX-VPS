import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`panel ${className}`}>{children}</div>;
}

export function CardHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-cvx-border px-4 py-3">
      <h3 className="text-sm font-medium text-cvx-text">{title}</h3>
      {action}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="panel px-4 py-3">
      <div className="stat-label">{label}</div>
      <div className="mt-1 text-lg font-medium text-cvx-text">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-cvx-faint">{sub}</div>}
    </div>
  );
}
