import { cn } from "@/lib/utils";

type Kind = "add" | "del" | "hunk" | "meta" | "ctx";

export function classifyLine(line: string): Kind {
  if (line.startsWith("+++") || line.startsWith("---")) return "meta";
  if (line.startsWith("diff ") || line.startsWith("index ")) return "meta";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "del";
  return "ctx";
}

const STYLES: Record<Kind, string> = {
  add: "bg-success/10 text-success-fg",
  del: "bg-destructive/10 text-destructive-fg",
  hunk: "bg-info/10 text-info-fg",
  meta: "font-semibold text-muted-foreground",
  ctx: "",
};

// Screen readers can't see the colors, so each changed line says what it is.
const SR_PREFIX: Partial<Record<Kind, string>> = { add: "added: ", del: "removed: " };

/** A unified diff with added/removed lines tinted (not just a wall of text). */
export function DiffView({ diff, className }: { diff: string; className?: string }) {
  const lines = diff.replace(/\n$/, "").split("\n");
  const added = lines.filter((l) => classifyLine(l) === "add").length;
  const removed = lines.filter((l) => classifyLine(l) === "del").length;
  return (
    <div className={cn("overflow-hidden rounded-md border border-border", className)}>
      <div className="flex items-center gap-3 border-b border-border bg-muted/60 px-3 py-1.5 text-xs">
        <span className="font-medium text-success-fg">+{added}</span>
        <span className="font-medium text-destructive-fg">−{removed}</span>
        <span className="text-muted-foreground">
          line{added + removed === 1 ? "" : "s"} changed
        </span>
      </div>
      <pre className="max-h-[28rem] overflow-auto bg-background py-2 font-mono text-xs leading-5">
        <code className="block w-max min-w-full">
          {lines.map((line, i) => {
            const kind = classifyLine(line);
            return (
              <span key={i} className={cn("block px-3", STYLES[kind])}>
                {SR_PREFIX[kind] && <span className="sr-only">{SR_PREFIX[kind]}</span>}
                {line || " "}
              </span>
            );
          })}
        </code>
      </pre>
    </div>
  );
}
