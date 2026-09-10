import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ErrorMessage } from "./ErrorMessage";

describe("ErrorMessage", () => {
  it("renders the detail text verbatim", () => {
    render(<ErrorMessage detail="sympy could not solve this. Try rephrasing." />);

    expect(screen.getByText("sympy could not solve this. Try rephrasing.")).toBeInTheDocument();
  });
});
