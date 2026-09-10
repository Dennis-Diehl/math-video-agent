import { ThemeToggle } from "./ThemeToggle";

interface HeaderProps {
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export function Header({ theme, onToggleTheme }: HeaderProps) {
  return (
    <header className="panel flex items-center justify-between border-b px-4 py-2 shadow-sm">
      <span className="text-sm font-medium">Math Video Agent</span>
      <ThemeToggle theme={theme} onToggle={onToggleTheme} />
    </header>
  );
}
