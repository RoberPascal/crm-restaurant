// app/admin/page.jsx
"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import Header from "@/components/Header/Header";
import { DashboardProvider } from "@/context/DashboardContext";
import { api } from "@/utils/api";

// Динамический импорт для избежания проблем с инициализацией
const AdminPanel = dynamic(() => import("@/components/AdminPanel/AdminPanel"), {
  ssr: false,
  loading: () => (
    <div style={{ display: "flex", justifyContent: "center", padding: "20px" }}>
      <span>Загрузка панели...</span>
    </div>
  ),
});

const Spinner = () => (
  <div>
    <svg width="24" height="24" viewBox="0 0 24 24">
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="2"
        fill="none"
        strokeDasharray="15"
      />
    </svg>
  </div>
);

export default function AdminPage() {
  const [isAuthenticated, setIsAuthenticated] = useState(null);
  const [user, setUser] = useState(null);
  const router = useRouter();
  const authCheckRef = useRef(false);

  useEffect(() => {
    if (authCheckRef.current) return;
    authCheckRef.current = true;

    const checkAuth = async () => {
      try {
        const userData = await api.get("/api/v1/admin/auth/me");

        if (userData.role !== "admin") {
          setIsAuthenticated(false);
          router.push("/");
          return;
        }

        setIsAuthenticated(true);
        setUser(userData);
      } catch (error) {
        console.error("Admin auth check failed:", error);
        setIsAuthenticated(false);
        router.push("/login");
      }
    };

    checkAuth();
  }, [router]);

  if (isAuthenticated === null) {
    return (
      <div>
        <Spinner />
        <span>Проверка авторизации...</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <DashboardProvider user={user}>
      <Header />
      <AdminPanel />
    </DashboardProvider>
  );
}
