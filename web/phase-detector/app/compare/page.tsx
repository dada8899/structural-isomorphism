import CompareClient from "@/components/CompareClient";
import { parseCompareTickers } from "@/lib/compare-query";
import { loadServerCompany } from "@/lib/server-api";
import type { Company } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ComparePage({
  searchParams,
}: {
  searchParams: { tickers?: string | string[] };
}) {
  const tickers = parseCompareTickers(searchParams.tickers);
  const results = await Promise.allSettled(
    tickers.map((ticker) => loadServerCompany(ticker)),
  );
  const companies: Company[] = [];
  const errors: Record<string, string> = {};
  results.forEach((result, index) => {
    const ticker = tickers[index];
    if (result.status === "fulfilled") companies.push(result.value);
    else {
      errors[ticker] =
        result.reason instanceof Error ? result.reason.message : "fetch failed";
    }
  });
  return (
    <CompareClient
      key={tickers.join(",")}
      tickers={tickers}
      companies={companies}
      errors={errors}
    />
  );
}
