"use client";

import Link from "next/link";
import { useAuth } from "./auth";

export default function HomePage() {
  const { status } = useAuth();

  return (
    <main>
      <div className="card">
        <h1>Ebook Translator Admin</h1>
        <p>This UI uses Supabase authentication and calls the FastAPI backend.</p>

        {status === "loading" && <p className="hint">Checking your session...</p>}

        {status === "unauthenticated" && (
          <p>
            1. Sign in or sign up from <Link href="/login">/login</Link>.
            <br />
            2. After login, you can create jobs and review them from the protected pages.
          </p>
        )}

        {status === "authenticated" && (
          <p>
            1. Create translation jobs from <Link href="/new-job">/new-job</Link>.
            <br />
            2. Inspect and review jobs from <Link href="/jobs">/jobs</Link>.
          </p>
        )}
      </div>
    </main>
  );
}
