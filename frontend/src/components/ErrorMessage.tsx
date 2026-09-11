import Alert from "@mui/material/Alert";

interface ErrorMessageProps {
  detail: string;
}

export function ErrorMessage({ detail }: ErrorMessageProps) {
  return <Alert severity="error">{detail}</Alert>;
}
