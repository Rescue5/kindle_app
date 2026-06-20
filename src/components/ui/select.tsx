import * as React from "react";
import { cn } from "@/lib/utils";

export function Select({
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 rounded-[10px] border border-border bg-input px-3 text-sm text-foreground outline-none transition-all hover:border-primary/25 focus:border-primary/50 focus:ring-2 focus:ring-primary/12 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
