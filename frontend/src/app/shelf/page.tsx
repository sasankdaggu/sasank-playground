"use client";

import { useEffect, useState } from "react";
import { api, type ShelfItem } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { useAuth } from "@/lib/auth-context";
import Link from "next/link";
import { ShoppingBag, Sparkles, Plus } from "lucide-react";

export default function ShelfPage() {
  const { user, loading: authLoading } = useAuth();
  const [items, setItems] = useState<ShelfItem[]>([]);
  const [itemsLoading, setItemsLoading] = useState(false);

  useEffect(() => {
    if (!user) return;
    const token = getToken();
    if (!token) return;
    setItemsLoading(true);
    api.shelf.get(token).then(setItems).finally(() => setItemsLoading(false));
  }, [user]);

  if (authLoading) {
    return <div className="max-w-6xl mx-auto px-4 py-8 text-sm text-gray-400">Loading...</div>;
  }

  if (!user) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-24 text-center">
        <Sparkles size={36} className="text-[#e85d9b] mx-auto mb-4" />
        <h1 className="text-2xl font-bold mb-2">Your shelf lives here</h1>
        <p className="text-gray-500 mb-6 text-sm">Sign in to build your virtual bathroom shelf and track everything you&apos;re using.</p>
        <Link href="/onboarding" className="inline-flex items-center gap-2 bg-[#e85d9b] text-white font-semibold px-5 py-2.5 rounded-xl hover:bg-pink-600 transition-colors text-sm">
          Get started
        </Link>
      </div>
    );
  }

  if (itemsLoading) {
    return <div className="max-w-6xl mx-auto px-4 py-8 text-sm text-gray-400">Loading your shelf...</div>;
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">My Shelf</h1>
        <Link
          href="/catalog"
          className="inline-flex items-center gap-1.5 text-sm border border-gray-200 rounded-xl px-3 py-2 hover:bg-gray-50 transition-colors"
        >
          <Plus size={14} /> Add products
        </Link>
      </div>

      {items.length === 0 ? (
        <div className="text-center py-24 text-gray-400">
          <ShoppingBag size={40} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">Your shelf is empty. Find your first product.</p>
          <Link href="/catalog" className="mt-4 inline-block text-[#e85d9b] text-sm hover:underline">Browse catalog →</Link>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {items.map((item) => (
            <Link
              key={item.id}
              href={`/products/${item.product_id}`}
              className="bg-white rounded-2xl border border-gray-100 overflow-hidden hover:shadow-md transition-all"
            >
              <div className="aspect-square bg-[#FDF8F5] flex items-center justify-center">
                {item.images[0] ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={item.images[0]} alt={item.canonical_name} className="w-full h-full object-contain p-3" />
                ) : (
                  <ShoppingBag size={28} className="text-gray-200" />
                )}
              </div>
              <div className="p-3">
                <div className="text-xs text-gray-400 mb-0.5">{item.brand_name}</div>
                <div className="text-sm font-medium line-clamp-2 text-gray-900">{item.canonical_name}</div>
                {item.pct_remaining != null && (
                  <div className="mt-2">
                    <div className="text-xs text-gray-400 mb-1">{item.pct_remaining}% remaining</div>
                    <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-[#e85d9b] rounded-full" style={{ width: `${item.pct_remaining}%` }} />
                    </div>
                  </div>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
