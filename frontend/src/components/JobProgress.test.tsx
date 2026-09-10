import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JobProgress } from "./JobProgress";
import type { ProgressLine } from "@/types";

describe("JobProgress", () => {
  it("renders one line per completed node, in order", () => {
    const progress: ProgressLine[] = [
      { node: "classifier", status: "done", detail: null, video: null },
      { node: "solver", status: "done", detail: null, video: null },
    ];

    render(<JobProgress progress={progress} />);

    const items = screen.getAllByRole("listitem");
    expect(items.map((i) => i.textContent)).toEqual(["classifier", "solver"]);
  });

  it("renders nothing extra when progress is empty", () => {
    render(<JobProgress progress={[]} />);

    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });
});
