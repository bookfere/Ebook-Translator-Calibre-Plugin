import "./globals.css";
import type { Metadata } from "next";
import { AuthProvider } from "./auth";
import { AuthHeader } from "../components/auth-header";

export const metadata: Metadata = {
  title: "Ebook Translator Admin",
  description: "Admin UI for Ebook Translator SaaS",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <AuthHeader />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
