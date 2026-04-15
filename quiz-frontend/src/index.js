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
  palette: {
    mode: "dark", // 🔥 instant modern look
    primary: {
      main: "#6366f1"
    }
  }
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