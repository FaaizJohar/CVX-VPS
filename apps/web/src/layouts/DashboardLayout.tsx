import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth, useIsAdmin } from "@/lib/auth";
import { Spinner } from "@/components/ui/Loading";
import { CommandPalette } from "@/components/ui/CommandPalette";

const mainNav = [
  { to: "/app", label: "Overview", end: true },
  { to: "/app/vps", label: "VPS", end: false },
];

const adminNav = [
  { to: "/app/admin/nodes", label: "Nodes" },
  { to: "/app/admin/images", label: "Images" },
  { to: "/app/admin/ips", label: "IP Addresses" },
  { to: "/app/admin/users", label: "Users" },
  { to: "/app/admin/logs", label: "Logs" },
  { to: "/app/admin/apikeys", label: "API Keys" },
];

function NavItem({ to, label, end }: { to: string; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `block rounded-md px-3 py-2 text-sm transition-colors ${
          isActive
            ? "bg-cvx-raised text-cvx-text"
            : "text-cvx-muted hover:bg-cvx-raised/60 hover:text-cvx-text"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export function DashboardLayout() {
  const { user, loading, logout } = useAuth();
  const isAdmin = useIsAdmin();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (!user) {
    void navigate("/login");
    return null;
  }

  const sidebar = (
    <nav className="flex h-full flex-col gap-6 overflow-y-auto p-4 scrollbar-thin">
      <NavLink to="/app" className="flex items-center gap-2 px-2 pt-1">
        <span className="font-mono text-lg font-semibold tracking-tight text-cvx-text">CVX</span>
        <span className="rounded border border-cvx-border px-1 py-0.5 text-[9px] uppercase tracking-widest text-cvx-faint">
          v1.1
        </span>
      </NavLink>

      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        aria-label="Open command palette"
        className="flex items-center justify-between rounded-md border border-cvx-border bg-cvx-raised/60 px-3 py-2 text-xs text-cvx-faint transition-colors hover:border-cvx-border-strong hover:text-cvx-muted"
      >
        <span>Search…</span>
        <kbd className="rounded border border-cvx-border px-1 font-mono text-[10px]">⌘K</kbd>
      </button>

      <div className="space-y-1">
        <p className="px-3 pb-1 text-[10px] font-medium uppercase tracking-[0.16em] text-cvx-faint">
          Infrastructure
        </p>
        {mainNav.map((n) => (
          <NavItem key={n.to} {...n} />
        ))}
      </div>

      {isAdmin && (
        <div className="space-y-1">
          <p className="px-3 pb-1 text-[10px] font-medium uppercase tracking-[0.16em] text-cvx-faint">
            Administration
          </p>
          {adminNav.map((n) => (
            <NavItem key={n.to} {...n} />
          ))}
        </div>
      )}

      <div className="mt-auto space-y-1 border-t border-cvx-border pt-4">
        <div className="px-3 pb-2">
          <p className="truncate text-sm text-cvx-text">{user.name || user.email}</p>
          <p className="text-xs uppercase tracking-wider text-cvx-faint">{user.role}</p>
        </div>
        <button
          onClick={() => void logout().then(() => navigate("/login"))}
          className="w-full rounded-md px-3 py-2 text-left text-sm text-cvx-muted hover:bg-cvx-raised hover:text-cvx-text"
        >
          Sign out
        </button>
      </div>
    </nav>
  );

  return (
    <div className="flex h-full">
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />

      {/* Desktop sidebar */}
      <aside className="hidden w-60 shrink-0 border-r border-cvx-border bg-cvx-panel lg:block">
        {sidebar}
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-64 border-r border-cvx-border bg-cvx-panel">
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile topbar */}
        <header className="flex items-center justify-between border-b border-cvx-border bg-cvx-panel px-4 py-3 lg:hidden">
          <button onClick={() => setMobileOpen(true)} aria-label="Open menu" className="rounded-md p-1.5 hover:bg-cvx-raised">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 4.5h14M2 9h14M2 13.5h14" />
            </svg>
          </button>
          <span className="font-mono font-semibold">CVX</span>
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            aria-label="Search"
            className="rounded-md p-1.5 hover:bg-cvx-raised"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="7" cy="7" r="4.5" />
              <path d="M10.5 10.5L14 14" />
            </svg>
          </button>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6 scrollbar-thin">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
