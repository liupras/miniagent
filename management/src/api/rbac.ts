import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export interface PageResult<T> {
  total: number;
  page: number;
  page_size: number;
  data: T[];
}

export interface UserItem {
  id: number;
  username: string;
  nickname?: string | null;
  avatar?: string | null;
  is_active: boolean;
  created_at: string;
  last_login?: string | null;
  failed_login_attempts: number;
  locked_until?: string | null;
  is_locked: boolean;
  roles: string[];
  permissions: string[];
}

export interface UserListParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  username?: string;
  is_active?: boolean;
  role_id?: number;
}

export interface PasswordPolicy {
  min_length: number;
  require_upper: boolean;
  require_lower: boolean;
  require_digit: boolean;
  require_special: boolean;
}

export interface UserCreatePayload {
  username: string;
  password: string;
  nickname?: string | null;
  avatar?: string | null;
  is_active: boolean;
  role_ids: number[];
}

export interface UserUpdatePayload {
  username?: string;
  nickname?: string | null;
  avatar?: string | null;
  is_active?: boolean;
}

export interface RoleOption {
  id: number;
  code: string;
  name: string;
  is_super: boolean;
}

export interface RoleItem extends RoleOption {
  description?: string | null;
  menu_ids: number[];
  user_count: number;
}

export interface RoleCreatePayload {
  code: string;
  name: string;
  description?: string | null;
  is_super: boolean;
  menu_ids: number[];
}

export type RoleUpdatePayload = Partial<Omit<RoleCreatePayload, "menu_ids">>;

export type MenuType = "menu" | "button";

export interface MenuItem {
  id: number;
  parent_id?: number | null;
  name: string;
  title_key: string;
  path?: string | null;
  component?: string | null;
  icon?: string | null;
  sort_order: number;
  menu_type: MenuType;
  description?: string | null;
  is_visible: boolean;
  is_active: boolean;
  created_at: string;
  children: MenuItem[];
}

export interface MenuUpdatePayload {
  parent_id?: number | null;
  name?: string;
  title_key?: string;
  path?: string | null;
  component?: string | null;
  icon?: string | null;
  sort_order?: number;
  menu_type?: MenuType;
  description?: string | null;
  is_visible?: boolean;
  is_active?: boolean;
}

export const getUserList = (params: UserListParams) =>
  http.request<PageResult<UserItem>>("get", baseUrlApi("admin/users"), {
    params
  });

export const getPasswordPolicy = () =>
  http.request<PasswordPolicy>("get", baseUrlApi("password-policy"));

export const createUser = (data: UserCreatePayload) =>
  http.request<UserItem>("post", baseUrlApi("admin/users"), { data });

export const updateUser = (id: number, data: UserUpdatePayload) =>
  http.request<UserItem>("patch", baseUrlApi(`admin/users/${id}`), {
    data
  });

export const updateUserRoles = (id: number, roleIds: number[]) =>
  http.request<UserItem>("put", baseUrlApi(`admin/users/${id}/roles`), {
    data: { role_ids: roleIds }
  });

export const resetUserPassword = (id: number, password: string) =>
  http.request<void>("put", baseUrlApi(`admin/users/${id}/password`), {
    data: { password }
  });

export const unlockUser = (id: number) =>
  http.request<void>("put", baseUrlApi(`admin/users/${id}/unlock`));

export const deleteUser = (id: number) =>
  http.request<void>("delete", baseUrlApi(`admin/users/${id}`));

export const getRoleOptions = () =>
  http.request<RoleOption[]>("get", baseUrlApi("admin/roles/options"));

export const getRoleList = (params: {
  page?: number;
  page_size?: number;
  keyword?: string;
}) =>
  http.request<PageResult<RoleItem>>("get", baseUrlApi("admin/roles"), {
    params
  });

export const createRole = (data: RoleCreatePayload) =>
  http.request<RoleItem>("post", baseUrlApi("admin/roles"), { data });

export const updateRole = (id: number, data: RoleUpdatePayload) =>
  http.request<RoleItem>("patch", baseUrlApi(`admin/roles/${id}`), {
    data
  });

export const updateRoleMenus = (id: number, menuIds: number[]) =>
  http.request<RoleItem>("put", baseUrlApi(`admin/roles/${id}/menus`), {
    data: { menu_ids: menuIds }
  });

export const deleteRole = (id: number) =>
  http.request<void>("delete", baseUrlApi(`admin/roles/${id}`));

export const getMenuList = (params?: {
  tree?: boolean;
  menu_type?: MenuType;
  is_active?: boolean;
}) => http.request<MenuItem[]>("get", baseUrlApi("admin/menus"), { params });

export const getMenuById = (id: number) =>
  http.request<MenuItem>("get", baseUrlApi(`admin/menus/${id}`));

export const updateMenu = (id: number, data: MenuUpdatePayload) =>
  http.request<MenuItem>("patch", baseUrlApi(`admin/menus/${id}`), { data });
