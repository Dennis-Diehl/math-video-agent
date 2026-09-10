import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VideoPlayer } from "./VideoPlayer";

describe("VideoPlayer", () => {
  it("renders a video element with the given source and native controls", () => {
    render(<VideoPlayer src="http://localhost:8000/jobs/abc/video" />);

    const video = screen.getByTestId("video-player") as HTMLVideoElement;
    expect(video.querySelector("source")).toHaveAttribute(
      "src",
      "http://localhost:8000/jobs/abc/video",
    );
    expect(video).toHaveAttribute("controls");
  });

  it("renders no download button or link", () => {
    render(<VideoPlayer src="http://localhost:8000/jobs/abc/video" />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /download/i })).not.toBeInTheDocument();
  });
});
