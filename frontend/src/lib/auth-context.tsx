"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { api, type UserProfile } from "./api";
import { getToken, setToken, clearToken } from "./auth";

export interface AuthUser {
  id: number;
  name: string | null;
  theme_slug: string;
  onboarding_step: string | null;
  goals: Record<string, string[]>;
  skin_profile: Record<string, unknown>;
  selected_agent_slugs: string[];
}

interface AuthContext {
  user: AuthUser | null;
  loading: boolean;
  signInWithGoogle: (credential: string) => Promise<{ is_new_user: boolean }>;
  sendEmailOtp: (email: string) => Promise<void>;
  verifyEmailOtp: (email: string, otp: string) => Promise<{ is_new_user: boolean }>;
  updateProfile: (data: Partial<AuthUser & { onboarding_step: string }>) => Promise<void>;
  signOut: () => void;
}

const Ctx = createContext<AuthContext | null>(null);

function profileToAuthUser(profile: UserProfile): AuthUser {
  return {
    id: profile.id,
    name: profile.name ?? null,
    theme_slug: profile.theme_slug,
    onboarding_step: profile.onboarding_step ?? null,
    goals: (profile.goals as Record<string, string[]>) || {},
    skin_profile: profile.skin_profile || {},
    selected_agent_slugs: profile.selected_agent_slugs || [],
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async (): Promise<AuthUser | null> => {
    const token = getToken();
    if (!token) { setLoading(false); return null; }
    try {
      const profile = await api.auth.me(token);
      const u = profileToAuthUser(profile);
      setUser(u);
      return u;
    } catch {
      clearToken();
      setLoading(false);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadUser(); }, [loadUser]);

  const signInWithGoogle = async (credential: string): Promise<{ is_new_user: boolean }> => {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/auth/google`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential }),
    });
    if (!res.ok) throw new Error("Google sign-in failed");
    const data = await res.json();
    setToken(data.access_token);
    const u = await loadUser();
    if (!data.is_new_user && u?.onboarding_step === "complete") {
      toast(`Welcome back${u?.name ? `, ${u.name.split(" ")[0]}` : ""}!`);
    }
    return { is_new_user: data.is_new_user };
  };

  const sendEmailOtp = async (email: string) => {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/auth/email/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error("Failed to send OTP");
  };

  const verifyEmailOtp = async (email: string, otp: string): Promise<{ is_new_user: boolean }> => {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/auth/email/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, otp }),
    });
    if (!res.ok) throw new Error("Invalid OTP");
    const data = await res.json();
    setToken(data.access_token);
    const u = await loadUser();
    if (!data.is_new_user && u?.onboarding_step === "complete") {
      toast(`Welcome back${u?.name ? `, ${u.name.split(" ")[0]}` : ""}!`);
    }
    return { is_new_user: data.is_new_user };
  };

  const updateProfile = async (data: Partial<AuthUser & { onboarding_step: string }>) => {
    const token = getToken();
    if (!token) return;
    const updated = await api.auth.updateMe(token, data as Parameters<typeof api.auth.updateMe>[1]);
    setUser(profileToAuthUser(updated));
  };

  const signOut = () => {
    clearToken();
    setUser(null);
  };

  return (
    <Ctx.Provider value={{ user, loading, signInWithGoogle, sendEmailOtp, verifyEmailOtp, updateProfile, signOut }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
