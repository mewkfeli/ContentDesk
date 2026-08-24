"use client";

import { useEffect, useState } from "react";

type Toast = { id: number; message: string; tone?: "success" | "error" | "info" };

export function showToast(message: string, tone: Toast["tone"] = "success") {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("contentdesk:toast", { detail: { message, tone } }));
}

export function ToastProvider() {
  const [items, setItems] = useState<Toast[]>([]);
  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ message: string; tone?: Toast["tone"] }>;
      const id = Date.now() + Math.floor(Math.random() * 1000);
      const toast = { id, message: custom.detail.message, tone: custom.detail.tone ?? "success" };
      setItems((prev) => [...prev.slice(-3), toast]);
      setTimeout(() => setItems((prev) => prev.filter((x) => x.id !== id)), 3200);
    };
    window.addEventListener("contentdesk:toast", handler);
    return () => window.removeEventListener("contentdesk:toast", handler);
  }, []);
  return <div className="toastStack" aria-live="polite">{items.map((item) => <div key={item.id} className={`toast ${item.tone ?? "success"}`}>{item.message}</div>)}</div>;
}
