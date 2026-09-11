import Stepper from "@mui/material/Stepper";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
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
  const activeStep = progress.length - 1;
  return (
    <Stepper activeStep={activeStep} orientation="vertical">
      {progress.map((line, index) => (
        <Step key={`${line.node}-${index}`} completed={line.status === "done"}>
          <StepLabel error={line.status === "error"}>
            {(line.node && NODE_DESCRIPTIONS[line.node]) || line.node}
          </StepLabel>
        </Step>
      ))}
    </Stepper>
  );
}
