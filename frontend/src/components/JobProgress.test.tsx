import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JobProgress } from "./JobProgress";
import type { ProgressLine } from "@/types";

describe("JobProgress", () => {
  it("renders the description for each completed node, in order", () => {
    const progress: ProgressLine[] = [
      { node: "classifier", status: "done", detail: null, video: null },
      { node: "solver", status: "done", detail: null, video: null },
    ];

    render(<JobProgress progress={progress} />);

    expect(screen.getByText("Identifying the topic and difficulty")).toBeInTheDocument();
    expect(screen.getByText("Solving the problem step by step")).toBeInTheDocument();
    expect(screen.queryByText("classifier")).not.toBeInTheDocument();
    expect(screen.queryByText("solver")).not.toBeInTheDocument();
  });

  it("renders nothing extra when progress is empty", () => {
    render(<JobProgress progress={[]} />);

    expect(screen.queryByText(/./)).not.toBeInTheDocument();
  });

  it("falls back to the raw node name for an unknown node, without crashing", () => {
    const progress: ProgressLine[] = [
      { node: "some_future_node", status: "done", detail: null, video: null },
    ];

    render(<JobProgress progress={progress} />);

    expect(screen.getByText("some_future_node")).toBeInTheDocument();
  });

  it("shows an error node's step as errored", () => {
    const progress: ProgressLine[] = [
      { node: "classifier", status: "done", detail: null, video: null },
      { node: "solver", status: "error", detail: "sympy could not solve this.", video: null },
    ];

    render(<JobProgress progress={progress} />);

    const errorLabel = screen.getByText("Solving the problem step by step");
    expect(errorLabel.closest(".Mui-error")).not.toBeNull();
  });
});
