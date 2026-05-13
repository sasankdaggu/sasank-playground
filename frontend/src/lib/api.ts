const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ProductSummary {
  id: number;
  canonical_name: string;
  brand_name: string;
  images: string[];
  min_price: string | null;
  max_price: string | null;
  retailer_count: number;
  ingredient_scrape_status: string;
}

export interface RetailerListing {
  retailer_id: number;
  retailer_name: string;
  retailer_slug: string;
  listing_url: string;
  current_price: string | null;
  compare_at_price: string | null;
  stock_status: string;
  rating_value: number | null;
  rating_count: number | null;
  last_scraped_at: string | null;
}

export interface ProductDetail {
  id: number;
  canonical_name: string;
  brand_name: string;
  brand_id: number;
  images: string[];
  variants: Array<{
    sku: string;
    price: number;
    available: boolean;
    option_name: string;
    option_value: string;
    compare_at_price: number | null;
  }>;
  description_raw: string | null;
  description_source: string | null;
  ingredient_scrape_status: string;
  ingredients_raw: string | null;
  listings: RetailerListing[];
  category: string | null;
}

export interface ProductSearchResult {
  items: ProductSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface Brand {
  id: number;
  name: string;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  parent_id: number | null;
}

export interface FiltersResult {
  brands: Brand[];
  categories: Category[];
}

export interface ShelfItem {
  id: number;
  product_id: number;
  canonical_name: string;
  brand_name: string;
  images: string[];
  added_at: string;
  opened_date: string | null;
  pct_remaining: number | null;
  user_rating: number | null;
  notes: string | null;
  purchase_price: string | null;
}

export interface UserProfile {
  id: number;
  phone: string | null;
  name: string | null;
  theme_slug: string;
  selected_agent_slugs: string[];
  profile: Record<string, unknown>;
  onboarding_step: string | null;
  goals: Record<string, string[]>;
  skin_profile: Record<string, unknown>;
}

export interface SkinAnalysisResult {
  skin_type: string | null;
  visible_concerns: string[];
  texture: string | null;
  oiliness: string | null;
  skin_tone: string | null;
  notes: string | null;
  raw: Record<string, unknown>;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  products: {
    search: (params: { q?: string; category?: string; brand_ids?: number[]; product_type?: string; page?: number; page_size?: number }) => {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.category) qs.set("category", params.category);
      params.brand_ids?.forEach((id) => qs.append("brand_id", String(id)));
      if (params.product_type) qs.set("product_type", params.product_type);
      if (params.page) qs.set("page", String(params.page));
      if (params.page_size) qs.set("page_size", String(params.page_size));
      return apiFetch<ProductSearchResult>(`/products?${qs}`);
    },
    get: (id: number) => apiFetch<ProductDetail>(`/products/${id}`),
    filters: (params?: { q?: string; brand_ids?: number[]; product_type?: string }) => {
      const qs = new URLSearchParams();
      if (params?.q) qs.set("q", params.q);
      params?.brand_ids?.forEach((id) => qs.append("brand_id", String(id)));
      if (params?.product_type) qs.set("product_type", params.product_type);
      return apiFetch<FiltersResult>(`/products/filters${qs.toString() ? `?${qs}` : ""}`);
    },
  },

  shelf: {
    get: (token: string) =>
      apiFetch<ShelfItem[]>("/shelf", { headers: { Authorization: `Bearer ${token}` } }),
    add: (token: string, product_id: number) =>
      apiFetch<ShelfItem>("/shelf", {
        method: "POST",
        body: JSON.stringify({ product_id }),
        headers: { Authorization: `Bearer ${token}` },
      }),
    remove: (token: string, item_id: number) =>
      apiFetch<void>(`/shelf/${item_id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      }),
  },

  auth: {
    me: (token: string) =>
      apiFetch<UserProfile>("/auth/me", {
        headers: { Authorization: `Bearer ${token}` },
      }),
    updateMe: (token: string, data: Partial<{
      name: string;
      theme_slug: string;
      selected_agent_slugs: string[];
      goals: Record<string, string[]>;
      skin_profile: Record<string, unknown>;
      onboarding_step: string;
    }>) =>
      apiFetch<UserProfile>("/auth/me", {
        method: "PATCH",
        body: JSON.stringify(data),
        headers: { Authorization: `Bearer ${token}` },
      }),
    analyzeSkin: (token: string, imageBase64: string, mediaType = "image/jpeg") =>
      apiFetch<SkinAnalysisResult>("/auth/analyze-skin", {
        method: "POST",
        body: JSON.stringify({ image_base64: imageBase64, media_type: mediaType }),
        headers: { Authorization: `Bearer ${token}` },
      }),
  },
};
