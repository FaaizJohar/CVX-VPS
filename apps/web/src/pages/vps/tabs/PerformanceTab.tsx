import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import type { MetricPoint, VPS } from "@/types";
import { Card, CardHeader, Stat } from "@/components/ui/Card";
import { fmtMbps } from "@/lib/format";

const RANGES = ["1h", "6h", "24h", "7d", "30d"] as const;

export default function PerformanceTab({ vps }: { vps: VPS }) {
  const [range, setRange] = useState<(typeof RANGES)[number]>("1h");

  const { data } = useQuery({
    queryKey: ["vps", vps.id, "metrics", range],
    queryFn: () => api.get<{ series: MetricPoint[] }>(`/api/v1/metrics/vps/${vps.id}?range=${range}`),
    refetchInterval: range === "1h" ? 10_000 : false,
  });

  const series = data?.series ?? [];
  const last = series[series.length - 1];
  const memPct =
    last?.mem_used_mb != null && last?.mem_total_mb
      ? (last.mem_used_mb / last.mem_total_mb) * 100
      : null;
  const diskPct =
    last?.disk_used_gb != null && last?.disk_total_gb
      ? (last.disk_used_gb / last.disk_total_gb) * 100
      : null;

  const timeFmt = (ts: string) =>
    new Date(ts).toLocaleTimeString(undefined, range === "1h" || range === "6h"
      ? { hour: "2-digit", minute: "2-digit" }
      : { month: "short", day: "numeric" });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="grid flex-1 grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat
            label="CPU"
            value={last?.cpu_percent != null ? `${last.cpu_percent.toFixed(1)}%` : "—"}
          />
          <Stat
            label="Memory"
            value={memPct != null ? `${memPct.toFixed(0)}%` : "—"}
            sub={last?.mem_used_mb != null ? `${(last.mem_used_mb / 1024).toFixed(2)} GB used` : undefined}
          />
          <Stat
            label="Disk"
            value={diskPct != null ? `${diskPct.toFixed(0)}%` : "—"}
            sub={last?.disk_used_gb != null ? `${last.disk_used_gb.toFixed(1)} GB` : undefined}
          />
          <Stat
            label="Network"
            value={fmtMbps((last?.net_rx_bps ?? 0) + (last?.net_tx_bps ?? 0))}
            sub={`↓ ${fmtMbps(last?.net_rx_bps)} · ↑ ${fmtMbps(last?.net_tx_bps)}`}
          />
        </div>
      </div>

      <div className="flex gap-1">
        {RANGES.map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium uppercase tracking-wider transition-colors ${
              r === range ? "bg-cvx-accent/15 text-cvx-accent" : "text-cvx-faint hover:text-cvx-muted"
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader title="CPU usage (%)" />
        <div className="h-56 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series}>
              <CartesianGrid stroke="#1e2229" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="ts" tickFormatter={timeFmt} tick={{ fill: "#5b616c", fontSize: 11 }} stroke="#1e2229" />
              <YAxis domain={[0, 100]} tick={{ fill: "#5b616c", fontSize: 11 }} stroke="#1e2229" />
              <Tooltip
                contentStyle={{ background: "#15181d", border: "1px solid #2a2f38", borderRadius: 8, fontSize: 12 }}
                labelFormatter={(l) => new Date(String(l)).toLocaleString()}
              />
              <Area type="monotone" dataKey="cpu_percent" stroke="#3d7bfd" fill="#3d7bfd22" strokeWidth={1.5} dot={false} name="CPU %" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <CardHeader title="Memory (MB)" />
        <div className="h-56 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series}>
              <CartesianGrid stroke="#1e2229" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="ts" tickFormatter={timeFmt} tick={{ fill: "#5b616c", fontSize: 11 }} stroke="#1e2229" />
              <YAxis tick={{ fill: "#5b616c", fontSize: 11 }} stroke="#1e2229" />
              <Tooltip
                contentStyle={{ background: "#15181d", border: "1px solid #2a2f38", borderRadius: 8, fontSize: 12 }}
                labelFormatter={(l) => new Date(String(l)).toLocaleString()}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="mem_used_mb" stroke="#34d399" fill="#34d39918" strokeWidth={1.5} dot={false} name="Used" />
              <Line type="monotone" dataKey="mem_total_mb" stroke="#5b616c" strokeWidth={1} dot={false} name="Total" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <CardHeader title="Network throughput" />
        <div className="h-56 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series}>
              <CartesianGrid stroke="#1e2229" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="ts" tickFormatter={timeFmt} tick={{ fill: "#5b616c", fontSize: 11 }} stroke="#1e2229" />
              <YAxis tickFormatter={fmtMbps} tick={{ fill: "#5b616c", fontSize: 11 }} stroke="#1e2229" width={80} />
              <Tooltip
                contentStyle={{ background: "#15181d", border: "1px solid #2a2f38", borderRadius: 8, fontSize: 12 }}
                labelFormatter={(l) => new Date(String(l)).toLocaleString()}
                formatter={(value: number | string) => fmtMbps(Number(value))}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="net_rx_bps" stroke="#3d7bfd" strokeWidth={1.5} dot={false} name="RX" />
              <Line type="monotone" dataKey="net_tx_bps" stroke="#fbbf24" strokeWidth={1.5} dot={false} name="TX" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {series.length === 0 && (
        <p className="py-6 text-center text-sm text-cvx-faint">
          No metric samples in this window yet. Samples arrive with node heartbeats.
        </p>
      )}
    </div>
  );
}
