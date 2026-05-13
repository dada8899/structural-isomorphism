"use client";

import { useCallback, useEffect, useState } from "react";
import { CompanyCard } from "@/components/CompanyCard";
import { ScreenerFilter } from "@/components/ScreenerFilter";
import { StatsBar } from "@/components/StatsBar";
import { fetchScreener, fetchStats } from "@/lib/api";
import type { Company, ScreenerFilters, Stats } from "@/lib/types";

export default function ScreenerHomePage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [filters, setFilters] = useState<ScreenerFilters>({ limit: 50 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initial stats fetch (independent from screener).
  useEffect(() => {
    let cancelled = false;
    fetchStats()
      .then((s) => {
        if (!cancelled) setStats(s);
      })
      .catch((err) => {
        if (!cancelled) {
          // Stats failure is non-fatal; keep stats null, log to console.
          // eslint-disable-next-line no-console
          console.warn("stats fetch failed:", err);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async (f: ScreenerFilters) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchScreener(f);
      setCompanies(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setCompanies([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(filters);
  }, [filters, load]);

  const handleApply = useCallback((next: ScreenerFilters) => {
    setFilters(next);
  }, []);

  return (
    <div className="space-y-5">
      <section>
        <h1 className="mb-1 text-2xl font-semibold tracking-tight">
          Company screener
        </h1>
        <p className="text-sm text-gray-500">
          Filter by structural dynamics family and critical-point state. 30s
          TL;DR per company.
        </p>
      </section>

      <StatsBar stats={stats} />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[260px_1fr]">
        <ScreenerFilter
          initial={filters}
          stats={stats}
          onApply={handleApply}
          loading={loading}
        />

        <section>
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              Failed to load screener: {error}
            </div>
          )}

          {!error && loading && companies.length === 0 && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-56 animate-pulse rounded-xl border border-gray-200 bg-gray-50"
                />
              ))}
            </div>
          )}

          {!error && !loading && companies.length === 0 && (
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-6 py-12 text-center text-sm text-gray-500">
              No companies match these filters. Try widening the search.
            </div>
          )}

          {!error && companies.length > 0 && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-2">
              {companies.map((c) => (
                <CompanyCard key={c.ticker} company={c} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
