import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cvx: {
          bg: "#0a0b0d",
          panel: "#101216",
          raised: "#15181d",
          border: "#1e2229",
          "border-strong": "#2a2f38",
          text: "#e6e8eb",
          muted: "#8b919c",
          faint: "#5b616c",
          accent: "#3d7bfd",
          "accent-hover": "#5c90ff",
          ok: "#34d399",
          warn: "#fbbf24",
          danger: "#f87171",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "Geist",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
        display: [
          "Space Grotesk",
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "SF Mono",
          "Cascadia Code",
          "Consolas",
          "monospace",
        ],
      },
      spacing: {
        "4.5": "1.125rem",
        "13": "3.25rem",
        "15": "3.75rem",
        "18": "4.5rem",
      },
      transitionProperty: {
        "sidebar": "width, padding, margin",
      },
    },
  },
  plugins: [],
} satisfies Config;
