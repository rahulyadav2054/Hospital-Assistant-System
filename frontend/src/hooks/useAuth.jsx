import { createContext, useContext, useState } from "react";
import { api } from "../api/client.js";

const AuthContext = createContext(null);

function storedUser() {
  try {
    return JSON.parse(sessionStorage.getItem("user"));
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(storedUser);

  async function login(username, password) {
    const data = await api("/auth/login", { method: "POST", body: { username, password } });
    sessionStorage.setItem("token", data.access_token);
    sessionStorage.setItem("user", JSON.stringify(data.user));
    setUser(data.user);
  }

  function logout() {
    sessionStorage.clear();
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
