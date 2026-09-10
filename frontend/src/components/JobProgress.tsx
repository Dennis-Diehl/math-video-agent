import { motion } from "framer-motion";
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
      {/* No AnimatePresence here: steps are only ever appended, never removed
          or reordered (progress is a strictly-growing list from the backend),
          so there's no exit to animate — AnimatePresence exists to animate
          unmounts, which never happen in this list. */}
      {progress.map((line) => (
        <motion.li
          key={line.node}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="flex items-center gap-2"
        >
          <CheckCircle2 size={14} aria-hidden className="text-muted shrink-0" />
          <span>{(line.node && NODE_DESCRIPTIONS[line.node]) || line.node}</span>
        </motion.li>
      ))}
    </ul>
  );
}
