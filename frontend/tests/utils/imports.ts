import { randomSku } from "./random"

// Don't import the example fixture in E2E: its SKUs and category names are
// global, so re-runs would update instead of create. Build an equivalent file
export function makeImportCsv(prefix = randomSku()) {
  const category = `Import ${prefix}`
  const name = `Trail Shoes ${prefix}`
  const rows = [
    "name,sku,description,category,price,stock,weight_kg",
    `${name},${prefix}-1,"Grippy, light",${category},89.99,10,0.35`,
    `Mug ${prefix},${prefix}-2,Ceramic,${category},12.50,40,`,
    `Bad Price,${prefix}-3,,${category},$29.99,5,0.1`,
    `Negative,${prefix}-4,,${category},5.00,-5,0.1`,
    `,${prefix}-5,No name,${category},5.00,1,0.1`,
    ",,,,,,",
    `${name},${prefix}-1,"Grippy, light — v2",${category},94.99,8,0.35`,
  ]
  return {
    prefix,
    category,
    name,
    // CRLF and no final newline, like the backend example
    csv: rows.join("\r\n"),
    expected: {
      created: 2,
      updated: 1,
      unchanged: 0,
      errors: 3,
      blank: 1,
      categories: 1,
    },
    errorLines: [4, 5, 6],
  }
}

export const csvFile = (csv: string, name = "products.csv") => ({
  name,
  mimeType: "text/csv",
  buffer: Buffer.from(csv, "utf-8"),
})

export const txtFile = () => ({
  name: "notes.txt",
  mimeType: "text/plain",
  buffer: Buffer.from("x"),
})

export const bigCsvFile = () => ({
  name: "big.csv",
  mimeType: "text/csv",
  buffer: Buffer.alloc(10 * 1024 * 1024 + 1, 0x61),
})
