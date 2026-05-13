"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sparkles, LogOut } from "lucide-react";
import clsx from "clsx";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import AuthModal from "./AuthModal";

const links = [
  { href: "/catalog", label: "Catalog" },
  { href: "/shelf", label: "My Shelf" },
];

export default function Nav() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const [showAuth, setShowAuth] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-1.5 font-bold text-lg tracking-tight">
            <Sparkles size={18} className="text-[#e85d9b]" />
            wand
          </Link>
          <nav className="flex items-center gap-6">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={clsx(
                  "text-sm font-medium transition-colors",
                  pathname.startsWith(l.href) ? "text-[#e85d9b]" : "text-gray-500 hover:text-gray-900"
                )}
              >
                {l.label}
              </Link>
            ))}
            {user ? (
              <div className="flex items-center gap-3">
                <span className="text-sm text-gray-500">{user.name?.split(" ")[0] ?? "You"}</span>
                <button onClick={signOut} className="text-gray-400 hover:text-gray-600">
                  <LogOut size={15} />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowAuth(true)}
                className="text-sm font-medium bg-[#e85d9b] text-white px-3 py-1.5 rounded-lg hover:bg-pink-600 transition-colors"
              >
                Sign in
              </button>
            )}
          </nav>
        </div>
      </header>

      {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
    </>
  );
}
