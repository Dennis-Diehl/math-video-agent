import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProblemForm } from "./ProblemForm";

describe("ProblemForm", () => {
  it("calls onSubmit with the typed problem", async () => {
    const onSubmit = vi.fn();
    render(<ProblemForm onSubmit={onSubmit} />);

    await userEvent.type(screen.getByLabelText(/problem/i), "Solve x^2 - 4 = 0");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(onSubmit).toHaveBeenCalledWith("Solve x^2 - 4 = 0");
  });

  it("does not submit an empty problem", async () => {
    const onSubmit = vi.fn();
    render(<ProblemForm onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables the input once a problem has been submitted", () => {
    render(<ProblemForm onSubmit={vi.fn()} disabled />);

    expect(screen.getByLabelText(/problem/i)).toBeDisabled();
  });
});
