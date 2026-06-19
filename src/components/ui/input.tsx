import * as React from "react";
import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "h-11 w-full rounded-2xl border border-white/10 bg-white/[0.055] px-4 text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground focus:border-cyan-300/40 focus:bg-white/[0.075] focus:ring-4 focus:ring-cyan-300/10",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
