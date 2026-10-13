import type { ProductImportPublic } from "@/client"
import { isStorageForbidden, storageErrorCode } from "@/lib/storageUpload"

// Mirrors the backend (PRODUCT_IMPORT_MAX_BYTES)
export const IMPORT_MAX_BYTES = 10 * 1024 * 1024
export const IMPORT_ACCEPT = ".csv,text/csv"
export const IMPORT_HINT = "CSV up to 10 MB"
export const IMPORT_TEMPLATE_URL = "/product-import-template.csv"
export const IMPORT_POLL_MS = 1000

export type ImportStatus = ProductImportPublic["status"]

export const isImportActive = (status: ImportStatus | undefined) =>
  status === "pending" || status === "running"

// By extension and size only: browsers report .csv as application/vnd.ms-excel or ""
export function validateCsvFile(file: File): string | null {
  if (!/\.csv$/i.test(file.name)) return "Choose a .csv file"
  if (file.size === 0) return "The file is empty"
  if (file.size > IMPORT_MAX_BYTES) return "CSV must be 10 MB or smaller"
  return null
}

export function importStorageErrorMessage(err: unknown): string {
  if (storageErrorCode(err) === "EntityTooLarge")
    return "CSV must be 10 MB or smaller"
  if (isStorageForbidden(err)) return "Upload link expired, try again"
  return "CSV upload failed"
}

export function importSummary(i: ProductImportPublic): string {
  return `${i.created_count} created, ${i.updated_count} updated, ${i.unchanged_count} unchanged, ${i.error_count} errors`
}

// Spreadsheet formula guard, then RFC 4180 quoting
export function csvCell(value: string | number | null | undefined): string {
  let text = value == null ? "" : String(value)
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function buildErrorReport(
  rows: { line: number; sku: string | null; message: string }[],
): string {
  const lines = ["line,sku,error"].concat(
    rows.map((r) =>
      [csvCell(r.line), csvCell(r.sku), csvCell(r.message)].join(","),
    ),
  )
  return `${lines.join("\r\n")}\r\n`
}
