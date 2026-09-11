"use client";

import { useState, type FormEvent } from "react";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";

interface ProblemFormProps {
  onSubmit: (problem: string) => void;
  disabled?: boolean;
}

export function ProblemForm({ onSubmit, disabled }: ProblemFormProps) {
  const [problem, setProblem] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = problem.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }

  return (
    <Box component="form" onSubmit={handleSubmit} sx={{ display: "flex", gap: 1 }}>
      <TextField
        id="problem"
        label="Math problem"
        value={problem}
        onChange={(e) => setProblem(e.target.value)}
        disabled={disabled}
        placeholder="Enter a math problem..."
        fullWidth
        size="small"
      />
      <Button type="submit" variant="contained" disabled={disabled} aria-label="Send" sx={{ minWidth: 96 }}>
        {disabled ? <CircularProgress size={20} color="inherit" /> : "Send"}
      </Button>
    </Box>
  );
}
