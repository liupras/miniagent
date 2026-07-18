<template>
  <div class="main">
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] pl-8 pt-3 overflow-auto"
    >
      <el-form-item :label="t('form.type.label')" prop="menu_type">
        <el-select
          v-model="searchForm.menu_type"
          :placeholder="t('rbac.menu.allTypes')"
          clearable
          class="w-40!"
        >
          <el-option :label="t('rbac.menu.types.menu')" value="menu" />
          <el-option :label="t('rbac.menu.types.button')" value="button" />
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
        <el-button type="primary" :icon="Search" @click="fetchData">
          {{ t("buttons.search") }}
        </el-button>
        <el-button :icon="Refresh" @click="onReset">
          {{ t("buttons.reset") }}
        </el-button>
      </el-form-item>
    </el-form>

    <el-alert
      class="mb-4"
      type="info"
      :closable="false"
      show-icon
      :title="t('rbac.menu.editHint')"
    />

    <PureTableBar
      :title="t('rbac.menu.title')"
      :columns="columns"
      @refresh="fetchData"
    >
      <template #default="{ size, dynamicColumns }">
        <pure-table
          row-key="id"
          :data="tableData"
          :columns="dynamicColumns"
          :size="size"
          :loading="loading"
          :tree-props="{
            children: 'children',
            hasChildren: 'hasChildren',
            checkStrictly: false
          }"
          default-expand-all
          align-whole="left"
        >
          <template #title="{ row }">
            <div class="flex items-center gap-2">
              <span>{{ menuLabel(row) }}</span>
              <el-tag
                size="small"
                :type="row.menu_type === 'button' ? 'warning' : 'info'"
                effect="plain"
              >
                {{ t(`rbac.menu.types.${row.menu_type}`) }}
              </el-tag>
            </div>
          </template>
          <template #name="{ row }">
            <code class="rounded bg-(--el-fill-color-light) px-2 py-1 text-xs">
              {{ row.name }}
            </code>
          </template>
          <template #route="{ row }">
            <div class="text-left text-xs leading-5">
              <div>{{ row.path || "—" }}</div>
              <div v-if="row.component" class="text-gray-400">
                {{ row.component }}
              </div>
            </div>
          </template>
          <template #is_visible="{ row }">
            <el-tag :type="row.is_visible ? 'success' : 'info'" size="small">
              {{ row.is_visible ? t("labels.yes") : t("labels.no") }}
            </el-tag>
          </template>
          <template #is_active="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? t("buttons.active") : t("buttons.inactive") }}
            </el-tag>
          </template>
          <template #operation="{ row }">
            <el-button
              type="primary"
              link
              :icon="View"
              @click="showDetail(row)"
            >
              {{ t("buttons.view") }}
            </el-button>
            <el-button
              v-auth="'menu:edit'"
              type="primary"
              link
              :icon="EditPen"
              @click="openEditDialog(row)"
            >
              {{ t("buttons.edit") }}
            </el-button>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <el-dialog
      v-model="editVisible"
      :title="t('rbac.menu.edit')"
      width="680px"
      destroy-on-close
    >
      <el-form
        ref="editFormRef"
        :model="editForm"
        :rules="editRules"
        label-width="130px"
      >
        <el-form-item :label="t('rbac.menu.parentId')" prop="parent_id">
          <el-select
            v-model="editForm.parent_id"
            clearable
            filterable
            :placeholder="t('rbac.menu.rootMenu')"
            class="w-full"
          >
            <el-option
              v-for="option in availableParents"
              :key="option.id"
              :label="option.label"
              :value="option.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('rbac.menu.permissionCode')" prop="name">
          <el-input v-model="editForm.name" maxlength="100" />
        </el-form-item>
        <el-form-item :label="t('rbac.menu.titleKey')" prop="title_key">
          <el-input v-model="editForm.title_key" maxlength="100">
            <template #append>{{ translatedEditTitle }}</template>
          </el-input>
        </el-form-item>
        <el-form-item :label="t('form.type.label')" prop="menu_type">
          <el-radio-group v-model="editForm.menu_type">
            <el-radio value="menu">{{ t("rbac.menu.types.menu") }}</el-radio>
            <el-radio value="button">{{
              t("rbac.menu.types.button")
            }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="t('rbac.menu.path')" prop="path">
          <el-input v-model="editForm.path" maxlength="200" />
        </el-form-item>
        <el-form-item :label="t('rbac.menu.component')" prop="component">
          <el-input v-model="editForm.component" maxlength="200" />
        </el-form-item>
        <el-form-item :label="t('rbac.menu.icon')" prop="icon">
          <el-input v-model="editForm.icon" maxlength="100" />
        </el-form-item>
        <el-form-item :label="t('rbac.menu.sortOrder')" prop="sort_order">
          <el-input-number v-model="editForm.sort_order" :min="0" />
        </el-form-item>
        <el-form-item :label="t('form.description.label')" prop="description">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item :label="t('rbac.menu.visible')">
          <el-switch v-model="editForm.is_visible" />
        </el-form-item>
        <el-form-item :label="t('labels.status')">
          <el-switch
            v-model="editForm.is_active"
            :active-text="t('buttons.active')"
            :inactive-text="t('buttons.inactive')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">{{
          t("buttons.cancel")
        }}</el-button>
        <el-button type="primary" :loading="editLoading" @click="submitEdit">
          {{ t("buttons.confirm") }}
        </el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="detailVisible"
      :title="t('rbac.menu.detail')"
      size="520px"
    >
      <el-skeleton v-if="detailLoading" :rows="10" animated />
      <el-descriptions v-else-if="currentMenu" :column="1" border>
        <el-descriptions-item label="ID">{{
          currentMenu.id
        }}</el-descriptions-item>
        <el-descriptions-item :label="t('rbac.menu.parentId')">
          {{ currentMenu.parent_id ?? "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('rbac.menu.titleKey')">
          {{ currentMenu.title_key }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('rbac.menu.displayTitle')">
          {{ menuLabel(currentMenu) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('rbac.menu.permissionCode')">
          <code>{{ currentMenu.name }}</code>
        </el-descriptions-item>
        <el-descriptions-item :label="t('form.type.label')">
          {{ t(`rbac.menu.types.${currentMenu.menu_type}`) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('rbac.menu.path')">
          {{ currentMenu.path || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('rbac.menu.component')">
          {{ currentMenu.component || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('rbac.menu.icon')">
          {{ currentMenu.icon || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('rbac.menu.sortOrder')">
          {{ currentMenu.sort_order }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('rbac.menu.visible')">
          {{ currentMenu.is_visible ? t("labels.yes") : t("labels.no") }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('labels.status')">
          {{
            currentMenu.is_active ? t("buttons.active") : t("buttons.inactive")
          }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('form.description.label')">
          {{ currentMenu.description || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('form.createdAt')">
          {{ formatTime(currentMenu.created_at) }}
        </el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import dayjs from "dayjs";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import View from "~icons/ep/view";
import EditPen from "~icons/ep/edit-pen";
import { PureTableBar } from "@/components/RePureTableBar";
import {
  getMenuById,
  getMenuList,
  updateMenu,
  type MenuItem,
  type MenuType
} from "@/api/rbac";

defineOptions({ name: "RbacMenuManagement" });
const { t } = useI18n();
const loading = ref(false);
const tableData = ref<MenuItem[]>([]);
const searchFormRef = ref<FormInstance>();
const searchForm = reactive({
  menu_type: undefined as MenuType | undefined,
  is_active: undefined as boolean | undefined
});
const detailVisible = ref(false);
const detailLoading = ref(false);
const currentMenu = ref<MenuItem>();

const menuLabel = (menu: MenuItem) => {
  const translated = t(menu.title_key);
  return translated === menu.title_key ? menu.title_key : translated;
};
const formatTime = (value: string) => dayjs(value).format("YYYY-MM-DD HH:mm");

const editVisible = ref(false);
const editLoading = ref(false);
const editFormRef = ref<FormInstance>();
const editingMenu = ref<MenuItem>();
const parentMenuTree = ref<MenuItem[]>([]);
const editForm = reactive({
  id: 0,
  parent_id: undefined as number | undefined,
  name: "",
  title_key: "",
  path: "",
  component: "",
  icon: "",
  sort_order: 0,
  menu_type: "menu" as MenuType,
  description: "",
  is_visible: true,
  is_active: true
});
const editRules: FormRules = {
  name: [
    { required: true, message: () => t("validation.required"), trigger: "blur" }
  ],
  title_key: [
    { required: true, message: () => t("validation.required"), trigger: "blur" }
  ],
  menu_type: [
    {
      required: true,
      message: () => t("validation.required"),
      trigger: "change"
    }
  ]
};

interface ParentOption {
  id: number;
  label: string;
}

function flattenMenus(items: MenuItem[], level = 0): ParentOption[] {
  return items.flatMap(item => [
    {
      id: item.id,
      label: `${"　".repeat(level)}${menuLabel(item)} (${item.name})`
    },
    ...flattenMenus(item.children || [], level + 1)
  ]);
}

function collectMenuIds(menu?: MenuItem): Set<number> {
  const ids = new Set<number>();
  const visit = (item?: MenuItem) => {
    if (!item) return;
    ids.add(item.id);
    item.children?.forEach(visit);
  };
  visit(menu);
  return ids;
}

const availableParents = computed(() => {
  const unavailable = collectMenuIds(editingMenu.value);
  return flattenMenus(parentMenuTree.value).filter(
    item => !unavailable.has(item.id)
  );
});

const translatedEditTitle = computed(() => {
  if (!editForm.title_key) return "";
  const translated = t(editForm.title_key);
  return translated === editForm.title_key ? "" : translated;
});

const columns: TableColumnList = [
  {
    label: t("rbac.menu.displayTitle"),
    prop: "title",
    minWidth: 220,
    slot: "title"
  },
  {
    label: t("rbac.menu.permissionCode"),
    prop: "name",
    minWidth: 175,
    slot: "name"
  },
  { label: t("rbac.menu.route"), prop: "route", minWidth: 220, slot: "route" },
  { label: t("rbac.menu.sortOrder"), prop: "sort_order", width: 100 },
  {
    label: t("rbac.menu.visible"),
    prop: "is_visible",
    width: 170,
    slot: "is_visible"
  },
  {
    label: t("labels.status"),
    prop: "is_active",
    width: 100,
    slot: "is_active"
  },
  {
    label: t("labels.operation"),
    prop: "operation",
    width: 100,
    fixed: "right",
    slot: "operation"
  }
];

async function fetchData() {
  loading.value = true;
  try {
    tableData.value = await getMenuList({
      tree: true,
      menu_type: searchForm.menu_type,
      is_active: searchForm.is_active
    });
  } finally {
    loading.value = false;
  }
}
function onReset() {
  searchFormRef.value?.resetFields();
  Object.assign(searchForm, { menu_type: undefined, is_active: undefined });
  fetchData();
}
async function showDetail(row: MenuItem) {
  detailVisible.value = true;
  detailLoading.value = true;
  try {
    currentMenu.value = await getMenuById(row.id);
  } finally {
    detailLoading.value = false;
  }
}

async function openEditDialog(row: MenuItem) {
  const [menu, fullTree] = await Promise.all([
    getMenuById(row.id),
    getMenuList({ tree: true })
  ]);
  parentMenuTree.value = fullTree;
  const findMenu = (items: MenuItem[]): MenuItem | undefined => {
    for (const item of items) {
      if (item.id === row.id) return item;
      const found = findMenu(item.children || []);
      if (found) return found;
    }
  };
  editingMenu.value = findMenu(fullTree);
  Object.assign(editForm, {
    id: menu.id,
    parent_id: menu.parent_id ?? undefined,
    name: menu.name,
    title_key: menu.title_key,
    path: menu.path || "",
    component: menu.component || "",
    icon: menu.icon || "",
    sort_order: menu.sort_order,
    menu_type: menu.menu_type,
    description: menu.description || "",
    is_visible: menu.is_visible,
    is_active: menu.is_active
  });
  editVisible.value = true;
}

async function submitEdit() {
  await editFormRef.value?.validate();
  editLoading.value = true;
  try {
    await updateMenu(editForm.id, {
      parent_id: editForm.parent_id ?? null,
      name: editForm.name,
      title_key: editForm.title_key,
      path: editForm.path || null,
      component: editForm.component || null,
      icon: editForm.icon || null,
      sort_order: editForm.sort_order,
      menu_type: editForm.menu_type,
      description: editForm.description || null,
      is_visible: editForm.is_visible,
      is_active: editForm.is_active
    });
    ElMessage.success(t("messages.editSuccess"));
    editVisible.value = false;
    await fetchData();
  } finally {
    editLoading.value = false;
  }
}

onMounted(fetchData);
</script>

<style scoped>
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
</style>
