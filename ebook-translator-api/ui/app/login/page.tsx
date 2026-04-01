"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../auth";
import { getSupabaseClient } from "../../lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const { status } = useAuth();

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/jobs");
    }
  }, [router, status]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(mode === "signin" ? "Signing in..." : "Creating account...");

    try {
      const supabase = getSupabaseClient();
      const { data, error } =
        mode === "signin"
          ? await supabase.auth.signInWithPassword({ email, password })
          : await supabase.auth.signUp({ email, password });

      if (error) {
        setMessage(error.message);
        return;
      }

      if (data.session?.access_token) {
        setMessage(mode === "signin" ? "Signed in. Redirecting to jobs..." : "Account created. Redirecting to jobs...");
        router.replace("/jobs");
        return;
      }

      if (mode === "signup") {
        setMessage("Account created. Check your email if confirmation is enabled, then sign in.");
        return;
      }

      const { data: sessionData, error: sessionError } = await supabase.auth.getSession();
      if (sessionError) {
        setMessage(sessionError.message);
        return;
      }

      if (sessionData.session?.access_token) {
        setMessage("Signed in. Redirecting to jobs...");
        router.replace("/jobs");
        return;
      }

      setMessage("No active session returned.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  if (status === "loading") {
    return (
      <main>
        <div className="card" style={{ maxWidth: 460 }}>
          <h1>Sign In</h1>
          <p className="hint">Checking your session...</p>
        </div>
      </main>
    );
  }

  if (status === "authenticated") {
    return (
      <main>
        <div className="card" style={{ maxWidth: 460 }}>
          <h1>Sign In</h1>
          <p className="hint">Redirecting to jobs...</p>
        </div>
      </main>
    );
  }

  return (
    <main>
      <div className="card" style={{ maxWidth: 460 }}>
        <h1>{mode === "signin" ? "Sign In" : "Sign Up"}</h1>
        <div className="tab-row" style={{ marginBottom: 18 }}>
          <button
            type="button"
            className={mode === "signin" ? "pill-tab active" : "pill-tab"}
            onClick={() => {
              setMode("signin");
              setMessage("");
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            className={mode === "signup" ? "pill-tab active" : "pill-tab"}
            onClick={() => {
              setMode("signup");
              setMessage("");
            }}
          >
            Sign Up
          </button>
        </div>
        <form onSubmit={onSubmit}>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <div style={{ height: 12 }} />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <div style={{ height: 18 }} />
          <button type="submit">{mode === "signin" ? "Sign In" : "Create Account"}</button>
        </form>
        <p className="hint" style={{ marginTop: 12 }}>
          This page uses Supabase Auth. Email confirmation behavior depends on your Supabase project settings.
        </p>
        <p style={{ marginTop: 14 }}>{message}</p>
      </div>
    </main>
  );
}
