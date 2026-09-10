import { CheckCircle2 } from "lucide-react";
import type { ProgressLine } from "@/types";

interface JobProgressProps {
  progress: ProgressLine[];
}

export function JobProgress({ progress }: JobProgressProps) {
  return (
    <ul className="flex flex-col gap-1 text-sm">
      {progress.map((line) => (
        <li key={line.node} className="flex items-center gap-2">
          <CheckCircle2 size={14} aria-hidden className="text-muted" />
          {line.node}
        </li>
      ))}
    </ul>
  );
}
