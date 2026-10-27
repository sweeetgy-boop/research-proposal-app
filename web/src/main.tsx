import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router";
import "./index.css";
import App from "./App";
import { ToastProvider } from "@/components/ui/toast";
import { isApiError } from "@/api/client";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, err) => !(isApiError(err) && err.status < 500) && count < 2,
      refetchOnWindowFocus: false,
      staleTime: 5_000,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <App />
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
