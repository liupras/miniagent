<template>
  <div class="main">
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] pl-8 pt-3 overflow-auto"
    >
      <el-form-item :label="t('rbac.role.keyword')" prop="keyword">
        <el-input
          v-model="searchForm.keyword"
          :placeholder="t('rbac.role.keywordPlaceholder')"
          clearable
          class="w-52!"
          @keyup.enter="onSearch"
        />
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
      :title="t('rbac.role.title')"
      :columns="columns"
      @refresh="fetchData"
    >
      <template #buttons>
        <el-button
          v-if="hasPerms('role:add')"
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
          <template #code="{ row }">
            <el-tag :type="row.is_super ? 'danger' : 'info'" effect="plain">
              {{ row.code }}
            </el-tag>
          </template>
          <template #is_super="{ row }">
            <el-tag :type="row.is_super ? 'danger' : 'info'" size="small">
              {{
                row.is_super
                  ? t("rbac.role.superRole")
                  : t("rbac.role.normalRole")
              }}
            </el-tag>
          </template>
          <template #operation="{ row }">
            <el-button
              v-if="hasPerms('role:edit')"
              type="primary"
              link
              :icon="EditPen"
              @click="openDialog('edit', row)"
            >
              {{ t("buttons.edit") }}
            </el-button>
            <el-button
              v-if="hasPerms('role:edit')"
              type="warning"
              link
              :icon="Lock"
              @click="openPermissionDialog(row)"
            >
              {{ t("rbac.role.permissions") }}
            </el-button>
            <el-popconfirm
              :title="t('messages.deleteConfirm', { name: row.name })"
              @confirm="removeRole(row)"
            >
              <template #reference>
                <el-button
                  v-if="hasPerms('role:delete')"
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
      :title="dialogType === 'add' ? t('rbac.role.add') : t('rbac.role.edit')"
      width="560px"
      destroy-on-close
    >
      <el-form
        ref="dialogFormRef"
        :model="dialogForm"
        :rules="dialogRules"
        label-width="120px"
      >
        <el-form-item :label="t('rbac.role.code')" prop="code">
          <el-input v-model="dialogForm.code" maxlength="50" />
        </el-form-item>
        <el-form-item :label="t('form.name.label')" prop="name">
          <el-input v-model="dialogForm.name" maxlength="100" />
        </el-form-item>
        <el-form-item :label="t('form.description.label')" prop="description">
          <el-input
            v-model="dialogForm.description"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item :label="t('rbac.role.superRole')">
          <el-switch v-model="dialogForm.is_super" />
          <span class="ml-3 text-xs text-gray-400">{{
            t("rbac.role.superHint")
          }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{
          t("buttons.cancel")
        }}</el-button>
        <el-button type="primary" :loading="dialogLoading" @click="submitRole">
          {{ t("buttons.confirm") }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="permissionVisible"
      :title="t('rbac.role.permissionFor', { name: currentRole?.name })"
      width="620px"
      destroy-on-close
    >
      <div class="mb-3 flex items-center justify-between">
        <span class="text-sm text-gray-500">{{
          t("rbac.role.permissionHint")
        }}</span>
        <div>
          <el-button link type="primary" @click="expandAll(true)">{{
            t("buttons.expand")
          }}</el-button>
          <el-button link type="primary" @click="expandAll(false)">{{
            t("buttons.collapse")
          }}</el-button>
        </div>
      </div>
      <div
        class="permission-tree rounded border border-(--el-border-color) p-3"
      >
        <el-tree
          ref="menuTreeRef"
          :data="menuTree"
          node-key="id"
          show-checkbox
          check-strictly
          default-expand-all
          :props="{ children: 'children' }"
        >
          <template #default="{ data }">
            <div class="flex flex-1 items-center justify-between pr-4">
              <span>{{ menuLabel(data) }}</span>
              <div class="flex items-center gap-2">
                <el-tag
                  size="small"
                  :type="data.menu_type === 'button' ? 'warning' : 'info'"
                  effect="plain"
                >
                  {{ t(`rbac.menu.types.${data.menu_type}`) }}
                </el-tag>
                <code class="text-xs text-gray-400">{{ data.name }}</code>
              </div>
            </div>
          </template>
        </el-tree>
      </div>
      <template #footer>
        <el-button @click="permissionVisible = false">{{
          t("buttons.cancel")
        }}</el-button>
        <el-button
          type="primary"
          :loading="permissionLoading"
          @click="savePermissions"
        >
          {{ t("buttons.save") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  ElMessage,
  type FormInstance,
  type FormRules,
  type ElTree
} from "element-plus";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import Plus from "~icons/ep/plus";
import EditPen from "~icons/ep/edit-pen";
import Delete from "~icons/ep/delete";
import Lock from "~icons/ep/lock";
import { PureTableBar } from "@/components/RePureTableBar";
import { hasPerms } from "@/utils/auth";
import {
  createRole,
  deleteRole,
  getMenuList,
  getRoleList,
  updateRole,
  updateRoleMenus,
  type MenuItem,
  type RoleItem
} from "@/api/rbac";

defineOptions({ name: "RbacRoleManagement" });
const { t, te } = useI18n();
const loading = ref(false);
const tableData = ref<RoleItem[]>([]);
const menuTree = ref<MenuItem[]>([]);
const searchFormRef = ref<FormInstance>();
const searchForm = reactive({ keyword: "" });
const pagination = reactive({
  total: 0,
  pageSize: 20,
  currentPage: 1,
  background: true,
  layout: "total, sizes, prev, pager, next, jumper"
});

const columns: TableColumnList = [
  { label: "ID", prop: "id", width: 70 },
  { label: t("rbac.role.code"), prop: "code", width: 150, slot: "code" },
  { label: t("form.name.label"), prop: "name", minWidth: 150 },
  {
    label: t("form.description.label"),
    prop: "description",
    minWidth: 200,
    showOverflowTooltip: true
  },
  {
    label: t("rbac.role.type"),
    prop: "is_super",
    width: 130,
    slot: "is_super"
  },
  { label: t("rbac.role.userCount"), prop: "user_count", width: 110 },
  {
    label: t("rbac.role.permissionCount"),
    prop: "menu_ids",
    width: 120,
    formatter: ({ menu_ids }) => menu_ids.length
  },
  {
    label: t("labels.operation"),
    prop: "operation",
    width: 285,
    fixed: "right",
    slot: "operation",
    hide: !hasPerms("role:edit") && !hasPerms("role:delete")
  }
];

const dialogVisible = ref(false);
const dialogLoading = ref(false);
const dialogType = ref<"add" | "edit">("add");
const dialogFormRef = ref<FormInstance>();
const dialogForm = reactive({
  id: undefined as number | undefined,
  code: "",
  name: "",
  description: "",
  is_super: false
});
const dialogRules: FormRules = {
  code: [
    {
      required: true,
      message: () => t("validation.required"),
      trigger: "blur"
    },
    {
      pattern: /^[A-Za-z][A-Za-z0-9_-]*$/,
      message: () => t("rbac.role.codePattern"),
      trigger: "blur"
    }
  ],
  name: [
    { required: true, message: () => t("validation.required"), trigger: "blur" }
  ]
};

const permissionVisible = ref(false);
const permissionLoading = ref(false);
const currentRole = ref<RoleItem>();
const menuTreeRef = ref<InstanceType<typeof ElTree>>();

const menuLabel = (menu: MenuItem) =>
  te(menu.title_key) ? t(menu.title_key) : menu.title_key;

async function fetchData() {
  loading.value = true;
  try {
    const result = await getRoleList({
      page: pagination.currentPage,
      page_size: pagination.pageSize,
      keyword: searchForm.keyword || undefined
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
  searchForm.keyword = "";
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

function openDialog(type: "add" | "edit", row?: RoleItem) {
  dialogType.value = type;
  Object.assign(
    dialogForm,
    type === "edit" && row
      ? {
          id: row.id,
          code: row.code,
          name: row.name,
          description: row.description || "",
          is_super: row.is_super
        }
      : { id: undefined, code: "", name: "", description: "", is_super: false }
  );
  dialogVisible.value = true;
}
async function submitRole() {
  await dialogFormRef.value?.validate();
  dialogLoading.value = true;
  try {
    const payload = {
      code: dialogForm.code,
      name: dialogForm.name,
      description: dialogForm.description || null,
      is_super: dialogForm.is_super
    };
    if (dialogType.value === "add") {
      await createRole({ ...payload, menu_ids: [] });
      ElMessage.success(t("messages.addSuccess"));
    } else {
      await updateRole(dialogForm.id!, payload);
      ElMessage.success(t("messages.editSuccess"));
    }
    dialogVisible.value = false;
    fetchData();
  } finally {
    dialogLoading.value = false;
  }
}
async function removeRole(row: RoleItem) {
  await deleteRole(row.id);
  ElMessage.success(t("messages.deleteSuccess"));
  if (tableData.value.length === 1 && pagination.currentPage > 1)
    pagination.currentPage--;
  fetchData();
}

async function openPermissionDialog(row: RoleItem) {
  currentRole.value = row;
  permissionVisible.value = true;
  await nextTick();
  menuTreeRef.value?.setCheckedKeys(row.menu_ids, false);
}
async function savePermissions() {
  permissionLoading.value = true;
  try {
    const checked =
      (menuTreeRef.value?.getCheckedKeys(false) as number[]) || [];
    await updateRoleMenus(currentRole.value!.id, checked);
    ElMessage.success(t("messages.saveSuccess"));
    permissionVisible.value = false;
    fetchData();
  } finally {
    permissionLoading.value = false;
  }
}
function expandAll(expanded: boolean) {
  const store = (menuTreeRef.value as any)?.store;
  Object.values(store?.nodesMap || {}).forEach((node: any) => {
    node.expanded = expanded;
  });
}

onMounted(async () => {
  const [menus] = await Promise.all([getMenuList({ tree: true }), fetchData()]);
  menuTree.value = menus;
});
</script>

<style scoped>
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
.permission-tree {
  max-height: 55vh;
  overflow: auto;
}
</style>
