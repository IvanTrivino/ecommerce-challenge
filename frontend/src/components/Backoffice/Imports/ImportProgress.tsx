import type { ProductImportPublic } from "@/client"
import { ImportStatusBadge } from "@/components/Backoffice/Imports/ImportStatusBadge"
import { ProgressBar } from "@/components/Common/ProgressBar"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { formatBytes } from "@/lib/format"

const COUNTERS = [
  ["created", "Created", "created_count"],
  ["updated", "Updated", "updated_count"],
  ["unchanged", "Unchanged", "unchanged_count"],
  ["errors", "Errors", "error_count"],
  ["blank", "Blank rows", "blank_count"],
  ["categories", "New categories", "categories_created"],
] as const

export function ImportProgress({
  productImport,
}: {
  productImport: ProductImportPublic
}) {
  const i = productImport
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <ImportStatusBadge productImport={i} />
        <ProgressBar
          value={i.progress}
          label="Import progress"
          className="flex-1"
        />
        <span className="w-10 text-right text-sm tabular-nums">
          {i.progress}%
        </span>
      </div>
      <p className="text-sm text-muted-foreground">
        {formatBytes(i.bytes_processed)} of {formatBytes(i.total_bytes)}
      </p>
      <dl
        aria-live="polite"
        className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6"
      >
        {COUNTERS.map(([id, label, field]) => (
          <div key={id}>
            <dt className="text-sm text-muted-foreground">{label}</dt>
            <dd
              className="text-2xl font-semibold tabular-nums"
              data-testid={`import-count-${id}`}
            >
              {i[field]}
            </dd>
          </div>
        ))}
      </dl>
      {i.status === "failed" && (
        <Alert variant="destructive">
          <AlertDescription>
            {i.error_message ?? "The import failed"}
          </AlertDescription>
        </Alert>
      )}
    </div>
  )
}
