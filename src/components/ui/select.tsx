import * as React from "react";
import { cn } from "@/lib/utils";

export function Select({
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-11 rounded-2xl border border-white/10 bg-white/[0.055] px-4 text-sm text-foreground outline-none transition-all focus:border-cyan-300/40 focus:ring-4 focus:ring-cyan-300/10",
        className,
      )}
      {...props}
    />
  );
}
