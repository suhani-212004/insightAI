"use client";

import clsx from "clsx";
import { X } from "lucide-react";
import { useEffect } from "react";

export function Button({
  variant = "primary", size = "md", className, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md" }) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3.5 py-2 text-sm",
        variant === "primary" && "bg-brand-600 text-white hover:bg-brand-700",
        variant === "secondary" && "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800",
        variant === "ghost" && "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-700",
        className,
      )}
    />
  );
}

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx("field", className)} />;
}

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={clsx("field", className)} />;
}

export function Label({ children, text }: { children: React.ReactNode; text: string }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-slate-600 dark:text-slate-400">{text}</span>
      {children}
    </label>
  );
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={clsx("rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900", className)} />;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Badge({ children, tone = "slate" }: { children: React.ReactNode; tone?: "slate" | "blue" | "green" | "amber" | "red" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    blue: "bg-brand-50 text-brand-700 dark:bg-brand-700/20 dark:text-brand-100",
    green: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
    amber: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
    red: "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300",
  };
  return <span className={clsx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", tones[tone])}>{children}</span>;
}

export function ErrorText({ error }: { error: string | null }) {
  if (!error) return null;
  return <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>;
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center dark:border-slate-700">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-2 text-sm text-slate-500">{children}</div>}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/50 p-4 sm:p-10" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-label={title}
        className={clsx("w-full rounded-2xl bg-white p-5 shadow-xl dark:bg-slate-900", wide ? "max-w-5xl" : "max-w-lg")}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Spinner() {
  return <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600" aria-label="Loading" />;
}
