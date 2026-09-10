import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  it("shows which theme is active and calls onToggle when clicked", async () => {
    const onToggle = vi.fn();
    render(<ThemeToggle theme="dark" onToggle={onToggle} />);

    await userEvent.click(screen.getByRole("button", { name: /switch to light/i }));

    expect(onToggle).toHaveBeenCalled();
  });
});
