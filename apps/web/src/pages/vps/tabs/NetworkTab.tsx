import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { VPS } from "@/types";
import { Card, CardHeader } from "@/components/ui/Card";

interface LiveState {
  reachable: boolean;
  ips?: Record<string, string>;
}

export default function NetworkTab({ vps }: { vps: VPS }) {
  const { data: live } = useQuery({
    queryKey: ["vps", vps.id, "state"],
    queryFn: () => api.get<LiveState>(`/api/v1/vps/${vps.id}/state`),
    refetchInterval: 20_000,
  });

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader title="Addressing" />
        <dl className="divide-y divide-cvx-border text-sm">
          {[
            ["IPv4 (assigned)", vps.ipv4 ?? "DHCP"],
            ["IPv6 (assigned)", vps.ipv6 ?? "—"],
            ["MAC address", vps.mac_address ?? "—"],
            ["Network", vps.network_name ?? "default bridge"],
            ["DNS servers", vps.dns_servers.length ? vps.dns_servers.join(", ") : "node default"],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-4 px-4 py-2.5">
              <dt className="text-cvx-faint">{k}</dt>
              <dd className="mono-data break-all text-right">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card>
        <CardHeader title="Live interfaces" />
        {!live?.reachable ? (
          <p className="px-4 py-8 text-center text-sm text-cvx-faint">
            Node unreachable or VPS stopped.
          </p>
        ) : Object.keys(live.ips ?? {}).length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-cvx-faint">No interfaces reported.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cvx-border text-left text-[11px] uppercase tracking-wider text-cvx-faint">
                <th className="px-4 py-2 font-medium">Interface</th>
                <th className="px-4 py-2 font-medium">Address</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cvx-border">
              {Object.entries(live.ips ?? {}).map(([iface, ip]) => (
                <tr key={iface}>
                  <td className="mono-data px-4 py-2">{iface}</td>
                  <td className="mono-data px-4 py-2 text-cvx-muted">{ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card className="xl:col-span-2">
        <CardHeader title="Firewall" />
        <p className="px-4 py-3 text-xs leading-relaxed text-cvx-muted">
          Host-level firewall management is intentionally not exposed per-VPS in CVX V1.
          Manage firewall rules inside the VPS (e.g. nftables/ufw) via the terminal, or at the
          node level through your infrastructure policy. This avoids granting the panel
          host-network control that could affect other tenants.
        </p>
      </Card>
    </div>
  );
}
