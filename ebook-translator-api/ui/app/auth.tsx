"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";
import { getSupabaseClient } from "../lib/supabase";

const TOKEN_STORAGE_KEY = "ebook_translator_token";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  status: AuthStatus;
  session: Session | null;
  accessToken: string | null;
  signOut: () => Promise<void>;
};

type AuthProviderProps = {
  children: ReactNode;
};

type UseRequireAuthOptions = {
  redirectTo?: string;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function syncLegacyToken(session: Session | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (session?.access_token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, session.access_token);
    return;
  }

  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export function AuthProvider({ children }: AuthProviderProps) {
  const router = useRouter();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [session, setSession] = useState<Session | null>(null);

  const applySession = useCallback((nextSession: Session | null) => {
    syncLegacyToken(nextSession);
    setSession(nextSession);
    setStatus(nextSession ? "authenticated" : "unauthenticated");
  }, []);

  useEffect(() => {
    let mounted = true;
    const supabase = getSupabaseClient();

    const safeApplySession = (nextSession: Session | null) => {
      if (!mounted) {
        return;
      }
      applySession(nextSession);
    };

    const initializeSession = async () => {
      try {
        const sessionResult = await supabase.auth.getSession();
        if (sessionResult.error) {
          safeApplySession(null);
          return;
        }
        safeApplySession(sessionResult.data.session ?? null);
      } catch {
        safeApplySession(null);
      }
    };

    void initializeSession();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event: unknown, nextSession: Session | null) => {
      safeApplySession(nextSession ?? null);
    });

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, [applySession]);

  const signOut = useCallback(async () => {
    const supabase = getSupabaseClient();
    try {
      await supabase.auth.signOut();
    } finally {
      applySession(null);
      router.replace("/login");
    }
  }, [applySession, router]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      session,
      accessToken: session?.access_token ?? null,
      signOut,
    }),
    [session, signOut, status],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return context;
}

export function useRequireAuth(options: UseRequireAuthOptions = {}) {
  const { redirectTo = "/login" } = options;
  const auth = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace(redirectTo);
    }
  }, [auth.status, redirectTo, router]);

  return auth;
}
