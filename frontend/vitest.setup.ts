import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement matchMedia. Default every test to "desktop" (no
// media query matches) so components using useIsMobile (e.g. AppShell) don't
// crash when they don't care about mobile/desktop behavior specifically;
// tests that do care (useIsMobile.test.ts) stub it themselves per-test via
// vi.stubGlobal, which overrides this default for the duration of that test.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
