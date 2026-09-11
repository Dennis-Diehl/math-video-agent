import { createTheme, type PaletteMode } from "@mui/material/styles";

export function getTheme(mode: PaletteMode) {
  return createTheme({
    palette: { mode },
  });
}
