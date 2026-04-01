"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "../app/auth";

export function AuthHeader() {
  const { status, signOut } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    if (signingOut) {
      return;
    }

    setSigningOut(true);
    try {
      await signOut();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/">Home</Link>

        {status === "unauthenticated" && (
          <>
            <Link href="/login">Login</Link>
            <Link href="/login">Sign Up</Link>
          </>
        )}

        {status === "authenticated" && (
          <>
            <Link href="/new-job">New Job</Link>
            <Link href="/jobs">Jobs</Link>
            <button type="button" className="topbar-link-button" onClick={() => void handleSignOut()} disabled={signingOut}>
              {signingOut ? "Logging out..." : "Logout"}
            </button>
          </>
        )}
      </div>
    </header>
  );
}
