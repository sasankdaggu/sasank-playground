import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import Nav from "@/components/ui/Nav";
import OnboardingBanner from "@/components/OnboardingBanner";
import { AuthProvider } from "@/lib/auth-context";
import Script from "next/script";
import { Toaster } from "sonner";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });

export const metadata: Metadata = {
  title: "Wand — AI skincare for you, not the retailer",
  description: "AI-native skincare aggregator. Price compare, ingredient check, dupe finder — on your side.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geist.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-[#fafaf9] text-[#1a1a1a]">
        <Script src="https://accounts.google.com/gsi/client" strategy="lazyOnload" />
        <AuthProvider>
          <Nav />
          <OnboardingBanner />
          <main className="flex-1">{children}</main>
          <Toaster position="bottom-center" />
        </AuthProvider>
      </body>
    </html>
  );
}
