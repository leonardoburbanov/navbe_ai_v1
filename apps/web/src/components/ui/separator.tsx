import { cn } from "@/lib/utils";
import { Separator as SeparatorPrimitive } from "@base-ui/react/separator";
import type * as React from "react";

type SeparatorProps = React.ComponentProps<typeof SeparatorPrimitive>;

/** Horizontal or vertical divider. */
function Separator({
  className,
  orientation = "horizontal",
  ...props
}: SeparatorProps) {
  return (
    <SeparatorPrimitive
      orientation={orientation}
      className={cn(
        "shrink-0 bg-border",
        orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
        className,
      )}
      {...props}
    />
  );
}

export { Separator };
