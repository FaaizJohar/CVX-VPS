import { useEffect } from "react";
import { Button } from "@/components/ui/Button";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: Props) {

  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      const btn = document.querySelector<HTMLButtonElement>("[data-confirm-btn]");
      btn?.focus();
    }, 0);
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, busy, onClose]);

  if (!open) return null;

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-[2px]" onClick={busy ? undefined : onClose} />
      <div className="panel animate-fade-up relative w-full max-w-sm p-5 shadow-2xl shadow-black/40">
        <h2 id="confirm-title" className="text-sm font-semibold text-cvx-text">
          {title}
        </h2>
        <p className="mt-2 text-xs leading-relaxed text-cvx-muted">{message}</p>
        <div className="mt-5 flex justify-end gap-2">
          <Button size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant={danger ? "danger" : "primary"}
            onClick={onConfirm}
            disabled={busy}
            data-confirm-btn
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
