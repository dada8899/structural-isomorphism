import CompanyDetailClient from "@/components/CompanyDetailClient";
import { companyFromEws } from "@/lib/company-data";
import { loadServerCompany, loadServerEws } from "@/lib/server-api";
import type { Company, EwsResultFull } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function CompanyDetailPage({
  params,
}: {
  params: { ticker: string };
}) {
  const ticker = params.ticker.toUpperCase();
  if (!/^[A-Z0-9.-]{1,10}$/.test(ticker)) {
    return (
      <CompanyDetailClient
        ticker={ticker}
        company={null}
        ews={null}
        error="invalid ticker"
      />
    );
  }

  const [companyResult, ewsResult] = await Promise.allSettled([
    loadServerCompany(ticker),
    loadServerEws(ticker),
  ]);
  const ews: EwsResultFull | null =
    ewsResult.status === "fulfilled" ? ewsResult.value : null;
  let company: Company | null =
    companyResult.status === "fulfilled" ? companyResult.value : null;
  if (!company && ews) company = companyFromEws(ews);

  const error =
    company === null
      ? companyResult.status === "rejected" && companyResult.reason instanceof Error
        ? companyResult.reason.message
        : `company ${ticker} not found`
      : null;

  return (
    <CompanyDetailClient
      key={ticker}
      ticker={ticker}
      company={company}
      ews={ews}
      error={error}
    />
  );
}
