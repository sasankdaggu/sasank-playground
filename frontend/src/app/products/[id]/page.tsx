import { api } from "@/lib/api";
import { notFound } from "next/navigation";
import { ExternalLink } from "lucide-react";
import AddToShelfButton from "@/components/shelf/AddToShelfButton";
import ProductImageGallery from "@/components/product/ProductImageGallery";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function ProductPage({ params }: Props) {
  const { id } = await params;
  const product = await api.products.get(Number(id)).catch((e: unknown) => {
    console.error("[ProductPage] fetch error for id=%s:", id, e);
    return null;
  });
  if (!product) notFound();

  const cheapest = product.listings.find((l) => l.current_price != null);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="grid md:grid-cols-2 gap-8">
        {/* Image gallery */}
        <ProductImageGallery images={product.images} name={product.canonical_name} />

        {/* Core info */}
        <div className="flex flex-col gap-4">
          <div>
            <div className="text-sm text-gray-400 mb-1">{product.brand_name}</div>
            <h1 className="text-2xl font-bold leading-snug">{product.canonical_name}</h1>
            {product.category && (
              <span className="inline-block mt-2 text-xs bg-pink-50 text-[#e85d9b] px-2 py-0.5 rounded-full">
                {product.category}
              </span>
            )}
          </div>

          {/* Price */}
          {cheapest && (
            <div className="text-3xl font-bold text-[#e85d9b]">
              ₹{Number(cheapest.current_price).toFixed(0)}
              <span className="text-sm font-normal text-gray-400 ml-2">from {cheapest.retailer_name}</span>
            </div>
          )}

          <AddToShelfButton productId={product.id} />

          {/* Variants */}
          {product.variants.length > 1 && (
            <div>
              <div className="text-xs text-gray-500 mb-2 font-medium uppercase tracking-wide">Variants</div>
              <div className="flex flex-wrap gap-2">
                {product.variants.map((v) => (
                  <span key={v.sku} className="text-xs border border-gray-200 rounded-lg px-2.5 py-1 text-gray-600">
                    {v.option_value} — ₹{v.price}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Price compare table */}
      <section className="mt-10">
        <h2 className="text-lg font-bold mb-4">Available at</h2>
        <div className="rounded-2xl border border-gray-100 overflow-hidden">
          {product.listings.map((l, i) => (
            <div
              key={l.retailer_id}
              className={`flex items-center justify-between px-4 py-3 ${
                i === 0 ? "bg-pink-50" : "bg-white"
              } ${i > 0 ? "border-t border-gray-100" : ""}`}
            >
              <div className="flex items-center gap-3">
                {i === 0 && (
                  <span className="text-xs bg-[#e85d9b] text-white px-2 py-0.5 rounded-full">Best price</span>
                )}
                <span className="font-medium text-sm">{l.retailer_name}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  l.stock_status === "in_stock" ? "bg-green-50 text-green-600" :
                  l.stock_status === "out_of_stock" ? "bg-red-50 text-red-500" : "bg-gray-50 text-gray-400"
                }`}>
                  {l.stock_status.replace("_", " ")}
                </span>
              </div>
              <div className="flex items-center gap-4">
                <span className="font-bold">{l.current_price ? `₹${Number(l.current_price).toFixed(0)}` : "—"}</span>
                <a
                  href={l.listing_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs flex items-center gap-1 text-[#e85d9b] hover:underline"
                >
                  Buy <ExternalLink size={11} />
                </a>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Ingredients */}
      {product.ingredients_raw && (
        <section className="mt-10">
          <h2 className="text-lg font-bold mb-1">Ingredients</h2>
          <p className="text-xs text-gray-400 mb-4">Full INCI list · {product.ingredients_raw.split(",").length} ingredients</p>
          <div className="flex flex-wrap gap-2">
            {product.ingredients_raw.split(",").map((ing, i) => {
              const name = ing.trim();
              if (!name) return null;
              return (
                <span
                  key={i}
                  className="text-xs bg-gray-50 border border-gray-100 text-gray-600 px-2.5 py-1 rounded-full"
                >
                  {name}
                </span>
              );
            })}
          </div>
        </section>
      )}

      {/* Description */}
      {product.description_raw && (
        <section className="mt-8">
          <h2 className="text-lg font-bold mb-3">About this product</h2>
          <div
            className="text-sm text-gray-600 leading-relaxed prose prose-sm max-w-none"
            dangerouslySetInnerHTML={{ __html: product.description_raw }}
          />
          {product.description_source && (
            <div className="mt-2 text-xs text-gray-400">Source: {product.description_source.replace(/_/g, " ")}</div>
          )}
        </section>
      )}
    </div>
  );
}
