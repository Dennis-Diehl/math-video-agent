import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import { ThemeToggle } from "./ThemeToggle";

interface HeaderProps {
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export function Header({ theme, onToggleTheme }: HeaderProps) {
  return (
    <AppBar position="static" color="default" elevation={1}>
      <Toolbar variant="dense" sx={{ justifyContent: "space-between" }}>
        <Typography variant="subtitle2">Math Video Agent</Typography>
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </Toolbar>
    </AppBar>
  );
}
