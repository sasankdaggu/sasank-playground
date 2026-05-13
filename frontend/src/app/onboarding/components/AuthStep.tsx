"use client";

import { useEffect, useRef, useState } from "react";
import type { Theme } from "@/lib/themes";
import { useAuth } from "@/lib/auth-context";

interface AuthStepProps {
  theme: Theme;
  onComplete: () => void;
}

export default function AuthStep({ theme, onComplete }: AuthStepProps) {
  const { user, signInWithGoogle, sendEmailOtp, verifyEmailOtp } = useAuth();
  const googleButtonRef = useRef<HTMLDivElement>(null);
  const [emailStep, setEmailStep] = useState<"email" | "otp">("email");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"choose" | "email">("choose");

  // If already signed in, complete immediately
  useEffect(() => {
    if (user) onComplete();
  }, [user, onComplete]);

  // Mount Google Sign-In button
  useEffect(() => {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId || !googleButtonRef.current) return;

    const mountButton = () => {
      if (!window.google || !googleButtonRef.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: async (response: { credential: string }) => {
          setLoading(true);
          setError(null);
          try {
            await signInWithGoogle(response.credential);
            onComplete();
          } catch {
            setError("Google sign-in failed. Try email instead.");
          } finally {
            setLoading(false);
          }
        },
      });
      window.google.accounts.id.renderButton(googleButtonRef.current!, {
        theme: "outline",
        size: "large",
        width: 300,
        text: "continue_with",
      });
    };

    if (window.google) {
      mountButton();
    } else {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.onload = mountButton;
      document.head.appendChild(script);
    }
  }, [signInWithGoogle, onComplete]);

  const handleSendOtp = async () => {
    if (!email.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await sendEmailOtp(email.trim());
      setEmailStep("otp");
    } catch {
      setError("Failed to send code. Check the email address.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async () => {
    if (!otp.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await verifyEmailOtp(email.trim(), otp.trim());
      onComplete();
    } catch {
      setError("Wrong code. Try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-sm mx-auto">
      <div className="text-center">
        <div className="text-4xl mb-3">🔒</div>
        <h2 className="text-2xl font-bold mb-2">Save your shelf</h2>
        <p className="text-sm opacity-70">Sign in to save your goals, skin profile, and product shelf — free forever.</p>
      </div>

      {error && (
        <div className="text-xs bg-red-50 text-red-600 px-4 py-2 rounded-xl text-center">{error}</div>
      )}

      {mode === "choose" && (
        <div className="flex flex-col gap-3">
          {/* Google button */}
          <div className="flex justify-center">
            <div ref={googleButtonRef} />
          </div>

          <div className="flex items-center gap-3 my-1">
            <div className="flex-1 h-px bg-gray-200" />
            <span className="text-xs opacity-40">or</span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>

          <button
            onClick={() => setMode("email")}
            className="w-full py-3 rounded-xl border text-sm font-semibold transition-all bg-white/60 hover:shadow-sm"
            style={{ borderColor: theme.borderColor }}
          >
            Continue with email
          </button>
        </div>
      )}

      {mode === "email" && emailStep === "email" && (
        <div className="flex flex-col gap-3">
          <input
            autoFocus
            type="email"
            placeholder="your@email.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSendOtp()}
            className="w-full text-sm px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:border-gray-400 bg-white/80"
          />
          <button
            onClick={handleSendOtp}
            disabled={loading || !email.trim()}
            className="w-full py-3 rounded-xl font-semibold text-sm transition-all disabled:opacity-50"
            style={{ backgroundColor: theme.accentColor, color: theme.textOnAccent }}
          >
            {loading ? "Sending..." : "Send code"}
          </button>
          <button onClick={() => setMode("choose")} className="text-xs opacity-50 text-center">
            ← Back
          </button>
        </div>
      )}

      {mode === "email" && emailStep === "otp" && (
        <div className="flex flex-col gap-3">
          <p className="text-xs opacity-60 text-center">Enter the 6-digit code sent to <strong>{email}</strong></p>
          <input
            autoFocus
            type="text"
            inputMode="numeric"
            maxLength={6}
            placeholder="000000"
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
            onKeyDown={(e) => e.key === "Enter" && otp.length === 6 && handleVerifyOtp()}
            className="w-full text-center text-2xl tracking-[0.5em] font-bold py-4 rounded-xl border border-gray-200 focus:outline-none focus:border-gray-400 bg-white/80"
          />
          <button
            onClick={handleVerifyOtp}
            disabled={loading || otp.length !== 6}
            className="w-full py-3 rounded-xl font-semibold text-sm transition-all disabled:opacity-50"
            style={{ backgroundColor: theme.accentColor, color: theme.textOnAccent }}
          >
            {loading ? "Verifying..." : "Sign in"}
          </button>
          <button onClick={() => { setEmailStep("email"); setOtp(""); }} className="text-xs opacity-50 text-center">
            Resend code
          </button>
        </div>
      )}
    </div>
  );
}
