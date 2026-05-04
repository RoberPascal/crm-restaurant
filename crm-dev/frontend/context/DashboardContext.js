// context/DashboardContext.jsx
"use client";

import {
  createContext,
  useContext,
  useReducer,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { getMoscowStartOfDay } from "@/utils/date";
import { api } from "@/utils/api";

// ОПТИМИЗАЦИЯ: логирование ошибок только в dev-режиме
const IS_DEV = process.env.NODE_ENV === "development";
const debugError = IS_DEV ? console.error.bind(console) : () => {};

const DashboardContext = createContext();

const initialState = (user) => ({
  selectedRestaurantSlug: null,
  selectedRestaurantId: null,
  selectedDate: getMoscowStartOfDay(),
  searchQuery: "",
  statusFilter: "all",
  bookings: [],
  restaurants: [],
  user: user || null,
  loading: false,
  error: null,
});

function dashboardReducer(state, action) {
  switch (action.type) {
    case "SET_RESTAURANT":
      if (state.selectedRestaurantSlug === action.payload.slug) return state;
      return {
        ...state,
        selectedRestaurantSlug: action.payload.slug,
        selectedRestaurantId: action.payload.id ?? state.selectedRestaurantId,
        searchQuery: "",
        statusFilter: "all",
      };
    case "SET_DATE":
      if (state.selectedDate.getTime() === action.payload.getTime())
        return state;
      return { ...state, selectedDate: action.payload };
    case "SET_SEARCH":
      return { ...state, searchQuery: action.payload };
    case "SET_STATUS_FILTER":
      return { ...state, statusFilter: action.payload };
    case "SET_BOOKINGS":
      if (Array.isArray(action.payload)) {
        return { ...state, bookings: action.payload };
      }
      if (typeof action.payload === "function") {
        const newBookings = action.payload(state.bookings);
        return {
          ...state,
          bookings: Array.isArray(newBookings) ? newBookings : state.bookings,
        };
      }
      console.warn("Некорректный payload для SET_BOOKINGS:", action.payload);
      return state;
    case "SET_LOADING":
      return { ...state, loading: action.payload };
    case "SET_ERROR":
      return { ...state, error: action.payload };
    case "SET_USER":
      return { ...state, user: action.payload };
    case "SET_RESTAURANTS":
      return { ...state, restaurants: action.payload };
    case "CLEAR_DATA":
      return {
        ...initialState(state.user),
        restaurants: state.restaurants,
        user: state.user,
      };
    default:
      return state;
  }
}

export function DashboardProvider({ children, user }) {
  const [state, dispatch] = useReducer(dashboardReducer, initialState(user));
  const initializedRef = useRef(false);
  const userRef = useRef(user);
  const bookingsRef = useRef(state.bookings);

  useEffect(() => {
    bookingsRef.current = state.bookings;
  }, [state.bookings]);

  const loadRestaurants = useCallback(async () => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    dispatch({ type: "SET_LOADING", payload: true });
    try {
      const response = await api.get("/api/v1/admin/user/restaurants");

      // ИСПРАВЛЕНИЕ: правильная обработка ответа API
      let restaurants = [];

      if (Array.isArray(response)) {
        restaurants = response;
      } else if (response && typeof response === "object") {
        // Проверяем различные возможные структуры ответа
        if (Array.isArray(response.data)) {
          restaurants = response.data;
        } else if (Array.isArray(response.restaurants)) {
          restaurants = response.restaurants;
        } else if (response.data && typeof response.data === "object") {
          // Если data - объект, извлекаем массив
          const data = response.data;
          if (Array.isArray(data.restaurants)) {
            restaurants = data.restaurants;
          } else if (Array.isArray(data.data)) {
            restaurants = data.data;
          }
        }
      }

      if (!Array.isArray(restaurants)) {
        debugError("Invalid restaurants format:", response);
        restaurants = [];
      }

      dispatch({ type: "SET_RESTAURANTS", payload: restaurants });

      let slugToUse = null;
      const savedSlug =
        (typeof window !== "undefined" &&
          localStorage.getItem("selectedRestaurantSlug")) ||
        null;

      if (savedSlug && restaurants.some((r) => r.slug === savedSlug)) {
        slugToUse = savedSlug;
      } else if (restaurants.length > 0) {
        slugToUse = restaurants[0].slug;
      }

      if (slugToUse) {
        const restaurant = restaurants.find((r) => r.slug === slugToUse);
        if (restaurant) {
          dispatch({
            type: "SET_RESTAURANT",
            payload: { slug: restaurant.slug, id: restaurant.id },
          });
          if (typeof window !== "undefined") {
            localStorage.setItem("selectedRestaurantSlug", restaurant.slug);
          }
        }
      }
    } catch (error) {
      debugError("Error loading restaurants:", error);
      dispatch({
        type: "SET_ERROR",
        payload: error.message || "Ошибка загрузки ресторанов",
      });
    } finally {
      dispatch({ type: "SET_LOADING", payload: false });
    }
  }, []);

  useEffect(() => {
    if (user && !initializedRef.current) {
      loadRestaurants();
    }
  }, [user, loadRestaurants]);

  useEffect(() => {
    if (user && user !== userRef.current) {
      userRef.current = user;
      dispatch({ type: "SET_USER", payload: user });
    }
  }, [user]);

  const actions = useMemo(
    () => ({
      setRestaurant: (restaurant) => {
        dispatch({
          type: "SET_RESTAURANT",
          payload: { slug: restaurant.slug, id: restaurant.id },
        });
        if (typeof window !== "undefined" && restaurant.slug) {
          localStorage.setItem("selectedRestaurantSlug", restaurant.slug);
        }
      },
      setDate: (date) => {
        dispatch({ type: "SET_DATE", payload: date });
        if (typeof window !== "undefined") {
          localStorage.setItem("selectedDate", date.toISOString());
        }
      },
      setSearch: (query) => dispatch({ type: "SET_SEARCH", payload: query }),
      setStatusFilter: (filter) =>
        dispatch({ type: "SET_STATUS_FILTER", payload: filter }),

      updateBookings: (bookingsOrFn) => {
        if (typeof bookingsOrFn === "function") {
          const newBookings = bookingsOrFn(bookingsRef.current);
          dispatch({ type: "SET_BOOKINGS", payload: newBookings });
        } else if (Array.isArray(bookingsOrFn)) {
          dispatch({ type: "SET_BOOKINGS", payload: bookingsOrFn });
        } else {
          debugError("Invalid updateBookings:", bookingsOrFn);
        }
      },

      setLoading: (loading) =>
        dispatch({ type: "SET_LOADING", payload: loading }),
      setError: (error) => dispatch({ type: "SET_ERROR", payload: error }),
      setUser: (user) => dispatch({ type: "SET_USER", payload: user }),
      setRestaurants: (restaurants) =>
        dispatch({ type: "SET_RESTAURANTS", payload: restaurants }),
      clearData: () => {
        initializedRef.current = false;
        dispatch({ type: "CLEAR_DATA" });
      },
      loadRestaurants,
    }),
    [dispatch, loadRestaurants],
  );

  const contextValue = useMemo(() => {
    const isAdmin = state.user?.role === "admin";
    const isOperator = state.user?.role === "operator" || isAdmin;

    return {
      ...state,
      ...actions,
      isAdmin,
      isOperator,
      canCreateBooking: isAdmin || isOperator,
    };
  }, [
    // Only re-create context when meaningful fields change
    // This prevents re-renders on transient loading/error toggles
    state.selectedRestaurantSlug,
    state.selectedRestaurantId,
    state.selectedDate,
    state.searchQuery,
    state.statusFilter,
    state.bookings,
    state.restaurants,
    state.user,
    state.loading,
    state.error,
    actions,
  ]);

  return (
    <DashboardContext.Provider value={contextValue}>
      {children}
    </DashboardContext.Provider>
  );
}

export const useDashboard = () => {
  const ctx = useContext(DashboardContext);
  if (!ctx)
    throw new Error("useDashboard must be used within DashboardProvider");
  return ctx;
};
