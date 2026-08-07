import { createRoot } from "react-dom/client";
import { StrictMode } from "react";
import App from "./App";

document.documentElement.dataset.theme = "dark";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
