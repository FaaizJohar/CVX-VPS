import { useEffect, useRef, useState } from "react";
import type { VPS } from "@/types";
import { Button } from "@/components/ui/Button";

export default function TerminalTab({ vps }: { vps: VPS }) {
  const id = vps.id;
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<import("@xterm/xterm").Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    let disposed = false;
    let fit: import("@xterm/addon-fit").FitAddon | null = null;
    const cleanupFns: Array<() => void> = [];

    async function setup() {
      const [{ Terminal }, { FitAddon }, { WebLinksAddon }] = await Promise.all([
        import("@xterm/xterm"),
        import("@xterm/addon-fit"),
        import("@xterm/addon-web-links"),
      ]);
      if (disposed || !containerRef.current) return;

      const term = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: "'JetBrains Mono', 'SF Mono', Consolas, monospace",
        theme: {
          background: "#0a0b0d",
          foreground: "#e6e8eb",
          cursor: "#3d7bfd",
          selectionBackground: "#3d7bfd44",
          black: "#0a0b0d",
          brightBlack: "#5b616c",
        },
      });
      fit = new FitAddon();
      term.loadAddon(fit);
      term.loadAddon(new WebLinksAddon());
      term.open(containerRef.current);
      fit.fit();
      termRef.current = term;
      term.focus();

      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${window.location.host}/api/v1/vps/${id}/console?cols=${term.cols}&rows=${term.rows}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        term.writeln("\x1b[90m── CVX secure console ──────────────────────────\x1b[0m");
      };
      ws.onmessage = (ev) => {
        if (typeof ev.data === "string") term.write(ev.data);
        else term.write(new Uint8Array(ev.data));
      };
      ws.onclose = (ev) => {
        setConnected(false);
        term.writeln(
          ev.code === 4401
            ? "\r\n\x1b[31mSession unauthorized.\x1b[0m"
            : "\r\n\x1b[90mSession closed.\x1b[0m",
        );
      };
      ws.onerror = () => setConnected(false);

      term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "input", data }));
        }
      });

      const resizeHandler = () => {
        if (!fit) return;
        fit.fit();
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
        }
      };
      window.addEventListener("resize", resizeHandler);
      cleanupFns.push(() => window.removeEventListener("resize", resizeHandler));
    }

    void setup();

    return () => {
      disposed = true;
      for (const fn of cleanupFns) fn();
      wsRef.current?.close();
      termRef.current?.dispose();
      termRef.current = null;
    };
  }, [id]);

  function reconnect() {
    wsRef.current?.close();
    termRef.current?.dispose();
    // Remount by toggling a key is overkill; simplest robust path:
    window.location.reload();
  }

  return (
    <div className={fullscreen ? "fixed inset-0 z-50 bg-cvx-bg p-2" : ""}>
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-cvx-faint">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`} />
          {connected ? "Connected" : "Disconnected"}
        </div>
        <div className="flex gap-2">
          {!connected && <Button size="sm" onClick={reconnect}>Reconnect</Button>}
          <Button size="sm" onClick={() => setFullscreen(!fullscreen)}>
            {fullscreen ? "Exit fullscreen" : "Fullscreen"}
          </Button>
        </div>
      </div>
      <div
        ref={containerRef}
        className="h-[62vh] overflow-hidden rounded-lg border border-cvx-border p-1"
        style={{ minHeight: 320 }}
      />
    </div>
  );
}
