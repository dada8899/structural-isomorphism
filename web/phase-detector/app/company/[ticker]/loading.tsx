export default function CompanyLoading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <div className="h-9 w-40 animate-pulse rounded bg-zinc-200" />
      <div className="h-36 animate-pulse rounded-xl border border-zinc-200 bg-white" />
      <div className="h-28 animate-pulse rounded-xl border border-zinc-200 bg-white" />
    </div>
  );
}
