// Stubs for next/navigation in Storybook. Stories can override the
// pathname via `parameters.nextjs.navigation.pathname` — we read it off
// a window global that preview.ts populates.

const noop = () => {};

function getNav(): { pathname?: string; query?: Record<string, string> } {
  if (typeof window === "undefined") return {};
  return (window as unknown as { __SB_NAV__?: { pathname?: string; query?: Record<string, string> } }).__SB_NAV__ ?? {};
}

export function usePathname(): string {
  return getNav().pathname ?? "/";
}

export function useSearchParams(): URLSearchParams {
  const q = getNav().query ?? {};
  const params = new URLSearchParams();
  Object.entries(q).forEach(([k, v]) => params.set(k, String(v)));
  return params;
}

export function useRouter() {
  return {
    push: noop,
    replace: noop,
    back: noop,
    forward: noop,
    refresh: noop,
    prefetch: noop,
  };
}

export function useParams<T extends Record<string, string | string[]>>(): T {
  return {} as T;
}

export function useSelectedLayoutSegment(): string | null {
  return null;
}

export function useSelectedLayoutSegments(): string[] {
  return [];
}

export function redirect(_path: string): never {
  throw new Error(`[storybook] redirect(${_path}) called — not supported`);
}

export function notFound(): never {
  throw new Error("[storybook] notFound() called — not supported");
}
