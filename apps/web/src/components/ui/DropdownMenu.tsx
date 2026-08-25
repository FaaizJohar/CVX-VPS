import { useCallback, useEffect, useRef, useState } from "react";

export interface DropdownAction {
  label: string;
  icon?: React.ReactNode;
  danger?: boolean;
  disabled?: boolean;
  separator?: boolean;
  onClick?: () => void;
}

interface Props {
  trigger: React.ReactNode;
  actions: DropdownAction[];
  align?: "left" | "right";
}

export function DropdownMenu({ trigger, actions, align = "right" }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const [activeIdx, setActiveIdx] = useState(-1);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
      const actionable = actions.filter((a) => !a.separator && !a.disabled);
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, actionable.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && activeIdx >= 0) {
        e.preventDefault();
        actionable[activeIdx]?.onClick?.();
        close();
      }
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close, actions, activeIdx]);

  useEffect(() => {
    if (open) setActiveIdx(-1);
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      <div onClick={() => setOpen((v) => !v)}>{trigger}</div>
      {open && (
        <div
          role="menu"
          className={`dropdown-panel animate-fade-in ${align === "left" ? "left-0" : "right-0"}`}
        >
          {actions.map((a, i) => {
            if (a.separator) return <div key={`sep-${i}`} className="dropdown-separator" />;
            return (
              <button
                key={a.label}
                type="button"
                role="menuitem"
                disabled={a.disabled}
                className={`${a.danger ? "dropdown-item-danger" : "dropdown-item"} ${
                  !a.disabled ? "opacity-100" : "opacity-40 cursor-not-allowed"
                }`}
                onClick={() => {
                  a.onClick?.();
                  close();
                }}
              >
                {a.icon && <span className="shrink-0">{a.icon}</span>}
                {a.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
