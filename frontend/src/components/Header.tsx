import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { MenuIcon, BookText, Users, Share2, Home, LogIn, LogOut } from "lucide-react"; // Assuming lucide-react is installed

export function Header() {
  // Placeholder for authentication status. In a real app, this would come from a global state/context.
  const isAuthenticated = false; // Set to true to test authenticated state

  const navLinks = [
    { href: "/", label: "Home", icon: Home },
    { href: "/encyclopedia", label: "Encyclopedia", icon: BookText },
    { href: "/persons", label: "Persons", icon: Users },
    { href: "/graph", label: "Graph", icon: Share2 },
  ];

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between">
        {/* Logo/Title */}
        <Link href="/" className="flex items-center space-x-2 text-xl font-bold">
          <span className="text-primary">Detective-1</span>
        </Link>

        {/* Desktop Navigation */}
        <nav className="hidden md:flex items-center space-x-4 lg:space-x-6">
          {navLinks.map((link) => (
            <Button key={link.href} variant="ghost" asChild>
              <Link href={link.href} className="flex items-center gap-2">
                <link.icon className="h-4 w-4" />
                <span>{link.label}</span>
              </Link>
            </Button>
          ))}
        </nav>

        {/* User/Auth Section & Mobile Menu Trigger */}
        <div className="flex items-center space-x-4">
          {isAuthenticated ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="relative h-8 w-8 rounded-full">
                  <Avatar className="h-8 w-8">
                    {/* Placeholder avatar image, replace with actual user avatar */}
                    <AvatarImage src="https://github.com/shadcn.png" alt="@username" />
                    <AvatarFallback>JD</AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-56" align="end" forceMount>
                <DropdownMenuLabel className="font-normal">
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-medium leading-none">John Doe</p>
                    <p className="text-xs leading-none text-muted-foreground">
                      john.doe@example.com
                    </p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem>Profile</DropdownMenuItem>
                <DropdownMenuItem>Settings</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem>
                  <LogOut className="mr-2 h-4 w-4" />
                  <span>Log out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Button asChild>
              <Link href="/login" className="flex items-center gap-2">
                <LogIn className="h-4 w-4" />
                <span>Login</span>
              </Link>
            </Button>
          )}

          {/* Mobile Navigation Trigger */}
          <Sheet>
            <SheetTrigger asChild className="md:hidden">
              <Button variant="ghost" size="icon">
                <MenuIcon className="h-6 w-6" />
                <span className="sr-only">Toggle navigation menu</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-[300px] sm:w-[400px]">
              <nav className="flex flex-col gap-4 pt-8">
                {navLinks.map((link) => (
                  <Button key={link.href} variant="ghost" asChild className="justify-start">
                    <Link href={link.href} className="flex items-center gap-2 text-lg font-medium">
                      <link.icon className="h-5 w-5" />
                      <span>{link.label}</span>
                    </Link>
                  </Button>
                ))}
                {/* Potentially add mobile-specific auth links here if different from desktop */}
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}