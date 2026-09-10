interface VideoPlayerProps {
  src: string;
}

export function VideoPlayer({ src }: VideoPlayerProps) {
  return (
    <video data-testid="video-player" controls className="w-full max-w-full rounded">
      <source src={src} type="video/mp4" />
    </video>
  );
}
