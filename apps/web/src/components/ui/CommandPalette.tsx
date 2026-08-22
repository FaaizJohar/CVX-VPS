import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { VPS } from "@/types";
import { ModeBadge } from "@/components/ui/ModeBadge";

interface Item {
  id: string;
  label: string;
  hint?: string;
  badge?: React.ReactNode;
  to: string;
}

/** ⌘K / Ctrl+K command palette: jump to pages or any VPS. */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const { data } = useQuery({
    queryKey: ["vps", "palette"],
    queryFn: () => api.get<{ items: VPS[] }>("/api/v1/vps?page=1&page_size=100"),
    enabled: open,
    staleTime: 10_000,
  });

  const items = useMemo<Item[]>(() => {
    const nav: Item[] = [
      { id: "nav-overview", label: "Overview", to: "/app" },
      { id: "nav-vps", label: "Virtual Servers", to: "/app/vps" },
      { id: "nav-create", label: "Create VPS…", to: "/app/vps/new" },
      { id: "admin-nodes", label: "Nodes (admin)", to: "/app/admin/nodes" },
      { id: "admin-images", label: "Images (admin)", to: "/app/admin/images" },
      { id: "admin-users", label: "Users (admin)", to: "/app/admin/users" },
      { id: "admin-logs", label: "Logs (admin)", to: "/app/admin/logs" },
    ];
    const vpsItems: Item[] = (data?.items ?? []).map((v) => ({
      id: v.id,
      label: v.name,
      hint: v.ipv4 ?? v.hostname,
      badge: <ModeBadge mode={v.deployment_mode} />,
      to: `/app/vps/${v.id}`,
    }));
    const all = [...vpsItems, ...nav];
    if (!query.trim()) return all.slice(0, 12);
    const q = query.toLowerCase();
    return all
      .filter((i) => `${i.label} ${i.hint ?? ""}`.toLowerCase().includes(q))
      .slice(0, 12);
  }, [data, query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      // Focus after paint so the input exists.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => setActive(0), [query]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  function choose(i: number) {
    const item = items[i];
    if (!item) return;
    onClose();
    navigate(item.to);
  }

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(active);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]" role="presentation">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-[2px]" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="relative w-full max-w-lg overflow-hidden rounded-xl border border-cvx-border bg-cvx-panel shadow-2xl"
      >
        {/* eslint-disable-next-line jsx-a11y/no-autofocus */}
        <input
          ref={inputRef}
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onInputKey}
          placeholder="Search servers, pages…"
          aria-label="Search"
          aria-controls="cmdk-list"
          className="w-full border-b border-cvx-border bg-transparent px-4 py-3 text-sm text-cvx-text placeholder:text-cvx-faint outline-none"
        />
        {items.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-cvx-faint">No matches.</p>
        ) : (
          <ul id="cmdk-list" ref={listRef} role="listbox" aria-label="Results" className="max-h-80 overflow-y-auto p-1 scrollbar-thin">
            {items.map((item, i) => (
              <li key={`${item.id}-${i}`} role="option" aria-selected={i === active}>
                <button
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(i)}
                  className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors ${
                    i === active ? "bg-cvx-accent/15 text-cvx-text" : "text-cvx-muted"
                  }`}
                >
                  <span className="min-w-0 flex-1 truncate">
                    {item.label}
                    {item.hint && <span className="ml-2 text-xs text-cvx-faint">{item.hint}</span>}
                  </span>
                  {item.badge}
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex items-center gap-3 border-t border-cvx-border px-4 py-2 text-[10px] uppercase tracking-wider text-cvx-faint">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
          <span>esc close</span>
        </div>
      </div>
    </div>
  );
}
