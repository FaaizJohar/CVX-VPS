import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
}

const variants: Record<Variant, string> = {
  primary:
    "bg-cvx-accent text-white hover:bg-cvx-accent-hover disabled:hover:bg-cvx-accent",
  ghost: "text-cvx-muted hover:text-cvx-text hover:bg-cvx-raised",
  danger:
    "border border-cvx-danger/40 text-cvx-danger hover:bg-cvx-danger/10",
  outline:
    "border border-cvx-border-strong text-cvx-text hover:border-cvx-border-strong hover:bg-cvx-raised",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-4 text-sm",
};

export function Button({ variant = "outline", size = "md", className = "", children, ...rest }: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md font-medium
        transition-colors disabled:cursor-not-allowed disabled:opacity-40
        focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cvx-accent/60
        ${variants[variant]} ${sizes[size]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
