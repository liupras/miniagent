import type { LoginResponse } from "../types/auth";
import { http } from "./http";

export async function loginApi(username: string, password: string) {
  const response = await http.post<LoginResponse>("/api/v1/login", {
    username,
    password,
  });
  return response.data;
}
