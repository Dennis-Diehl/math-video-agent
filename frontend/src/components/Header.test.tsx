import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Header } from "./Header";

describe("Header", () => {
  it("renders the app title", () => {
    render(<Header theme="dark" onToggleTheme={vi.fn()} />);

    expect(screen.getByText("Math Video Agent")).toBeInTheDocument();
  });

  it("renders the theme toggle and forwards clicks", async () => {
    const onToggleTheme = vi.fn();
    render(<Header theme="dark" onToggleTheme={onToggleTheme} />);

    await userEvent.click(screen.getByRole("button", { name: /switch to light/i }));

    expect(onToggleTheme).toHaveBeenCalled();
  });
});
