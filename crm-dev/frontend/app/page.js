// app/page.js
"use client";

import { DashboardProvider } from "@/context/DashboardContext";
import Header from "@/components/Header/Header";
import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/utils/api";
import dynamic from "next/dynamic";

// Динамический импорт Dashboard для избежания проблем с инициализацией
const Dashboard = dynamic(() => import("@/components/Dashboard/Dashboard"), {
  ssr: false,
  loading: () => (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        padding: "40px",
        fontSize: "1.2rem",
        color: "#555",
      }}
    >
      Загрузка дашборда...
    </div>
  ),
});

export default function HomePage() {
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

        setIsAuthenticated(true);
        setUser(userData);
      } catch (error) {
        console.error("Auth check failed:", error);
        setIsAuthenticated(false);
        router.push("/login");
      }
    };

    checkAuth();
  }, [router]);

  if (isAuthenticated === null) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "100vh",
          fontSize: "1.2rem",
          color: "#555",
        }}
      >
        Проверка авторизации...
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  // Убеждаемся, что user загружен перед рендером Dashboard
  if (!user) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "100vh",
          fontSize: "1.2rem",
          color: "#555",
        }}
      >
        Загрузка данных пользователя...
      </div>
    );
  }

  return (
    <DashboardProvider user={user}>
      <div
        style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}
      >
        <Header />
        <main style={{ flex: 1 }}>
          <Dashboard />
        </main>
      </div>
    </DashboardProvider>
  );
}
