import { api, ProductSearchResult, FiltersResult } from "@/lib/api";
import ProductCard from "@/components/product/ProductCard";
import CatalogSearch from "@/components/product/CatalogSearch";

interface Props {
  searchParams: Promise<{
    q?: string;
    category?: string;
    subcategory?: string;
    brand_id?: string | string[];
    product_type?: string;
    page?: string;
  }>;
}

const EMPTY_RESULT: ProductSearchResult = { items: [], total: 0, page: 1, page_size: 24 };
const EMPTY_FILTERS: FiltersResult = { brands: [], categories: [] };

export default async function CatalogPage({ searchParams }: Props) {
  const params = await searchParams;
  const q = params.q;
  const rawBrandId = params.brand_id;
  const brand_ids = rawBrandId
    ? (Array.isArray(rawBrandId) ? rawBrandId.map(Number) : [Number(rawBrandId)])
    : [];
  const category = params.subcategory || params.category;
  const product_type = params.product_type;
  const page = Number(params.page || 1);

  let result = EMPTY_RESULT;
  let filtersData = EMPTY_FILTERS;
  let apiError: string | null = null;

  try {
    [result, filtersData] = await Promise.all([
      api.products.search({ q, category, brand_ids, product_type, page, page_size: 24 }),
      api.products.filters({ q, brand_ids, product_type }),
    ]);
  } catch (e) {
    apiError = e instanceof Error ? e.message : "Failed to load products";
  }

  function paginationUrl(targetPage: number) {
    const ps = new URLSearchParams();
    if (q) ps.set("q", q);
    brand_ids.forEach((id) => ps.append("brand_id", String(id)));
    if (product_type) ps.set("product_type", product_type);
    if (params.category) ps.set("category", params.category);
    if (params.subcategory) ps.set("subcategory", params.subcategory);
    ps.set("page", String(targetPage));
    return `/catalog?${ps}`;
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1">Catalog</h1>
        {!apiError && <p className="text-sm text-gray-500">{result.total} products</p>}
      </div>

      <CatalogSearch
        defaultQ={q}
        defaultBrandIds={brand_ids}
        defaultCategory={params.category}
        defaultSubcategory={params.subcategory}
        defaultProductType={product_type}
        brands={filtersData.brands}
        categories={filtersData.categories}
      />

      {apiError ? (
        <div className="text-center py-24 text-gray-400">
          <p className="text-base mb-1">Could not load products</p>
          <p className="text-sm">{apiError}</p>
        </div>
      ) : result.items.length === 0 ? (
        <div className="text-center py-24 text-gray-400">
          No products found{q ? ` for "${q}"` : ""}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mt-6">
          {result.items.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}

      {result.total > 24 && (
        <div className="flex justify-center gap-2 mt-10">
          {page > 1 && (
            <a
              href={paginationUrl(page - 1)}
              className="px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50"
            >
              Previous
            </a>
          )}
          <span className="px-4 py-2 text-sm text-gray-500">Page {page}</span>
          {page * 24 < result.total && (
            <a
              href={paginationUrl(page + 1)}
              className="px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50"
            >
              Next
            </a>
          )}
        </div>
      )}
    </div>
  );
}
