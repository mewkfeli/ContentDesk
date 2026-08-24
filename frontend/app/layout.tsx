import type { Metadata } from "next";
import { Sidebar } from "@/components/sidebar";
import { GlobalShortcuts } from "@/components/global-shortcuts";
import { ToastProvider } from "@/components/toast-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "ContentDesk",
  description: "Content & SEO workspace",
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/icon.png",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body><GlobalShortcuts /><ToastProvider /><div className="shell"><Sidebar /><main className="main">{children}</main></div></body></html>;
}
