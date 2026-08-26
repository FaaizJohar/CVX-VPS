import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { LogItem, Paginated, VPS } from "@/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { fmtDate } from "@/lib/format";

const SEVERITIES = ["", "debug", "info", "warning", "error", "critical"];

export default function LogsTab({ vps }: { vps: VPS }) {
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  const pageSize = 50;
  const params = new URLSearchParams({
    vps_id: vps.id,
    page: String(page),
    page_size: String(pageSize),
  });
  if (severity) params.set("severity", severity);
  if (query) params.set("search", query);

  const { data, isLoading } = useQuery({
    queryKey: ["vps", vps.id, "logs", params.toString()],
    queryFn: () => api.get<Paginated<LogItem>>(`/api/v1/logs?${params}`),
    refetchInterval: 15_000,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <Card>
      <CardHeader title="VPS logs" />
      <div className="flex flex-wrap items-center gap-2 border-b border-cvx-border px-4 py-3">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setQuery(search.trim());
          }}
        >
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search messages…"
            className="w-64"
          />
          <Button type="submit" size="sm" variant="ghost">Search</Button>
        </form>
        <Select
          value={severity}
          onChange={(e) => {
            setSeverity(e.target.value);
            setPage(1);
          }}
          className="w-36"
        >
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s ? s.toUpperCase() : "All severities"}</option>
          ))}
        </Select>
        <span className="ml-auto text-xs text-cvx-faint">{data?.total ?? 0} entries</span>
      </div>

      {isLoading ? (
        <p className="px-4 py-8 text-center text-sm text-cvx-faint">Loading…</p>
      ) : !data || data.items.length === 0 ? (
        <p className="px-4 py-10 text-center text-sm text-cvx-faint">No log entries match.</p>
      ) : (
        <>
          <div className="divide-y divide-cvx-border font-mono text-xs">
            {data.items.map((l) => (
              <div key={l.id} className="flex gap-3 px-4 py-2">
                <span className="shrink-0 text-cvx-faint">{fmtDate(l.created_at)}</span>
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
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="flex items-center gap-1 disabled:opacity-30 hover:text-cvx-text">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                Prev
              </button>
              <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="flex items-center gap-1 disabled:opacity-30 hover:text-cvx-text">
                Next
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
              </button>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
