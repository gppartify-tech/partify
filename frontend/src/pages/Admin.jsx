import { Database, RefreshCw } from "lucide-react";
import { ErrorBox, PageLoader, StoreBadge } from "../components/ui";
import { timeAgo } from "../lib/format";
import { useApi } from "../lib/useApi";

export default function Admin() {
  const { data: stats, error, reload, loading } = useApi("/admin/stats");
  if (error && !stats) return <div className="container-page py-10"><ErrorBox error={error} /></div>;
  if (!stats) return <PageLoader />;
  const tiles = [
    ["Products", stats.products], ["Store offers", stats.offers], ["Price points", stats.price_points],
    ["Users", stats.users], ["Wishlist items", stats.wishlist_items], ["Listings", stats.listings],
  ];

  return (
    <div className="container-page py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight sm:text-3xl"><Database className="h-7 w-7 text-indigo-600 dark:text-indigo-400" /> Admin</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">What is in the database right now.</p>
        </div>
        <button className="btn btn-secondary" onClick={reload}><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Refresh</button>
      </div>
      <ErrorBox error={error} className="mt-4" />

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {tiles.map(([label, value]) => (
          <div key={label} className="card p-4">
            <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
            <div className="mt-1 text-2xl font-bold">{value.toLocaleString()}</div>
          </div>
        ))}
      </div>

      <section className="card mt-6 overflow-hidden">
        <h2 className="border-b border-slate-100 dark:border-slate-800 px-5 py-4 font-semibold">Stores</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              <tr><th className="px-5 py-2.5">Store</th><th className="px-3 py-2.5 text-right">Active offers</th><th className="px-3 py-2.5 text-right">In stock</th><th className="px-5 py-2.5">Prices updated</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {stats.stores.map(({ store, active_offers, in_stock_offers }) => (
                <tr key={store.id}>
                  <td className="px-5 py-3"><StoreBadge store={store} className="font-semibold" /></td>
                  <td className="tabular px-3 py-3 text-right">{active_offers}</td>
                  <td className="tabular px-3 py-3 text-right">{in_stock_offers}</td>
                  <td className="px-5 py-3 text-slate-600 dark:text-slate-300">{timeAgo(store.prices_updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
