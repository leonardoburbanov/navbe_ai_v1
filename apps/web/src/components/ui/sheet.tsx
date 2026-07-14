import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { XIcon } from "lucide-react";
import type * as React from "react";
import { useEffect } from "react";

type SheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
};

/** Controlled left drawer sheet (shadcn-style, no portal lib). */
function Sheet({ open, onOpenChange, children }: SheetProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div className="pointer-events-none fixed inset-0 z-40 flex">
      <button
        type="button"
        aria-label="Close sheet"
        className="pointer-events-auto flex-1 cursor-pointer border-0 bg-slate-900/25"
        onClick={() => onOpenChange(false)}
      />
      <aside className="pointer-events-auto order-first flex h-full w-[min(560px,92vw)] flex-col border-r bg-card text-card-foreground shadow-xl">
        {children}
      </aside>
    </div>
  );
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("flex flex-col gap-2 border-b p-4", className)}
      {...props}
    />
  );
}

function SheetTitle({ className, ...props }: React.ComponentProps<"h2">) {
  return <h2 className={cn("text-base font-semibold", className)} {...props} />;
}

function SheetDescription({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p
      className={cn("font-mono text-xs text-muted-foreground", className)}
      {...props}
    />
  );
}

function SheetClose({ onClick }: { onClick: () => void }) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="shrink-0"
      onClick={onClick}
      aria-label="Close"
    >
      <XIcon />
    </Button>
  );
}

function SheetBody({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div className={cn("flex-1 overflow-auto p-4", className)} {...props} />
  );
}

export {
  Sheet,
  SheetBody,
  SheetClose,
  SheetDescription,
  SheetHeader,
  SheetTitle,
};
