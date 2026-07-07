import { http } from "@/utils/http";
import { baseUrlApi } from "@/api/utils";

/** ─────────────────────────────────────────────────────────────────────
 *  Types
 *  ──────────────────────────────────────────────────────────────────── */

export interface SchemaInfo {
  schemaName: string;
  tableCount: number;
}

export interface TableInfo {
  schemaName: string;
  tableName: string;
  rowCount?: number;
  columnCount?: number;
  comment?: string;
}

export interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  isPrimaryKey: boolean;
  default?: string;
}

export interface TablePreview {
  columns: ColumnInfo[];
  rows: Record<string, any>[];
  total: number;
  page: number;
  pageSize: number;
}

export interface ImportTableResult {
  tablePath: string;
  schemaName: string;
  tableName: string;
  rowCount?: number;
  fileType: "csv" | "excel";
  sheetName?: string;
}

export interface ImportTableParams {
  file: File;
  schemaName: string;
  tableName?: string;
  sheetName?: string;
  primaryKey?: string;
  forceCast?: boolean;
  allowNewColumns?: boolean;
}

export interface TableDataParams {
  page: number;
  pageSize: number;
  orderBy?: string;
  orderDesc?: boolean;
}

/** ─────────────────────────────────────────────────────────────────────
 *  API
 *  ──────────────────────────────────────────────────────────────────── */

/** Accepted file extensions for the import dialog's <el-upload accept="..."> */
export const IMPORT_ACCEPT_EXTENSIONS = ".csv,.txt,.tsv,.xlsx,.xls,.xlsm";

export const isExcelFile = (filename: string): boolean =>
  /\.(xlsx|xls|xlsm)$/i.test(filename);

export const getSchemas = () => {
  return http.request<SchemaInfo[]>(
    "get",
    baseUrlApi("admin/sql-agent/schemas")
  );
};

export const getTables = (schemaName: string) => {
  return http.request<TableInfo[]>(
    "get",
    baseUrlApi("admin/sql-agent/tables"),
    {
      params: { schema_name: schemaName }
    }
  );
};

export const getTableColumns = (schemaName: string, tableName: string) => {
  return http.request<ColumnInfo[]>(
    "get",
    baseUrlApi(`admin/sql-agent/tables/${schemaName}/${tableName}/columns`)
  );
};

export const getTableData = (
  schemaName: string,
  tableName: string,
  params: TableDataParams
) => {
  return http.request<TablePreview>(
    "get",
    baseUrlApi(`admin/sql-agent/tables/${schemaName}/${tableName}/data`),
    {
      params: {
        page: params.page,
        page_size: params.pageSize,
        order_by: params.orderBy,
        order_desc: params.orderDesc
      }
    }
  );
};

export const deleteTable = (schemaName: string, tableName: string) => {
  return http.request<null>(
    "delete",
    baseUrlApi(`admin/sql-agent/tables/${schemaName}/${tableName}`)
  );
};

export const importTable = (params: ImportTableParams) => {
  const form = new FormData();
  form.append("file", params.file);
  form.append("schema_name", params.schemaName);
  if (params.tableName) form.append("table_name", params.tableName);
  if (params.sheetName) form.append("sheet_name", params.sheetName);
  if (params.primaryKey) form.append("primary_key", params.primaryKey);
  form.append("force_cast", String(params.forceCast ?? false));
  form.append("allow_new_columns", String(params.allowNewColumns ?? false));

  return http.request<ImportTableResult>(
    "post",
    baseUrlApi("admin/sql-agent/import"),
    { data: form },
    { headers: { "Content-Type": "multipart/form-data" } }
  );
};
