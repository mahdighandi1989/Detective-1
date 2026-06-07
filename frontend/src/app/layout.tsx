import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils"; // Assuming shadcn/ui utils.ts is present
import { Header } from "@/components/Header"; // Assuming a Header component exists

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" }); // Using Inter as a default font, with a CSS variable

export const metadata: Metadata = {
  title: "Detective-1: پلتفرم دانشنامه و تحلیل اطلاعاتی",
  description: "پلتفرم جامع برای جمع‌آوری، تحلیل و ارزیابی اطلاعات OSINT و شناسایی افراد نفوذی.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fa" dir="rtl" suppressHydrationWarning>
      <body
        className={cn(
          "min-h-screen bg-background font-sans antialiased",
          inter.variable
        )}
      >
        <div className="relative flex min-h-screen flex-col">
          <Header />
          <main className="flex-1 container mx-auto py-8">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}