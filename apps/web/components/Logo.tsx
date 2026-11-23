import { cn } from "@/lib/utils";

/**
 * The DevPilot mark: a pull-request glyph (a branch merging back) on a violet
 * gradient tile. Decorative; callers provide the accessible name.
 */
export function Logo({
  size = "md",
  className,
}: {
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const box = {
    sm: "h-5 w-5 rounded-[5px]",
    md: "h-7 w-7 rounded-md",
    lg: "h-11 w-11 rounded-xl",
  }[size];
  const icon = { sm: 12, md: 16, lg: 24 }[size];
  return (
    <span
      aria-hidden
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center",
        "bg-[linear-gradient(135deg,hsl(var(--primary)),hsl(var(--accent)))]",
        "shadow-[inset_0_1px_0_0_rgb(255_255_255/0.35),0_4px_16px_-4px_hsl(var(--glow)/0.6)]",
        box,
        className,
      )}
    >
      <svg
        width={icon}
        height={icon}
        viewBox="0 0 24 24"
        fill="none"
        stroke="hsl(240 10% 4%)"
        strokeWidth={2.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="6" cy="6" r="2.5" />
        <circle cx="6" cy="18" r="2.5" />
        <circle cx="18" cy="18" r="2.5" />
        <path d="M6 8.5v7" />
        <path d="M18 15.5V11a4 4 0 0 0-4-4h-3.5" />
        <path d="m12.5 4.5-2.5 2.5 2.5 2.5" />
      </svg>
    </span>
  );
}
