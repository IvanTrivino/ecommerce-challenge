// No binary files in the repo: images are built as buffers
export const PNG_1PX = Buffer.from(
  "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8cfc0f01f0005000201a5f6e2b70000000049454e44ae426082",
  "hex",
)

export const pngFile = (name = "photo.png") => ({
  name,
  mimeType: "image/png",
  buffer: PNG_1PX,
})

export const svgFile = () => ({
  name: "logo.svg",
  mimeType: "image/svg+xml",
  buffer: Buffer.from("<svg/>"),
})

export const bigPngFile = () => ({
  name: "big.png",
  mimeType: "image/png",
  buffer: Buffer.concat([PNG_1PX, Buffer.alloc(5 * 1024 * 1024)]),
})
