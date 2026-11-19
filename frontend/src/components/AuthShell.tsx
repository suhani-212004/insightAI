export function AuthShell({ title, children, footer }: { title: string; children: React.ReactNode; footer: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-lg font-bold text-white">i</div>
          <h1 className="text-xl font-semibold">{title}</h1>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">{children}</div>
        <p className="mt-4 text-center text-sm text-slate-500">{footer}</p>
      </div>
    </main>
  );
}
