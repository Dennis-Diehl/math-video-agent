"use client";

import { useEffect, useState } from "react";

const BREAKPOINT = "(max-width: 767px)";

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window === "undefined" ? false : window.matchMedia(BREAKPOINT).matches,
  );

  useEffect(() => {
    const mql = window.matchMedia(BREAKPOINT);
    const listener = () => setIsMobile(mql.matches);
    mql.addEventListener("change", listener);
    return () => mql.removeEventListener("change", listener);
  }, []);

  return isMobile;
}
