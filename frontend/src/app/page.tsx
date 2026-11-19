"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading) router.replace(user ? "/dashboards" : "/login");
  }, [user, loading, router]);
  return <div className="flex h-screen items-center justify-center"><Spinner /></div>;
}
