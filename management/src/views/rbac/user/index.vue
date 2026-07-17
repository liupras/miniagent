<template>
  <div class="main">
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] pl-8 pt-3 overflow-auto"
    >
      <el-form-item :label="t('rbac.user.keyword')" prop="keyword">
        <el-input
          v-model="searchForm.keyword"
          :placeholder="t('rbac.user.keywordPlaceholder')"
          clearable
          class="w-48!"
          @keyup.enter="onSearch"
        />
      </el-form-item>
      <el-form-item :label="t('rbac.role.label')" prop="role_id">
        <el-select
          v-model="searchForm.role_id"
          :placeholder="t('rbac.role.all')"
          clearable
          class="w-44!"
        >
          <el-option
            v-for="role in roleOptions"
            :key="role.id"
            :label="`${role.name} (${role.code})`"
            :value="role.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('labels.status')" prop="is_active">
        <el-select
          v-model="searchForm.is_active"
          :placeholder="t('search.status.placeholder')"
          clearable
          class="w-36!"
        >
          <el-option :label="t('buttons.active')" :value="true" />
          <el-option :label="t('buttons.inactive')" :value="false" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :icon="Search" @click="onSearch">
          {{ t("buttons.search") }}
        </el-button>
        <el-button :icon="Refresh" @click="onReset">
          {{ t("buttons.reset") }}
        </el-button>
      </el-form-item>
    </el-form>

    <PureTableBar
      :title="t('rbac.user.title')"
      :columns="columns"
      @refresh="fetchData"
    >
      <template #buttons>
        <el-button
          v-auth="'user:add'"
          type="primary"
          :icon="Plus"
          @click="openDialog('add')"
        >
          {{ t("buttons.add") }}
        </el-button>
      </template>
      <template #default="{ size, dynamicColumns }">
        <pure-table
          row-key="id"
          :data="tableData"
          :columns="dynamicColumns"
          :size="size"
          :loading="loading"
          :pagination="pagination"
          :paginationSmall="true"
          align-whole="center"
          @page-size-change="handleSizeChange"
          @page-current-change="handleCurrentChange"
        >
          <template #user="{ row }">
            <div class="flex items-center gap-2">
              <el-avatar :size="30" :src="row.avatar || undefined">
                {{ (row.nickname || row.username).slice(0, 1).toUpperCase() }}
              </el-avatar>
              <div class="min-w-0 text-left">
                <div class="truncate font-medium">{{ row.username }}</div>
                <div class="truncate text-xs text-gray-400">
                  {{ row.nickname || t("rbac.common.notSet") }}
                </div>
              </div>
            </div>
          </template>
          <template #roles="{ row }">
            <div class="flex flex-wrap justify-center gap-1">
              <el-tag
                v-for="code in row.roles"
                :key="code"
                :type="code === 'admin' ? 'danger' : 'info'"
                size="small"
                effect="plain"
              >
                {{ roleName(code) }}
              </el-tag>
              <span v-if="!row.roles.length" class="text-gray-400">—</span>
            </div>
          </template>
          <template #is_active="{ row }">
            <el-switch
              v-model="row.is_active"
              v-auth="'user:edit'"
              :loading="row._statusLoading"
              @change="changeStatus(row)"
            />
          </template>
          <template #operation="{ row }">
            <el-button
              v-auth="'user:edit'"
              type="primary"
              link
              :icon="EditPen"
              @click="openDialog('edit', row)"
            >
              {{ t("buttons.edit") }}
            </el-button>
            <el-button
              v-auth="'user:edit'"
              type="warning"
              link
              :icon="Key"
              @click="openPasswordDialog(row)"
            >
              {{ t("rbac.user.resetPassword") }}
            </el-button>
            <el-popconfirm
              :title="t('messages.deleteConfirm', { name: row.username })"
              @confirm="removeUser(row)"
            >
              <template #reference>
                <el-button
                  v-auth="'user:delete'"
                  type="danger"
                  link
                  :icon="Delete"
                >
                  {{ t("buttons.delete") }}
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'add' ? t('rbac.user.add') : t('rbac.user.edit')"
      width="620px"
      destroy-on-close
    >
      <el-form
        ref="dialogFormRef"
        :model="dialogForm"
        :rules="dialogRules"
        label-width="120px"
      >
        <el-form-item :label="t('rbac.user.username')" prop="username">
          <el-input v-model="dialogForm.username" maxlength="100" />
        </el-form-item>
        <el-form-item
          v-if="dialogType === 'add'"
          :label="t('rbac.user.password')"
          prop="password"
        >
          <el-input
            v-model="dialogForm.password"
            type="password"
            show-password
            maxlength="128"
          />
        </el-form-item>
        <el-form-item :label="t('rbac.user.nickname')" prop="nickname">
          <el-input v-model="dialogForm.nickname" maxlength="100" />
        </el-form-item>
        <el-form-item :label="t('rbac.user.avatar')" prop="avatar">
          <el-input
            v-model="dialogForm.avatar"
            :placeholder="t('rbac.user.avatarPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('rbac.role.label')" prop="role_ids">
          <el-select
            v-model="dialogForm.role_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            class="w-full"
          >
            <el-option
              v-for="role in roleOptions"
              :key="role.id"
              :label="`${role.name} (${role.code})`"
              :value="role.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('labels.status')">
          <el-switch
            v-model="dialogForm.is_active"
            :active-text="t('buttons.active')"
            :inactive-text="t('buttons.inactive')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{
          t("buttons.cancel")
        }}</el-button>
        <el-button type="primary" :loading="dialogLoading" @click="submitUser">
          {{ t("buttons.confirm") }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="passwordVisible"
      :title="t('rbac.user.resetPasswordFor', { name: currentUser?.username })"
      width="460px"
      destroy-on-close
    >
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-width="130px"
      >
        <el-form-item :label="t('rbac.user.newPassword')" prop="password">
          <el-input
            v-model="passwordForm.password"
            type="password"
            show-password
          />
        </el-form-item>
        <el-form-item
          :label="t('rbac.user.confirmPassword')"
          prop="confirmPassword"
        >
          <el-input
            v-model="passwordForm.confirmPassword"
            type="password"
            show-password
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordVisible = false">{{
          t("buttons.cancel")
        }}</el-button>
        <el-button
          type="primary"
          :loading="passwordLoading"
          @click="submitPassword"
        >
          {{ t("buttons.confirm") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import dayjs from "dayjs";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import Plus from "~icons/ep/plus";
import EditPen from "~icons/ep/edit-pen";
import Delete from "~icons/ep/delete";
import Key from "~icons/ep/key";
import { PureTableBar } from "@/components/RePureTableBar";
import { hasAuth } from "@/router/utils";
import {
  createUser,
  deleteUser,
  getRoleOptions,
  getUserList,
  resetUserPassword,
  updateUser,
  updateUserRoles,
  type RoleOption,
  type UserItem
} from "@/api/rbac";

defineOptions({ name: "RbacUserManagement" });
const { t } = useI18n();

const loading = ref(false);
const tableData = ref<UserItem[]>([]);
const roleOptions = ref<RoleOption[]>([]);
const searchFormRef = ref<FormInstance>();
const searchForm = reactive({
  keyword: "",
  role_id: undefined as number | undefined,
  is_active: undefined as boolean | undefined
});
const pagination = reactive({
  total: 0,
  pageSize: 20,
  currentPage: 1,
  background: true,
  layout: "total, sizes, prev, pager, next, jumper"
});

const roleMap = computed(() =>
  Object.fromEntries(roleOptions.value.map(role => [role.code, role.name]))
);
const roleName = (code: string) => roleMap.value[code] || code;
const formatTime = (value?: string | null) =>
  value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "—";

const columns: TableColumnList = [
  { label: "ID", prop: "id", width: 70 },
  { label: t("rbac.user.account"), prop: "user", minWidth: 180, slot: "user" },
  { label: t("rbac.role.label"), prop: "roles", minWidth: 170, slot: "roles" },
  {
    label: t("labels.status"),
    prop: "is_active",
    width: 100,
    slot: "is_active"
  },
  {
    label: t("rbac.user.lastLogin"),
    prop: "last_login",
    width: 165,
    formatter: ({ last_login }) => formatTime(last_login)
  },
  {
    label: t("form.createdAt"),
    prop: "created_at",
    width: 165,
    formatter: ({ created_at }) => formatTime(created_at)
  },
  {
    label: t("labels.operation"),
    prop: "operation",
    width: 290,
    fixed: "right",
    slot: "operation",
    hide: !hasAuth("user:edit") && !hasAuth("user:delete")
  }
];

const dialogVisible = ref(false);
const dialogLoading = ref(false);
const dialogType = ref<"add" | "edit">("add");
const dialogFormRef = ref<FormInstance>();
const dialogForm = reactive({
  id: undefined as number | undefined,
  username: "",
  password: "",
  nickname: "",
  avatar: "",
  is_active: true,
  role_ids: [] as number[]
});
const dialogRules: FormRules = {
  username: [
    {
      required: true,
      message: () => t("validation.required"),
      trigger: "blur"
    },
    {
      min: 3,
      max: 100,
      message: () => t("rbac.user.usernameLength"),
      trigger: "blur"
    }
  ],
  password: [
    {
      required: true,
      message: () => t("validation.required"),
      trigger: "blur"
    },
    {
      min: 6,
      max: 128,
      message: () => t("rbac.user.passwordLength"),
      trigger: "blur"
    }
  ]
};

const passwordVisible = ref(false);
const passwordLoading = ref(false);
const passwordFormRef = ref<FormInstance>();
const currentUser = ref<UserItem>();
const passwordForm = reactive({ password: "", confirmPassword: "" });
const passwordRules: FormRules = {
  password: [
    {
      required: true,
      message: () => t("validation.required"),
      trigger: "blur"
    },
    {
      min: 6,
      max: 128,
      message: () => t("rbac.user.passwordLength"),
      trigger: "blur"
    }
  ],
  confirmPassword: [
    {
      required: true,
      message: () => t("validation.required"),
      trigger: "blur"
    },
    {
      validator: (_rule, value, callback) =>
        value === passwordForm.password
          ? callback()
          : callback(new Error(t("rbac.user.passwordMismatch"))),
      trigger: "blur"
    }
  ]
};

async function fetchData() {
  loading.value = true;
  try {
    const result = await getUserList({
      page: pagination.currentPage,
      page_size: pagination.pageSize,
      keyword: searchForm.keyword || undefined,
      role_id: searchForm.role_id,
      is_active: searchForm.is_active
    });
    tableData.value = result.data;
    pagination.total = result.total;
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  pagination.currentPage = 1;
  fetchData();
}
function onReset() {
  searchFormRef.value?.resetFields();
  Object.assign(searchForm, {
    keyword: "",
    role_id: undefined,
    is_active: undefined
  });
  onSearch();
}
function handleSizeChange(size: number) {
  pagination.pageSize = size;
  fetchData();
}
function handleCurrentChange(page: number) {
  pagination.currentPage = page;
  fetchData();
}

function openDialog(type: "add" | "edit", row?: UserItem) {
  dialogType.value = type;
  Object.assign(
    dialogForm,
    type === "edit" && row
      ? {
          id: row.id,
          username: row.username,
          password: "",
          nickname: row.nickname || "",
          avatar: row.avatar || "",
          is_active: row.is_active,
          role_ids: roleOptions.value
            .filter(role => row.roles.includes(role.code))
            .map(role => role.id)
        }
      : {
          id: undefined,
          username: "",
          password: "",
          nickname: "",
          avatar: "",
          is_active: true,
          role_ids: []
        }
  );
  dialogVisible.value = true;
}

async function submitUser() {
  await dialogFormRef.value?.validate();
  dialogLoading.value = true;
  try {
    if (dialogType.value === "add") {
      await createUser({
        username: dialogForm.username,
        password: dialogForm.password,
        nickname: dialogForm.nickname || null,
        avatar: dialogForm.avatar || null,
        is_active: dialogForm.is_active,
        role_ids: dialogForm.role_ids
      });
      ElMessage.success(t("messages.addSuccess"));
    } else {
      await updateUser(dialogForm.id!, {
        username: dialogForm.username,
        nickname: dialogForm.nickname || null,
        avatar: dialogForm.avatar || null,
        is_active: dialogForm.is_active
      });
      await updateUserRoles(dialogForm.id!, dialogForm.role_ids);
      ElMessage.success(t("messages.editSuccess"));
    }
    dialogVisible.value = false;
    fetchData();
  } finally {
    dialogLoading.value = false;
  }
}

async function changeStatus(row: UserItem & { _statusLoading?: boolean }) {
  row._statusLoading = true;
  try {
    await updateUser(row.id, { is_active: row.is_active });
    ElMessage.success(t("messages.toggleSuccess"));
  } catch {
    row.is_active = !row.is_active;
  } finally {
    row._statusLoading = false;
  }
}

async function removeUser(row: UserItem) {
  await deleteUser(row.id);
  ElMessage.success(t("messages.deleteSuccess"));
  if (tableData.value.length === 1 && pagination.currentPage > 1)
    pagination.currentPage--;
  fetchData();
}

function openPasswordDialog(row: UserItem) {
  currentUser.value = row;
  Object.assign(passwordForm, { password: "", confirmPassword: "" });
  passwordVisible.value = true;
}
async function submitPassword() {
  await passwordFormRef.value?.validate();
  passwordLoading.value = true;
  try {
    await resetUserPassword(currentUser.value!.id, passwordForm.password);
    ElMessage.success(t("rbac.user.passwordResetSuccess"));
    passwordVisible.value = false;
  } finally {
    passwordLoading.value = false;
  }
}

onMounted(async () => {
  roleOptions.value = await getRoleOptions();
  await fetchData();
});
</script>

<style scoped>
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
</style>
