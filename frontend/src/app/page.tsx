import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-900 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl w-full space-y-8 text-center">
        <div>
          <h1 className="text-5xl font-extrabold text-gray-900 dark:text-white sm:text-6xl">
            Detective-1
          </h1>
          <p className="mt-4 text-xl text-gray-600 dark:text-gray-300">
            پلتفرم دانشنامه و تحلیل اطلاعاتی (OSINT)
          </p>
          <p className="mt-2 text-lg text-gray-500 dark:text-gray-400">
            شناسایی و رهگیری تا دستگیری
          </p>
        </div>

        <div className="mt-10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <Card className="flex flex-col justify-between">
            <CardHeader>
              <CardTitle className="text-right">دانشنامه اطلاعاتی</CardTitle>
              <CardDescription className="text-right">
                ذخیره، دسته‌بندی و خلاصه‌سازی محتوای مرتبط با اطلاعات و نفوذ.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex justify-end">
              <Button asChild>
                <Link href="/encyclopedia">مشاهده دانشنامه</Link>
              </Button>
            </CardContent>
          </Card>

          <Card className="flex flex-col justify-between">
            <CardHeader>
              <CardTitle className="text-right">پروفایل اشخاص</CardTitle>
              <CardDescription className="text-right">
                گردآوری و تحلیل اطلاعات عمومی افراد (سوابق، سمت‌ها، عملکرد).
              </CardDescription>
            </CardHeader>
            <CardContent className="flex justify-end">
              <Button asChild>
                <Link href="/persons">مشاهده پروفایل‌ها</Link>
              </Button>
            </CardContent>
          </Card>

          <Card className="flex flex-col justify-between">
            <CardHeader>
              <CardTitle className="text-right">نمودار ارتباطی</CardTitle>
              <CardDescription className="text-right">
                نمایش بصری ارتباطات و سطح ریسک افراد با رنگ‌بندی.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex justify-end">
              <Button asChild>
                <Link href="/graph">مشاهده نمودار</Link>
              </Button>
            </CardContent>
          </Card>

          <Card className="flex flex-col justify-between">
            <CardHeader>
              <CardTitle className="text-right">جستجوی معنایی</CardTitle>
              <CardDescription className="text-right">
                جستجوی پیشرفته و هوشمند در محتوای دانشنامه.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex justify-end">
              <Button asChild>
                <Link href="/search">شروع جستجو</Link>
              </Button>
            </CardContent>
          </Card>

          <Card className="flex flex-col justify-between">
            <CardHeader>
              <CardTitle className="text-right">موتور ارزیابی ریسک</CardTitle>
              <CardDescription className="text-right">
                ارزیابی خودکار سطح خطر هر پروفایل بر اساس شواهد.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex justify-end">
              <Button asChild>
                <Link href="/risk-assessment">ارزیابی ریسک</Link>
              </Button>
            </CardContent>
          </Card>

          <Card className="flex flex-col justify-between">
            <CardHeader>
              <CardTitle className="text-right">ورود / ثبت نام</CardTitle>
              <CardDescription className="text-right">
                برای دسترسی به امکانات کامل پلتفرم.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex justify-end">
              <Button asChild>
                <Link href="/auth">ورود</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}