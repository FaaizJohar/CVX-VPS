import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { LogItem, Paginated } from "@/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { fmtDate } from "@/lib/format";

const SOURCES = ["", "panel", "agent", "auth", "audit"];
const SEVERITIES = ["", "debug", "info", "warning", "error", "critical"];

export default function AdminLogsPage() {
  const [page, setPage] = useState(1);
  const [source, setSource] = useState("");
  const [severity, setSeverity] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  const pageSize = 100;
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (source) params.set("source", source);
  if (severity) params.set("severity", severity);
  if (search) params.set("search", search);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-logs", params.toString()],
    queryFn: () => api.get<Paginated<LogItem>>(`/api/v1/logs?${params}`),
    refetchInterval: 15_000,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">System logs</h1>
        <p className="text-xs text-cvx-faint">Panel, agent and auth events across all nodes.</p>
      </div>

      <Card>
        <CardHeader title={`Entries (${data?.total ?? 0})`} />
        <div className="flex flex-wrap items-center gap-2 border-b border-cvx-border px-4 py-3">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setPage(1);
              setSearch(searchInput.trim());
            }}
          >
            <Input value={searchInput} onChange={(e) => setSearchInput(e.target.value)} placeholder="Search…" className="w-64" />
            <Button type="submit" size="sm" variant="ghost">Search</Button>
          </form>
          <Select value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }} className="w-36">
            {SOURCES.map((s) => <option key={s} value={s}>{s || "All sources"}</option>)}
          </Select>
          <Select value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1); }} className="w-40">
            {SEVERITIES.map((s) => <option key={s} value={s}>{s ? s.toUpperCase() : "All severities"}</option>)}
          </Select>
        </div>

        {isLoading ? (
          <p className="px-4 py-8 text-center text-sm text-cvx-faint">Loading…</p>
        ) : !data || data.items.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-cvx-faint">No entries match.</p>
        ) : (
          <>
            <div className="max-h-[60vh] divide-y divide-cvx-border overflow-y-auto font-mono text-xs scrollbar-thin">
              {data.items.map((l) => (
                <div key={l.id} className="flex gap-3 px-4 py-2">
                  <span className="shrink-0 text-cvx-faint">{fmtDate(l.created_at)}</span>
                  <span className="w-12 shrink-0 uppercase text-cvx-accent">{l.source}</span>
                  <span
                    className={`w-14 shrink-0 uppercase ${
                      l.severity === "error" || l.severity === "critical"
                        ? "text-red-400"
                        : l.severity === "warning"
                          ? "text-amber-400"
                          : "text-cvx-faint"
                    }`}
                  >
                    {l.severity}
                  </span>
                  <span className="min-w-0 break-all text-cvx-muted">{l.message}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between border-t border-cvx-border px-4 py-2 text-xs text-cvx-faint">
              <span>Page {data.page} of {totalPages}</span>
              <div className="flex gap-3">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="disabled:opacity-30 hover:text-cvx-text">← Prev</button>
                <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="disabled:opacity-30 hover:text-cvx-text">Next →</button>
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
