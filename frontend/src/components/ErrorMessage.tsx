interface ErrorMessageProps {
  detail: string;
}

export function ErrorMessage({ detail }: ErrorMessageProps) {
  return (
    <div role="alert" className="alert-error rounded border px-3 py-2">
      {detail}
    </div>
  );
}
