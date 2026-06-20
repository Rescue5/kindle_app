import * as React from "react";
import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "h-9 w-full rounded-[10px] border border-border bg-input px-3 text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground hover:border-primary/25 focus:border-primary/50 focus:ring-2 focus:ring-primary/12 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
