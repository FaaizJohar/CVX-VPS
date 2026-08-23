import { useState } from "react";

interface CommandBlockProps {
  command: string;
  label?: string;
  className?: string;
}

/** Copyable shell command with mono type and a subtle copy affordance. */
export function CommandBlock({ command, label, className = "" }: CommandBlockProps) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable (http) — user can select manually */
    }
  }

  return (
    <div className={className}>
      {label && <p className="stat-label mb-1.5">{label}</p>}
      <div className="group relative">
        <pre className="overflow-x-auto rounded-md border border-cvx-border bg-cvx-bg px-3 py-2.5 pr-20 font-mono text-xs leading-relaxed text-cvx-muted">
          {command}
        </pre>
        <button
          type="button"
          onClick={() => void copy()}
          aria-label="Copy command"
          className={`absolute right-1.5 top-1/2 -translate-y-1/2 rounded border px-2 py-1 text-[10px] font-medium uppercase tracking-wider transition-colors duration-150 ${
            copied
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
              : "border-cvx-border bg-cvx-raised text-cvx-muted hover:border-cvx-border-strong hover:text-cvx-text"
          }`}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}
