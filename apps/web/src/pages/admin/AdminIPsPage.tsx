import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { NodeInfo } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { StatusBadge } from "@/components/ui/StatusBadge";

interface IPAddress {
  id: string;
  node_id: string | null;
  family: number;
  address: string;
  cidr: number | null;
  gateway: string | null;
  status: string;
  vps_id: string | null;
  notes: string | null;
}

interface Network {
  id: string;
  node_id: string;
  name: string;
  type: string;
  description: string;
  ipv4_subnet: string | null;
  ipv6_subnet: string | null;
  managed: boolean;
  is_default: boolean;
}

export default function AdminIPsPage() {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [familyFilter, setFamilyFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [bulk, setBulk] = useState("");
  const [gateway, setGateway] = useState("");
  const [netForm, setNetForm] = useState({ node_id: "", name: "", ipv4_subnet: "", ipv6_subnet: "" });

  const { data: ips, isLoading } = useQuery({
    queryKey: ["ips"],
    queryFn: () => api.get<IPAddress[]>("/api/v1/ips"),
    refetchInterval: 20_000,
  });

  const { data: networks } = useQuery({
    queryKey: ["networks"],
    queryFn: () => api.get<Network[]>("/api/v1/networks"),
  });

  const { data: nodes } = useQuery({
    queryKey: ["nodes"],
    queryFn: () => api.get<NodeInfo[]>("/api/v1/nodes"),
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["ips"] });

  const addIps = useMutation({
    mutationFn: () =>
      api.post<{ added: number; skipped: string[] }>("/api/v1/ips", {
        addresses: bulk.split(/[\s,;]+/).filter(Boolean),
        gateway: gateway.trim() || undefined,
      }),
    onSuccess: (d) => {
      setNotice(`Added ${d.added} address(es)${d.skipped.length ? `, skipped duplicates: ${d.skipped.join(", ")}` : ""}.`);
      setError(null);
      setBulk("");
      invalidate();
    },
    onError: (e) => {
      setNotice(null);
      setError(e instanceof ApiError ? e.message : "Failed to add IPs.");
    },
  });

  const op = useMutation({
    mutationFn: ({ ip, action }: { ip: IPAddress; action: "reserve" | "release" }) =>
      api.post(`/api/v1/ips/${ip.id}/${action}`),
    onSuccess: invalidate,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed."),
  });

  const createNetwork = useMutation({
    mutationFn: () =>
      api.post("/api/v1/networks", {
        node_id: netForm.node_id,
        name: netForm.name.trim(),
        ipv4_subnet: netForm.ipv4_subnet.trim() || null,
        ipv6_subnet: netForm.ipv6_subnet.trim() || null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["networks"] });
      setError(null);
      setNetForm({ node_id: "", name: "", ipv4_subnet: "", ipv6_subnet: "" });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Failed to create network."),
  });

  const filtered = (ips ?? []).filter(
    (i) =>
      (!familyFilter || i.family === Number(familyFilter)) &&
      (!statusFilter || i.status === statusFilter),
  );

  return (
    <div className="animate-fade-up space-y-4">
      <div>
        <h1 className="font-display text-lg font-semibold tracking-tight">IP address pools</h1>
        <p className="text-xs text-cvx-faint">Manage allocatable addresses and per-node networks.</p>
      </div>

      {(error || notice) && (
        <p
          className={`rounded-md border px-3 py-2 text-xs ${
            error ? "border-cvx-danger/30 bg-cvx-danger/5 text-cvx-danger" : "border-emerald-500/30 bg-emerald-500/5 text-emerald-400"
          }`}
        >
          {error ?? notice}
        </p>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Add addresses" />
          <form
            className="space-y-3 p-4"
            onSubmit={(e) => {
              e.preventDefault();
              addIps.mutate();
            }}
          >
            <textarea
              value={bulk}
              onChange={(e) => setBulk(e.target.value)}
              rows={4}
              placeholder={"203.0.113.10\n203.0.113.11\n2001:db8::10"}
              className="input-base font-mono text-xs"
            />
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="stat-label mb-1 block">Gateway (optional)</label>
                <Input value={gateway} onChange={(e) => setGateway(e.target.value)} placeholder="203.0.113.1" />
              </div>
              <Button type="submit" variant="primary" disabled={addIps.isPending || !bulk.trim()}>
                Add
              </Button>
            </div>
            <p className="text-[11px] text-cvx-faint">One address per line (CIDR suffix allowed). Duplicates are skipped.</p>
          </form>
        </Card>

        <Card>
          <CardHeader title="Create network" />
          <form
            className="grid gap-3 p-4"
            onSubmit={(e) => {
              e.preventDefault();
              createNetwork.mutate();
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <Select required value={netForm.node_id} onChange={(e) => setNetForm({ ...netForm, node_id: e.target.value })}>
                <option value="">Select node…</option>
                {(nodes ?? []).map((n) => (
                  <option key={n.id} value={n.id}>{n.name}</option>
                ))}
              </Select>
              <Input required placeholder="Network name" value={netForm.name}
                onChange={(e) => setNetForm({ ...netForm, name: e.target.value })} />
              <Input placeholder="IPv4 subnet (e.g. 10.10.0.0/24)" value={netForm.ipv4_subnet}
                onChange={(e) => setNetForm({ ...netForm, ipv4_subnet: e.target.value })} />
              <Input placeholder="IPv6 subnet (optional)" value={netForm.ipv6_subnet}
                onChange={(e) => setNetForm({ ...netForm, ipv6_subnet: e.target.value })} />
            </div>
            <Button type="submit" variant="primary" disabled={createNetwork.isPending || !netForm.node_id}>
              Create network
            </Button>
          </form>
          {networks && networks.length > 0 && (
            <ul className="divide-y divide-cvx-border border-t border-cvx-border text-xs">
              {networks.map((n) => (
                <li key={n.id} className="flex items-center justify-between px-4 py-2">
                  <span className="font-mono">{n.name}</span>
                  <span className="text-cvx-faint">{n.type}{n.is_default ? " · default" : ""}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card>
        <CardHeader title={`Addresses (${filtered.length})`} />
        <div className="flex gap-2 border-b border-cvx-border px-4 py-2.5">
          <Select value={familyFilter} onChange={(e) => setFamilyFilter(e.target.value)} className="w-32">
            <option value="">All families</option>
            <option value="4">IPv4</option>
            <option value="6">IPv6</option>
          </Select>
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-40">
            <option value="">All statuses</option>
            <option value="available">Available</option>
            <option value="assigned">Assigned</option>
            <option value="reserved">Reserved</option>
          </Select>
        </div>
        {isLoading ? (
          <p className="px-4 py-8 text-center text-sm text-cvx-faint">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-cvx-faint">No addresses in the pool.</p>
        ) : (
          <div className="max-h-[50vh] overflow-y-auto scrollbar-thin">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-cvx-panel">
                <tr className="border-b border-cvx-border text-left text-[11px] uppercase tracking-wider text-cvx-faint">
                  <th className="px-4 py-2 font-medium">Address</th>
                  <th className="px-4 py-2 font-medium">Family</th>
                  <th className="px-4 py-2 font-medium">Gateway</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-cvx-border">
                {filtered.map((ip) => (
                  <tr key={ip.id} className="hover:bg-cvx-raised/40">
                    <td className="mono-data px-4 py-2">{ip.address}{ip.cidr != null ? `/${ip.cidr}` : ""}</td>
                    <td className="mono-data px-4 py-2 text-cvx-muted">v{ip.family}</td>
                    <td className="mono-data px-4 py-2 text-cvx-faint">{ip.gateway ?? "—"}</td>
                    <td className="px-4 py-2"><StatusBadge status={ip.status} /></td>
                    <td className="px-4 py-2 text-right">
                      {ip.status !== "assigned" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={op.isPending}
                          onClick={() => op.mutate({ ip, action: ip.status === "reserved" ? "release" : "reserve" })}
                        >
                          {ip.status === "reserved" ? "Release" : "Reserve"}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
