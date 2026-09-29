"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Remove the access token stored by earlier frontend releases.
    sessionStorage.removeItem("habicapital_access_token");
  }, []);
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: {
    staleTime: 10_000, retry: false, refetchOnWindowFocus: true,
  }, mutations: { retry: false } } }));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
