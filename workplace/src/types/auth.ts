export interface AuthUser {
  avatar?: string | null;
  username?: string | null;
  nickname?: string | null;
  roles: string[];
  permissions: string[];
}

export interface AuthSession extends AuthUser {
  accessToken: string;
  refreshToken: string;
  expires: string;
}

export interface LoginResponse {
  success: boolean;
  data: AuthSession | null;
  error_code?: string | null;
  message?: string | null;
  locked_until?: string | null;
}

export interface RefreshResponse {
  success: boolean;
  data: Pick<AuthSession, "accessToken" | "refreshToken" | "expires"> | null;
  error_code?: string | null;
  message?: string | null;
}
