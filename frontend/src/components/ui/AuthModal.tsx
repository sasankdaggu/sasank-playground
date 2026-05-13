"use client";

import { useEffect, useRef, useState } from "react";
import { X, Mail, ArrowRight, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: object) => void;
          renderButton: (el: HTMLElement, config: object) => void;
          prompt: () => void;
        };
      };
    };
  }
}

interface Props {
  onClose: () => void;
}

export default function AuthModal({ onClose }: Props) {
  const { signInWithGoogle, sendEmailOtp, verifyEmailOtp } = useAuth();
  const googleBtnRef = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState<"choose" | "email-send" | "email-verify">("choose");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId || !window.google || !googleBtnRef.current) return;

    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: async (response: { credential: string }) => {
        try {
          await signInWithGoogle(response.credential);
          onClose();
        } catch {
          setError("Google sign-in failed. Try email instead.");
        }
      },
    });

    window.google.accounts.id.renderButton(googleBtnRef.current, {
      theme: "outline",
      size: "large",
      width: "100%",
      text: "signin_with",
    });
  }, [signInWithGoogle, onClose]);

  async function handleEmailSend(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await sendEmailOtp(email);
      setStep("email-verify");
    } catch {
      setError("Failed to send OTP. Check the email address.");
    } finally {
      setLoading(false);
    }
  }

  async function handleEmailVerify(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await verifyEmailOtp(email, otp);
      onClose();
    } catch {
      setError("Invalid or expired code. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-4 p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-gray-400 hover:text-gray-600">
          <X size={18} />
        </button>

        <h2 className="text-xl font-bold mb-1">Sign in to Wand</h2>
        <p className="text-sm text-gray-500 mb-6">Save your shelf and track prices across retailers.</p>

        {step === "choose" && (
          <div className="flex flex-col gap-3">
            {/* Google button — rendered by GSI SDK */}
            <div ref={googleBtnRef} className="w-full" />

            {/* Fallback if Google SDK not loaded */}
            {!process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID && (
              <div className="text-xs text-center text-gray-400">Google sign-in not configured</div>
            )}

            <div className="flex items-center gap-3 my-1">
              <div className="flex-1 h-px bg-gray-100" />
              <span className="text-xs text-gray-400">or</span>
              <div className="flex-1 h-px bg-gray-100" />
            </div>

            <button
              onClick={() => setStep("email-send")}
              className="flex items-center justify-center gap-2 border border-gray-200 rounded-xl py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              <Mail size={15} /> Continue with email
            </button>
          </div>
        )}

        {step === "email-send" && (
          <form onSubmit={handleEmailSend} className="flex flex-col gap-3">
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
              autoFocus
              className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-pink-200 focus:border-[#e85d9b]"
            />
            {error && <p className="text-xs text-red-500">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="flex items-center justify-center gap-2 bg-[#e85d9b] text-white font-semibold py-2.5 rounded-xl hover:bg-pink-600 disabled:opacity-60 transition-colors text-sm"
            >
              {loading ? <Loader2 size={15} className="animate-spin" /> : <><ArrowRight size={15} /> Send code</>}
            </button>
            <button type="button" onClick={() => setStep("choose")} className="text-xs text-center text-gray-400 hover:text-gray-600">
              ← Back
            </button>
          </form>
        )}

        {step === "email-verify" && (
          <form onSubmit={handleEmailVerify} className="flex flex-col gap-3">
            <p className="text-sm text-gray-500">We sent a 6-digit code to <strong>{email}</strong></p>
            <input
              type="text"
              value={otp}
              onChange={e => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="000000"
              required
              autoFocus
              className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm text-center tracking-widest text-lg font-bold focus:outline-none focus:ring-2 focus:ring-pink-200 focus:border-[#e85d9b]"
            />
            {error && <p className="text-xs text-red-500">{error}</p>}
            <button
              type="submit"
              disabled={loading || otp.length < 6}
              className="flex items-center justify-center gap-2 bg-[#e85d9b] text-white font-semibold py-2.5 rounded-xl hover:bg-pink-600 disabled:opacity-60 transition-colors text-sm"
            >
              {loading ? <Loader2 size={15} className="animate-spin" /> : "Verify & sign in"}
            </button>
            <button type="button" onClick={() => { setStep("email-send"); setOtp(""); }} className="text-xs text-center text-gray-400 hover:text-gray-600">
              ← Resend code
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
