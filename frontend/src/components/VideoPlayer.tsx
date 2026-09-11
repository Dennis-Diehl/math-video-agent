import Paper from "@mui/material/Paper";

interface VideoPlayerProps {
  src: string;
}

export function VideoPlayer({ src }: VideoPlayerProps) {
  return (
    <Paper elevation={1} sx={{ overflow: "hidden", borderRadius: 2 }}>
      <video data-testid="video-player" controls style={{ width: "100%", display: "block" }}>
        <source src={src} type="video/mp4" />
      </video>
    </Paper>
  );
}
