"use client";

import { useState } from "react";
import { Plus, Check } from "lucide-react";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";
import AuthModal from "@/components/ui/AuthModal";

export default function AddToShelfButton({ productId }: { productId: number }) {
  const [state, setState] = useState<"idle" | "loading" | "added">("idle");
  const [showAuth, setShowAuth] = useState(false);

  async function handleAdd() {
    const token = getToken();
    if (!token) { setShowAuth(true); return; }
    setState("loading");
    try {
      await api.shelf.add(token, productId);
      setState("added");
    } catch {
      setState("idle");
    }
  }

  return (
    <>
      <button
        onClick={handleAdd}
        disabled={state !== "idle"}
        className="flex items-center gap-2 bg-[#1a1a1a] text-white font-semibold px-5 py-2.5 rounded-xl hover:bg-gray-800 disabled:opacity-60 transition-colors w-fit"
      >
        {state === "added" ? <><Check size={16} /> On your shelf</> : <><Plus size={16} /> Add to shelf</>}
      </button>
      {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
    </>
  );
}
