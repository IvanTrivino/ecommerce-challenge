import axios from "axios"

// Straight to object storage: the default axios instance carries no auth
// header, which would break the storage signature and leak the token
export async function uploadToStorage(
  ticket: { url: string; fields: Record<string, string> },
  file: File,
  {
    onProgress,
    signal,
  }: { onProgress?: (percent: number) => void; signal?: AbortSignal } = {},
): Promise<void> {
  const body = new FormData()
  for (const [name, value] of Object.entries(ticket.fields))
    body.append(name, value)
  body.append("file", file) // storage ignores any field after the file
  await axios.post(ticket.url, body, {
    signal,
    onUploadProgress: (e) =>
      e.total && onProgress?.(Math.round((e.loaded / e.total) * 100)),
  })
}

// The <Code> of an S3 XML error response, if any
export function storageErrorCode(err: unknown): string | null {
  if (!axios.isAxiosError(err) || !err.response) return null
  const data: unknown = err.response.data
  return typeof data === "string"
    ? (/<Code>([^<]+)<\/Code>/.exec(data)?.[1] ?? null)
    : null
}

export const isStorageForbidden = (err: unknown) =>
  axios.isAxiosError(err) && err.response?.status === 403
