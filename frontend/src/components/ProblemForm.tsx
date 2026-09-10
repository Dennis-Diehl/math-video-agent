"use client";

import { useState, type FormEvent } from "react";

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
    <form onSubmit={handleSubmit} className="flex gap-2">
      <label htmlFor="problem" className="sr-only">
        Math problem
      </label>
      <input
        id="problem"
        value={problem}
        onChange={(e) => setProblem(e.target.value)}
        disabled={disabled}
        placeholder="Enter a math problem..."
        className="flex-1 rounded-xl border border-[var(--border)] px-3 py-2 shadow-sm transition-colors disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={disabled}
        className="btn-primary rounded-xl px-4 py-2 shadow-sm transition-colors transition-[filter] hover:brightness-110 disabled:opacity-50"
      >
        Send
      </button>
    </form>
  );
}
