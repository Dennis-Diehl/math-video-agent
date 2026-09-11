import { createTheme, type PaletteMode } from "@mui/material/styles";

export function getTheme(mode: PaletteMode) {
  return createTheme({
    palette: { mode },
    shape: { borderRadius: 10 },
    typography: {
      h6: { fontWeight: 600 },
      subtitle2: { fontWeight: 600 },
      overline: { fontWeight: 600, letterSpacing: 0.6 },
      button: { textTransform: "none", fontWeight: 600 },
    },
    components: {
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: { borderRadius: 10 },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: { backgroundImage: "none" },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: ({ theme }) => ({ boxShadow: "none", borderBottom: `1px solid ${theme.palette.divider}` }),
        },
      },
    },
  });
}
