import { CheckCircle2 } from "lucide-react";
import type { ProgressLine } from "@/types";

const NODE_DESCRIPTIONS: Record<string, string> = {
  classifier: "Identifying the topic and difficulty",
  solver: "Solving the problem step by step",
  scene_planner: "Splitting the solution into animation scenes",
  codegen: "Generating the animation code for each scene",
  executor: "Rendering the animations",
  tts: "Narrating the explanation",
  assembler: "Combining picture and narration into the final video",
};

interface JobProgressProps {
  progress: ProgressLine[];
}

export function JobProgress({ progress }: JobProgressProps) {
  return (
    <ul className="flex flex-col gap-1 text-sm">
      {progress.map((line) => (
        <li key={line.node} className="fade-in flex items-center gap-2">
          <CheckCircle2 size={14} aria-hidden className="text-muted shrink-0" />
          <span>{(line.node && NODE_DESCRIPTIONS[line.node]) || line.node}</span>
        </li>
      ))}
    </ul>
  );
}
