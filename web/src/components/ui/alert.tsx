import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const alertVariants = cva("relative w-full rounded-lg border p-4 leading-relaxed text-sm [&>svg]:size-5 [&>svg]:shrink-0 flex gap-3", {
  variants: {
    variant: {
      default: "bg-card text-card-foreground",
      destructive: "border-destructive/40 bg-destructive-soft text-foreground [&>svg]:text-destructive-soft-foreground",
      warning: "border-warning/30 bg-apricot text-foreground [&>svg]:text-apricot-foreground",
      success: "border-success/30 bg-mint text-foreground [&>svg]:text-mint-foreground",
      info: "border-primary/25 bg-primary-soft text-foreground [&>svg]:text-primary-soft-foreground",
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
