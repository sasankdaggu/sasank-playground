"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Plus, X, ChevronRight, Search, Barcode } from "lucide-react";
import Link from "next/link";
import type { Theme } from "@/lib/themes";
import { THEMES } from "@/lib/themes";
import { api, type ProductSummary } from "@/lib/api";

interface ShelfBuildStepProps {
  theme: Theme;
  onThemeChange: (slug: string) => void;
  initialProductIds: number[];
  onNext: (productIds: number[]) => void;
}

interface ShelfProduct {
  id: number;
  name: string;
  brand: string;
  image: string | null;
}

const SHELF_ROWS = [
  { label: "Face", emoji: "✨", slots: 4 },
  { label: "Body", emoji: "🛁", slots: 3 },
  { label: "Hair", emoji: "💆", slots: 3 },
];

export default function ShelfBuildStep({ theme, onThemeChange, initialProductIds, onNext }: ShelfBuildStepProps) {
  const [shelfProducts, setShelfProducts] = useState<Record<string, ShelfProduct[]>>({
    Face: [],
    Body: [],
    Hair: [],
  });
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ProductSummary[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [activeSlot, setActiveSlot] = useState<{ row: string } | null>(null);
  const [barcodeSupported, setBarcodeSupported] = useState(false);
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    setBarcodeSupported("BarcodeDetector" in window);
  }, []);

  // Restore products from draft when navigating back to this step
  useEffect(() => {
    if (!initialProductIds.length) return;
    // Fetch details for each saved ID and place in Face row (we don't store row assignments)
    Promise.all(initialProductIds.map((id) => api.products.get(id).catch(() => null)))
      .then((details) => {
        const restored: ShelfProduct[] = details
          .filter(Boolean)
          .map((d) => ({ id: d!.id, name: d!.canonical_name, brand: d!.brand_name, image: d!.images[0] ?? null }));
        if (restored.length) {
          setShelfProducts((prev) => ({
            ...prev,
            Face: restored.filter((p) => !Object.values(prev).flat().some((x) => x.id === p.id)),
          }));
        }
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = (q: string) => {
    setSearchQuery(q);
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    if (!q.trim()) { setSearchResults([]); return; }
    searchTimeoutRef.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const res = await api.products.search({ q, page_size: 8 });
        setSearchResults(res.items);
      } finally {
        setSearchLoading(false);
      }
    }, 400);
  };

  const addProduct = (row: string, product: ProductSummary) => {
    const row_ = shelfProducts[row] || [];
    if (row_.some((p) => p.id === product.id)) return;
    setShelfProducts((prev) => ({
      ...prev,
      [row]: [...prev[row], {
        id: product.id,
        name: product.canonical_name,
        brand: product.brand_name,
        image: product.images[0] || null,
      }],
    }));
    setActiveSlot(null);
    setSearchQuery("");
    setSearchResults([]);
  };

  const removeProduct = (row: string, productId: number) => {
    setShelfProducts((prev) => ({
      ...prev,
      [row]: prev[row].filter((p) => p.id !== productId),
    }));
  };

  const handleBarcodeClick = async () => {
    if (!("BarcodeDetector" in window)) return;
    // Open camera and scan
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      // For simplicity, show a message. Full barcode scan requires video element.
      stream.getTracks().forEach((t) => t.stop());
      alert("Point your camera at a product barcode. Barcode scanning coming soon!");
    } catch {
      alert("Camera access denied. Try searching by name instead.");
    }
  };

  const totalProducts = Object.values(shelfProducts).flat().length;

  return (
    <div className="flex flex-col gap-6 max-w-2xl mx-auto">
      <div className="text-center">
        <div className="text-4xl mb-3">🛁</div>
        <h2 className="text-2xl font-bold mb-1">Build your shelf</h2>
        <p className="text-sm opacity-70">Add the products you currently use. You can always add more later.</p>
      </div>

      {/* Theme picker */}
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide opacity-60 mb-2">Theme</div>
        <div className="flex gap-2 flex-wrap">
          {THEMES.map((t) => (
            <button
              key={t.slug}
              onClick={() => onThemeChange(t.slug)}
              className={clsx(
                "text-xs px-3 py-1.5 rounded-full border transition-all font-medium flex items-center gap-1",
                theme.slug === t.slug ? "text-white border-transparent" : "bg-white/60 border-gray-200 hover:border-gray-400"
              )}
              style={theme.slug === t.slug ? { backgroundColor: theme.accentColor, borderColor: theme.accentColor } : {}}
            >
              {t.emoji} {t.name}
            </button>
          ))}
        </div>
      </div>

      {/* Visual shelf */}
      <div className={clsx("rounded-3xl p-6 transition-all relative overflow-hidden", theme.bg)} style={{ minHeight: 320 }}>
        {/* Bathroom wall decoration */}
        <div className="absolute inset-0 pointer-events-none">
          {theme.slug === "garden" && (
            <svg className="absolute right-0 top-0 h-full opacity-30" viewBox="0 0 80 300" fill="none">
              <path d="M70 300 Q60 250 65 200 Q70 150 60 100 Q50 50 65 0" stroke="#16a34a" strokeWidth="3" fill="none"/>
              <ellipse cx="55" cy="80" rx="12" ry="8" fill="#16a34a" transform="rotate(-30 55 80)"/>
              <ellipse cx="62" cy="140" rx="10" ry="7" fill="#16a34a" transform="rotate(20 62 140)"/>
              <ellipse cx="58" cy="200" rx="14" ry="9" fill="#16a34a" transform="rotate(-15 58 200)"/>
            </svg>
          )}
          {theme.slug === "pastel" && (
            <>
              <div className="absolute top-4 left-8 w-16 h-6 bg-white/40 rounded-full blur-sm"/>
              <div className="absolute top-6 left-16 w-10 h-4 bg-white/30 rounded-full blur-sm"/>
              <div className="absolute top-3 right-12 w-20 h-7 bg-white/40 rounded-full blur-sm"/>
            </>
          )}
        </div>

        {/* Shelves */}
        <div className="relative flex flex-col gap-8">
          {SHELF_ROWS.map((row) => {
            const products = shelfProducts[row.label];
            const emptySlots = Math.max(0, row.slots - products.length);
            return (
              <div key={row.label}>
                {/* Post-it label */}
                <div
                  className="inline-flex items-center gap-1 text-xs font-bold px-2 py-1 rounded mb-2 rotate-[-1deg] shadow-sm"
                  style={{ backgroundColor: theme.postitColor }}
                >
                  {row.emoji} {row.label}
                </div>

                {/* Plank */}
                <div
                  className="shelf-plank relative rounded-lg"
                  style={{
                    backgroundColor: theme.shelfColor,
                    height: 8,
                    boxShadow: `0 4px 8px rgba(0,0,0,0.2)`,
                  }}
                />

                {/* Products on shelf */}
                <div className="flex gap-3 mt-2 flex-wrap">
                  {/* Existing products */}
                  {products.map((product) => (
                    <div key={product.id} className="relative group flex flex-col items-center" style={{ width: 70 }}>
                      <div className="w-16 h-16 rounded-xl border-2 bg-white/80 flex items-center justify-center overflow-hidden shadow-sm"
                        style={{ borderColor: theme.borderColor }}>
                        {product.image ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={product.image} alt={product.name} className="w-full h-full object-contain p-1" />
                        ) : (
                          <span className="text-2xl">🧴</span>
                        )}
                      </div>
                      <div className="text-center mt-1" style={{ maxWidth: 70 }}>
                        <div className="text-xs font-medium leading-tight line-clamp-2 opacity-80">{product.name}</div>
                      </div>
                      <button
                        onClick={() => removeProduct(row.label, product.id)}
                        className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-white hidden group-hover:flex items-center justify-center"
                      >
                        <X size={9} />
                      </button>
                    </div>
                  ))}

                  {/* Empty slots */}
                  {Array.from({ length: emptySlots }).map((_, i) => (
                    <button
                      key={i}
                      onClick={() => setActiveSlot({ row: row.label })}
                      className="w-16 h-16 rounded-xl border-2 border-dashed flex flex-col items-center justify-center text-xs gap-1 transition-all hover:scale-105"
                      style={{ borderColor: theme.slotBorder, color: theme.slotBorder, opacity: 0.7 }}
                    >
                      <Plus size={16} />
                      <span style={{ fontSize: 9 }}>Add</span>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Search modal / inline */}
      {activeSlot && (
        <div className="rounded-2xl border p-4 bg-white/80 shadow-lg" style={{ borderColor: theme.borderColor }}>
          <div className="flex items-center justify-between mb-3">
            <div className="font-semibold text-sm">Add to {activeSlot.row}</div>
            <button onClick={() => { setActiveSlot(null); setSearchQuery(""); setSearchResults([]); }}>
              <X size={16} className="opacity-50" />
            </button>
          </div>

          <div className="flex gap-2 mb-3">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 opacity-40" />
              <input
                autoFocus
                type="text"
                placeholder="Search by product name or brand..."
                value={searchQuery}
                onChange={(e) => handleSearch(e.target.value)}
                className="w-full text-sm pl-9 pr-3 py-2 rounded-xl border border-gray-200 focus:outline-none focus:border-gray-400 bg-white"
              />
            </div>
            {barcodeSupported && (
              <button
                onClick={handleBarcodeClick}
                className="p-2 rounded-xl border border-gray-200 hover:bg-gray-50"
                title="Scan barcode"
              >
                <Barcode size={18} className="opacity-60" />
              </button>
            )}
          </div>

          {searchLoading && <div className="text-xs opacity-50 py-2">Searching...</div>}

          {searchResults.length > 0 && (
            <div className="flex flex-col divide-y divide-gray-100 max-h-48 overflow-y-auto rounded-xl border border-gray-100">
              {searchResults.map((p) => (
                <button
                  key={p.id}
                  onClick={() => addProduct(activeSlot.row, p)}
                  className="flex items-center gap-3 px-3 py-2 hover:bg-gray-50 text-left transition-colors"
                >
                  <div className="w-9 h-9 rounded-lg bg-gray-50 flex items-center justify-center flex-shrink-0 overflow-hidden">
                    {p.images[0] ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={p.images[0]} alt={p.canonical_name} className="w-full h-full object-contain p-0.5" />
                    ) : (
                      <span className="text-base">🧴</span>
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-medium line-clamp-1">{p.canonical_name}</div>
                    <div className="text-xs opacity-50">{p.brand_name}</div>
                  </div>
                </button>
              ))}
            </div>
          )}

          {searchQuery && !searchLoading && searchResults.length === 0 && (
            <div className="text-xs opacity-50 py-2 text-center">
              No results. <Link href="/catalog" className="underline">Browse catalog</Link>
            </div>
          )}
        </div>
      )}

      <button
        onClick={() => onNext(Object.values(shelfProducts).flat().map((p) => p.id))}
        className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
        style={{ backgroundColor: theme.accentColor, color: theme.textOnAccent }}
      >
        {totalProducts === 0 ? "Skip for now" : `Continue with ${totalProducts} product${totalProducts !== 1 ? "s" : ""}`}
        <ChevronRight size={16} />
      </button>
    </div>
  );
}
