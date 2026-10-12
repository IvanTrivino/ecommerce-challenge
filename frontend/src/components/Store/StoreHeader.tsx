import { Link } from "@tanstack/react-router"

import { Appearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import { SearchBar } from "@/components/Store/SearchBar"
import { StoreUserMenu } from "@/components/Store/StoreUserMenu"
import { Button } from "@/components/ui/button"
import { APP_NAME } from "@/config"
import useAuth from "@/hooks/useAuth"
import { isLoggedIn } from "@/lib/auth"

export function StoreHeader() {
  const { user } = useAuth()

  return (
    <header className="sticky top-0 z-20 border-b bg-background">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3">
        <Link to="/" className="flex items-center gap-2 font-semibold">
          <Logo variant="icon" asLink={false} />
          <span>{APP_NAME}</span>
        </Link>
        <div className="order-last w-full md:order-none md:max-w-md md:flex-1">
          <SearchBar />
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Appearance />
          {user ? (
            <StoreUserMenu user={user} />
          ) : isLoggedIn() ? null : (
            <>
              <Button variant="ghost" asChild>
                <Link to="/login">Log in</Link>
              </Button>
              <Button asChild>
                <Link to="/signup">Sign up</Link>
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
