import type { ButtonHTMLAttributes, ReactNode } from "react";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  size?: "sm" | "md";
  variant?: "ghost" | "outline";
}

export function IconButton({ size = "md", variant = "ghost", className = "", children, ...rest }: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center rounded-md transition-colors
        focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cvx-accent/60
        disabled:cursor-not-allowed disabled:opacity-40
        ${size === "sm" ? "h-7 w-7 p-1" : "h-8 w-8 p-1.5"}
        ${variant === "ghost"
          ? "text-cvx-muted hover:bg-cvx-raised hover:text-cvx-text"
          : "border border-cvx-border text-cvx-muted hover:border-cvx-border-strong hover:text-cvx-text"
        }
        ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
