import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const alertVariants = cva("relative w-full rounded-lg border p-4 text-sm [&>svg]:size-5 [&>svg]:shrink-0 flex gap-3", {
  variants: {
    variant: {
      default: "bg-card text-card-foreground",
      destructive: "border-destructive/60 text-foreground [&>svg]:text-destructive",
      warning: "border-warning/60 text-foreground [&>svg]:text-warning",
      success: "border-success/60 text-foreground [&>svg]:text-success",
      info: "border-info/60 text-foreground [&>svg]:text-info",
    },
  },
  defaultVariants: { variant: "default" },
});

const Alert = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>>(
  ({ className, variant, role = "status", ...props }, ref) => (
    <div ref={ref} role={role} className={cn(alertVariants({ variant }), className)} {...props} />
  ),
);
Alert.displayName = "Alert";

const AlertTitle = ({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) => (
  <p className={cn("mb-1 font-semibold leading-none", className)} {...props} />
);
const AlertDescription = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("text-sm leading-relaxed [&_p]:leading-relaxed", className)} {...props} />
);

export { Alert, AlertTitle, AlertDescription };
