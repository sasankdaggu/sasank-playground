"use client";

import { useRouter } from "next/navigation";
import { Search, ChevronDown, X } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import type { Brand, Category } from "@/lib/api";

interface Props {
  defaultQ?: string;
  defaultBrandIds?: number[];
  defaultCategory?: string;
  defaultSubcategory?: string;
  defaultProductType?: string;
  brands: Brand[];
  categories: Category[];
}

function MultiSelectDropdown({
  label,
  options,
  selected,
  onChange,
  active,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (vals: string[]) => void;
  active: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const buttonLabel =
    selected.length === 0
      ? label
      : selected.length === 1
      ? options.find((o) => o.value === selected[0])?.label ?? label
      : `${selected.length} selected`;

  const base =
    "border border-gray-200 rounded-xl text-sm px-3 py-2.5 focus:outline-none bg-white flex items-center gap-1.5 cursor-pointer";
  const activeStyle = "border-[#e85d9b] ring-2 ring-pink-200";

  function toggle(val: string) {
    if (selected.includes(val)) {
      onChange(selected.filter((v) => v !== val));
    } else {
      onChange([...selected, val]);
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`${base} ${active ? activeStyle : ""}`}
      >
        <span>{buttonLabel}</span>
        {selected.length > 0 && (
          <span
            className="ml-1 text-gray-400 hover:text-gray-600"
            onClick={(e) => {
              e.stopPropagation();
              onChange([]);
            }}
          >
            <X size={12} />
          </span>
        )}
        <ChevronDown size={14} className="text-gray-400 ml-auto" />
      </button>

      {open && (
        <div className="absolute z-20 top-full mt-1 left-0 bg-white border border-gray-200 rounded-xl shadow-lg min-w-[200px] max-h-64 overflow-y-auto">
          {options.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2.5 px-3 py-2 hover:bg-gray-50 cursor-pointer text-sm"
            >
              <input
                type="checkbox"
                checked={selected.includes(opt.value)}
                onChange={() => toggle(opt.value)}
                className="accent-[#e85d9b] w-3.5 h-3.5"
              />
              <span>{opt.label}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function SingleSelect({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (val: string) => void;
}) {
  const base =
    "border border-gray-200 rounded-xl text-sm px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-pink-200 focus:border-[#e85d9b] bg-white";
  const active = "border-[#e85d9b] ring-2 ring-pink-200";

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`${base} ${value ? active : ""}`}
    >
      <option value="">{label}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export default function CatalogSearch({
  defaultQ,
  defaultBrandIds = [],
  defaultCategory,
  defaultSubcategory,
  defaultProductType,
  brands,
  categories,
}: Props) {
  const router = useRouter();
  const [q, setQ] = useState(defaultQ || "");
  const [brandIds, setBrandIds] = useState<string[]>(defaultBrandIds.map(String));
  const [category, setCategory] = useState(defaultCategory || "");
  const [subcategory, setSubcategory] = useState(defaultSubcategory || "");
  const [productType, setProductType] = useState(defaultProductType || "");

  const topLevelCategories = categories.filter((c) => c.parent_id === null);
  const selectedTopCategory = categories.find((c) => c.slug === category);
  const subcategories = selectedTopCategory
    ? categories.filter((c) => c.parent_id === selectedTopCategory.id)
    : [];

  function buildParams(overrides: Partial<{ q: string; brandIds: string[]; category: string; subcategory: string; productType: string }> = {}) {
    const vals = {
      q: overrides.q !== undefined ? overrides.q : q.trim(),
      brandIds: overrides.brandIds !== undefined ? overrides.brandIds : brandIds,
      category: overrides.category !== undefined ? overrides.category : category,
      subcategory: overrides.subcategory !== undefined ? overrides.subcategory : subcategory,
      productType: overrides.productType !== undefined ? overrides.productType : productType,
    };
    const params = new URLSearchParams();
    if (vals.q) params.set("q", vals.q);
    vals.brandIds.forEach((id) => params.append("brand_id", id));
    if (vals.productType) params.set("product_type", vals.productType);
    if (vals.subcategory) {
      params.set("subcategory", vals.subcategory);
      params.set("category", vals.category);
    } else if (vals.category) {
      params.set("category", vals.category);
    }
    return params;
  }

  function navigate(overrides?: Parameters<typeof buildParams>[0]) {
    const params = buildParams(overrides);
    router.push(`/catalog${params.toString() ? `?${params}` : ""}`);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    navigate();
  }

  function handleBrandsChange(vals: string[]) {
    setBrandIds(vals);
    navigate({ brandIds: vals });
  }

  function handleCategorySelect(slug: string) {
    setCategory(slug);
    setSubcategory("");
    navigate({ category: slug, subcategory: "" });
  }

  function handleSubcategorySelect(slug: string) {
    setSubcategory(slug);
    navigate({ subcategory: slug });
  }

  function handleProductTypeChange(val: string) {
    setProductType(val);
    navigate({ productType: val });
  }

  const showBrands = brands.length > 1;
  const showCategoryDropdown = topLevelCategories.length > 1;
  const showCategoryTag = topLevelCategories.length === 1;
  const showSubcategory = subcategories.length > 1;

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={handleSubmit} className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search products, ingredients, brands..."
          className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-pink-200 focus:border-[#e85d9b]"
        />
      </form>

      {(showBrands || showCategoryDropdown || showCategoryTag || showSubcategory) && (
        <div className="flex flex-wrap gap-2 items-center">
          {showBrands && (
            <MultiSelectDropdown
              label="All Brands"
              options={brands.map((b) => ({ value: String(b.id), label: b.name }))}
              selected={brandIds}
              onChange={handleBrandsChange}
              active={brandIds.length > 0}
            />
          )}

          {showCategoryTag && (
            <span className="border border-[#e85d9b] ring-2 ring-pink-200 rounded-xl text-sm px-3 py-2.5 bg-white text-gray-700">
              {topLevelCategories[0].name}
            </span>
          )}

          {showCategoryDropdown && (
            <SingleSelect
              label="All Categories"
              options={topLevelCategories.map((c) => ({ value: c.slug, label: c.name }))}
              value={category}
              onChange={handleCategorySelect}
            />
          )}

          {showSubcategory && (
            <SingleSelect
              label="All Subcategories"
              options={subcategories.map((c) => ({ value: c.slug, label: c.name }))}
              value={subcategory}
              onChange={handleSubcategorySelect}
            />
          )}

          <SingleSelect
            label="All Products"
            options={[{ value: "singles", label: "Singles only" }]}
            value={productType}
            onChange={handleProductTypeChange}
          />
        </div>
      )}
    </div>
  );
}
