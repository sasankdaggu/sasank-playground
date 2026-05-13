import Link from "next/link";
import { ArrowRight, ShieldCheck, Zap, Search } from "lucide-react";

export default function Home() {
  return (
    <div className="flex flex-col items-center">
      {/* Hero */}
      <section className="w-full max-w-4xl mx-auto px-4 pt-20 pb-16 text-center">
        <div className="inline-flex items-center gap-2 bg-pink-50 text-[#e85d9b] text-sm font-medium px-3 py-1 rounded-full mb-6">
          <span className="w-1.5 h-1.5 bg-[#e85d9b] rounded-full" />
          AI-native skincare — India Gen Z
        </div>
        <h1 className="text-5xl md:text-6xl font-bold tracking-tight mb-6 leading-tight">
          Every product has a panel of{" "}
          <span className="text-[#e85d9b]">AI experts</span>
          {" "}working for you
        </h1>
        <p className="text-xl text-gray-500 mb-8 max-w-2xl mx-auto">
          Price compare, ingredient check, dupe finder — across Nykaa, Tira, Purplle, and your favourite D2C brands. On your side, not the retailer&apos;s.
        </p>
        <div className="flex items-center gap-3 justify-center">
          <Link
            href="/catalog"
            className="inline-flex items-center gap-2 bg-[#e85d9b] text-white font-semibold px-6 py-3 rounded-xl hover:bg-pink-600 transition-colors"
          >
            Explore catalog <ArrowRight size={16} />
          </Link>
          <Link
            href="/onboarding"
            className="inline-flex items-center gap-2 border border-gray-200 text-gray-700 font-semibold px-6 py-3 rounded-xl hover:bg-gray-50 transition-colors"
          >
            Build my shelf
          </Link>
        </div>
      </section>

      {/* Trust strip */}
      <section className="w-full bg-white border-y border-gray-100 py-8">
        <div className="max-w-4xl mx-auto px-4 grid grid-cols-3 gap-6 text-center">
          {[
            { icon: ShieldCheck, title: "No brand bias", desc: "Zero paid placements. Affiliate links always disclosed." },
            { icon: Search, title: "Ingredient-first", desc: "Full INCI list, flagged irritants, dupe matches." },
            { icon: Zap, title: "Live prices", desc: "Hourly refresh on top SKUs across all major retailers." },
          ].map(({ icon: Icon, title, desc }) => (
            <div key={title} className="flex flex-col items-center gap-2">
              <Icon size={22} className="text-[#e85d9b]" />
              <div className="font-semibold text-sm">{title}</div>
              <div className="text-xs text-gray-500">{desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Coming soon agents */}
      <section className="w-full max-w-4xl mx-auto px-4 py-16 text-center">
        <div className="text-sm text-gray-400 uppercase tracking-widest mb-3">Phase 2 — coming soon</div>
        <h2 className="text-2xl font-bold mb-8">Your AI agent panel</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {["Price Scout", "Ingredient Check", "Dupe Hunter", "Creator Buzz", "Routine Builder", "Restock Alert"].map((a) => (
            <div key={a} className="bg-white border border-gray-100 rounded-xl p-4 text-sm font-medium text-gray-600 opacity-60">
              {a}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
