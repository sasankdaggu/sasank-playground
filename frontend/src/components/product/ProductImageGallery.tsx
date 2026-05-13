"use client";

import { useState } from "react";
import { ShoppingBag } from "lucide-react";

interface Props {
  images: string[];
  name: string;
}

export default function ProductImageGallery({ images, name }: Props) {
  const [selected, setSelected] = useState(0);
  const visibleImages = images.slice(0, 8);

  return (
    <div className="flex flex-col gap-3">
      {/* Main image */}
      <div className="aspect-square rounded-2xl overflow-hidden flex items-center justify-center bg-[#FDF8F5]">
        {visibleImages[selected] ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={visibleImages[selected]}
            alt={name}
            className="w-full h-full object-contain p-4"
          />
        ) : (
          <ShoppingBag size={48} className="text-gray-200" />
        )}
      </div>

      {/* Thumbnails — only shown when multiple images */}
      {visibleImages.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {visibleImages.map((url, i) => (
            <button
              key={i}
              onClick={() => setSelected(i)}
              className={`flex-shrink-0 w-14 h-14 rounded-xl overflow-hidden border-2 transition-colors bg-[#FDF8F5] ${
                i === selected ? "border-[#e85d9b]" : "border-transparent hover:border-gray-200"
              }`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={url} alt={`${name} view ${i + 1}`} className="w-full h-full object-contain p-1" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
