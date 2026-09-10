interface ErrorMessageProps {
  detail: string;
}

export function ErrorMessage({ detail }: ErrorMessageProps) {
  return (
    <div role="alert" className="alert-error rounded-xl border px-3 py-2 shadow-sm">
      {detail}
    </div>
  );
}
