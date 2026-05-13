import Link from "next/link";
import type { ProductSummary } from "@/lib/api";
import { ShoppingBag } from "lucide-react";

export default function ProductCard({ product }: { product: ProductSummary }) {
  const price = product.min_price ? `₹${Number(product.min_price).toFixed(0)}` : "—";

  return (
    <Link
      href={`/products/${product.id}`}
      className="group bg-white rounded-2xl border border-gray-100 overflow-hidden hover:shadow-md hover:border-pink-100 transition-all duration-200"
    >
      {/* Image */}
      <div className="aspect-square bg-[#FDF8F5] flex items-center justify-center relative">
        {product.images[0] ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={product.images[0]}
            alt={product.canonical_name}
            className="w-full h-full object-contain p-3"
          />
        ) : (
          <ShoppingBag size={32} className="text-gray-200" />
        )}
      </div>

      {/* Info */}
      <div className="p-3">
        <div className="text-xs text-gray-400 mb-0.5">{product.brand_name}</div>
        <div className="text-sm font-medium text-gray-900 line-clamp-2 leading-snug mb-2">
          {product.canonical_name}
        </div>
        <div className="flex items-center justify-between">
          <span className="text-base font-bold text-[#e85d9b]">{price}</span>
          <span className="text-xs text-gray-400">
            {product.retailer_count} {product.retailer_count === 1 ? "retailer" : "retailers"}
          </span>
        </div>
      </div>
    </Link>
  );
}
