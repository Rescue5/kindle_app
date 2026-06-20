export const tokens = {
  color: {
    bg: "hsl(var(--background))",
    panel: "hsl(var(--panel))",
    panelRaised: "hsl(var(--panel-raised))",
    line: "hsl(var(--line))",
    text: "hsl(var(--foreground))",
    muted: "hsl(var(--muted-foreground))",
    accent: "hsl(var(--accent))",
    success: "hsl(var(--success))",
    warning: "hsl(var(--warning))",
    danger: "hsl(var(--destructive))",
  },
  radius: {
    xs: "6px",
    sm: "8px",
    md: "10px",
    lg: "14px",
  },
  spacing: {
    shell: "14px",
    panel: "18px",
    row: "10px",
  },
  motion: {
    fast: "140ms cubic-bezier(0.2, 0, 0, 1)",
    base: "220ms cubic-bezier(0.2, 0, 0, 1)",
    spring: { type: "spring", stiffness: 420, damping: 34, mass: 0.8 },
  },
} as const;
