// import React from "react";
// import ReactDOM from "react-dom/client";
// import App from "./App";

// const root = ReactDOM.createRoot(document.getElementById("root"));
// root.render(
//   <React.StrictMode>
//     <App />
//   </React.StrictMode>
// );
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./App.css"; // or "./App.css"

// ✅ MUI imports
import { ThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";

// ✅ Create theme
const theme = createTheme({
  typography: {
    fontFamily: '"IBM Plex Sans", "Segoe UI", "Helvetica Neue", sans-serif',
    h4: { fontWeight: 700, letterSpacing: -0.3 },
    h5: { fontWeight: 700, letterSpacing: -0.2 },
    h6: { fontWeight: 650 },
  },
  palette: {
    mode: "dark",
    primary: {
      main: "#0ea5a4",
      dark: "#0b7f7e",
      light: "#2dd4bf",
    },
    secondary: {
      main: "#f59e0b",
      dark: "#b45309",
      light: "#fbbf24",
    },
    background: {
      default: "#0f172a",
      paper: "#111827",
    },
    text: {
      primary: "#f9fafb",
      secondary: "#cbd5e1",
    },
    divider: "#334155",
    error: {
      main: "#ef4444",
    },
    success: {
      main: "#22c55e",
    },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          background:
            "radial-gradient(1200px 800px at 10% -20%, rgba(14,165,164,0.12) 0%, rgba(15,23,42,0) 50%), radial-gradient(900px 600px at 100% 0%, rgba(245,158,11,0.10) 0%, rgba(15,23,42,0) 45%), #0f172a",
        },
        a: {
          color: "#5eead4",
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: "#111827",
          border: "1px solid #334155",
          boxShadow: "0 12px 40px rgba(2, 6, 23, 0.32)",
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          backgroundColor: "rgba(15, 23, 42, 0.45)",
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: "#475569",
          },
          "&:hover .MuiOutlinedInput-notchedOutline": {
            borderColor: "#64748b",
          },
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
            borderColor: "#2dd4bf",
            borderWidth: 2,
          },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 650,
          "&.Mui-focusVisible": {
            outline: "2px solid #2dd4bf",
            outlineOffset: 2,
          },
        },
        outlined: {
          borderColor: "#475569",
          "&:hover": {
            borderColor: "#64748b",
            backgroundColor: "rgba(148,163,184,0.08)",
          },
        },
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: {
          color: "#cbd5e1",
          "&.Mui-focused": {
            color: "#99f6e4",
          },
        },
      },
    },
    MuiFormHelperText: {
      styleOverrides: {
        root: {
          color: "#94a3b8",
        },
      },
    },
    MuiLink: {
      styleOverrides: {
        root: {
          color: "#5eead4",
          textDecorationColor: "rgba(94, 234, 212, 0.55)",
          "&:hover": {
            textDecorationColor: "#5eead4",
          },
        },
      },
    },
    MuiCheckbox: {
      styleOverrides: {
        root: {
          color: "#94a3b8",
          "&.Mui-checked": {
            color: "#2dd4bf",
          },
        },
      },
    },
    MuiRadio: {
      styleOverrides: {
        root: {
          color: "#94a3b8",
          "&.Mui-checked": {
            color: "#2dd4bf",
          },
        },
      },
    },
  },
});

// const theme = createTheme({
//   palette: {
//     mode: "dark",
//     primary: {
//       main: "#6366f1"
//     },
//     background: {
//       default: "transparent" // 👈 important
//     }
//   }
// });

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>
);