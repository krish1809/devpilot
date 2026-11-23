import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        surface: {
          DEFAULT: "hsl(var(--surface))",
          raised: "hsl(var(--surface-raised))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        border: "hsl(var(--border))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        accent: "hsl(var(--accent))",
        glow: "hsl(var(--glow))",
        success: { DEFAULT: "hsl(var(--success))", fg: "hsl(var(--success-fg))" },
        warning: { DEFAULT: "hsl(var(--warning))", fg: "hsl(var(--warning-fg))" },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          fg: "hsl(var(--destructive-fg))",
        },
        info: { DEFAULT: "hsl(var(--info))", fg: "hsl(var(--info-fg))" },
        ring: "hsl(var(--ring))",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      maxWidth: {
        page: "72rem",
      },
      boxShadow: {
        glow: "0 0 0 1px hsl(var(--primary) / 0.25), 0 8px 30px -8px hsl(var(--glow) / 0.55)",
        panel: "0 1px 0 0 hsl(var(--foreground) / 0.04) inset, 0 24px 48px -24px rgb(0 0 0 / 0.5)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
