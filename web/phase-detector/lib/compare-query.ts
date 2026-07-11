const MAX_TICKERS = 5;

export function parseCompareTickers(raw: string | string[] | null | undefined): string[] {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (!value) return [];
  return Array.from(
    new Set(
      value
        .split(",")
        .map((ticker) => ticker.trim().toUpperCase())
        .filter(
          (ticker) =>
            ticker.length > 0 && ticker.length <= 10 && /^[A-Z0-9.-]+$/.test(ticker),
        ),
    ),
  ).slice(0, MAX_TICKERS);
}
