import { APP_NAME } from "@/config"

export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="border-t py-4 px-6">
      <p className="text-center text-muted-foreground text-sm">
        {APP_NAME} - {currentYear}
      </p>
    </footer>
  )
}
