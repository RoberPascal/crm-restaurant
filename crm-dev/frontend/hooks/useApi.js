// hooks/useApi.js
import { useState, useCallback, useRef, useEffect } from "react";

export const useApi = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const callApi = useCallback(
    async (apiCall, successCallback, errorCallback) => {
      setLoading(true);
      setError(null);

      try {
        const result = await apiCall();
        if (!mountedRef.current) return result;
        if (successCallback) {
          successCallback(result);
        }
        return result;
      } catch (err) {
        if (!mountedRef.current) throw err;
        const errorMessage = err.message || "Произошла ошибка";
        setError(errorMessage);
        if (errorCallback) {
          errorCallback(errorMessage);
        }
        throw err;
      } finally {
        if (mountedRef.current) {
          setLoading(false);
        }
      }
    },
    [],
  );

  return { loading, error, callApi, setError };
};
