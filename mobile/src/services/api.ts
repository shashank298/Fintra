import axios from "axios";
import * as SecureStore from "expo-secure-store";

const API_BASE_URL = "https://yourapp.railway.app";

const api = axios.create({ baseURL: API_BASE_URL });

api.interceptors.request.use(async (config) => {
  const token = await SecureStore.getItemAsync("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh = await SecureStore.getItemAsync("refresh_token");
      if (refresh) {
        try {
          const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refresh,
          });
          await SecureStore.setItemAsync("access_token", data.access_token);
          error.config.headers.Authorization = `Bearer ${data.access_token}`;
          return api.request(error.config);
        } catch {
          await SecureStore.deleteItemAsync("access_token");
          await SecureStore.deleteItemAsync("refresh_token");
        }
      }
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  signup: (email: string, password: string) =>
    api.post("/auth/signup", { email, password }),
  login: (email: string, password: string) =>
    api.post("/auth/login", { email, password }),
  refresh: (refresh_token: string) =>
    api.post("/auth/refresh", { refresh_token }),
  logout: (refresh_token: string) =>
    api.post("/auth/logout", { refresh_token }),
  me: () => api.get("/auth/me"),
};

export const splitwiseApi = {
  getConnectUrl: () => api.get("/splitwise/connect"),
  getStatus: () => api.get("/splitwise/status"),
  getGroups: () => api.get("/splitwise/groups"),
};

export const gmailApi = {
  getConnectUrl: () => api.get("/gmail/connect"),
  getStatus: () => api.get("/gmail/status"),
};

export const telegramApi = {
  getStatus: () => api.get("/telegram/status"),
};

export const transactionsApi = {
  list: (limit = 20) => api.get(`/transactions?limit=${limit}`),
};

export const receiptApi = {
  upload: (formData: FormData) =>
    api.post("/receipt/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
};

export default api;
