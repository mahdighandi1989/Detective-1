# Detective-1

> پلتفرم دانشنامه و تحلیل اطلاعاتی منبع‌باز (OSINT) — شناسایی، رهگیری و ارزیابی ریسک اشخاص

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)

---

## 📖 معرفی

**Detective-1** یک پلتفرم تحلیل اطلاعات منبع‌باز (OSINT) است که دو هستهٔ اصلی دارد:

1.  **دانشنامهٔ اطلاعاتی** — ذخیره، دسته‌بندی و خلاصه‌سازی خودکار محتوای مرتبط با مهارت‌های اطلاعاتی، نفوذ، جاسوسی و ضدجاسوسی به‌کمک مدل‌های زبانی (LLM). محتوا چه خام و چه پخته وارد می‌شود و توسط مدل‌ها دسته‌بندی، آنالیز و قابل جستجوی معنایی می‌شود.

2.  **ماژول پروفایل‌سازی و رهگیری اشخاص** — گردآوری اطلاعات عمومی هر فرد (عکس، سوابق، سمت‌های فعلی و قبلی، مواضع و عملکرد) از منابع باز اینترنتی با کمک مدل‌های جستجوگر (مانند Perplexity / Sonar)، اعتبارسنجی منابع، و نمایش در یک **نمودار ارتباطی (Graph)** رنگ‌بندی‌شده بر اساس سطح ریسک.

سیستم با اتکا بر داده‌های دانشنامه، ارزیابی خودکار سطح خطر هر پروفایل را ارائه می‌کند و افراد را به دسته‌های **پاک / مشکوک / نفوذی / استحاله‌یافته** طبقه‌بندی می‌کند.

> ⚠️ **هشدار قانونی و اخلاقی:** این ابزار صرفاً برای تحلیل اطلاعات **منبع‌باز و عمومی (OSINT)** و اهداف پژوهشی/امنیتی مجاز طراحی شده است. استفاده از آن باید با رعایت کامل قوانین حریم خصوصی، حفاظت از داده و مقررات محلی انجام شود. مسئولیت هرگونه استفادهٔ نادرست بر عهدهٔ کاربر است.

---

## 🧱 معماری و پشتهٔ فناوری

### Backend
| لایه | فناوری |
|------|---------|
| API Framework | FastAPI (Python 3.11+) |
| ORM & Migration | SQLAlchemy 2.0 + Alembic |
| پایگاه دادهٔ رابطه‌ای | PostgreSQL |
| گراف ارتباطی | Neo4j |
| جستجوی معنایی | pgvector / Qdrant |
| صف کارهای پس‌زمینه | Celery + Redis |
| یکپارچه‌سازی LLM | OpenAI / Perplexity Sonar / Gemini |
| ذخیره‌سازی فایل | MinIO / S3 |

### Frontend
| لایه | فناوری | توضیحات |
|------|---------|-------------|
| Framework | Next.js 14 (App Router) | فریم‌ورک React برای ساخت رابط کاربری سمت سرور و کلاینت. |
| Language | TypeScript | جاوااسکریپت با Type Safety برای کدنویسی قابل اطمینان‌تر. |
| Styling | Tailwind CSS | فریم‌ورک CSS Utility-first برای طراحی سریع و منعطف. |
| UI Components | shadcn/ui | مجموعه‌ای از کامپوننت‌های UI قابل تنظیم و دسترسی‌پذیر بر پایه Tailwind CSS و Radix UI. |
| Graph Visualization | React Flow / Cytoscape.js | برای نمایش نمودارهای ارتباطی تعاملی. |

---

## 🚀 راه‌اندازی و اجرا

برای راه‌اندازی و اجرای پروژه Detective-1، مراحل زیر را دنبال کنید:

### پیش‌نیازها

*   [Docker](https://www.docker.com/get-started/) و [Docker Compose](https://docs.docker.com/compose/install/)
*   [Node.js](https://nodejs.org/en/download/) (نسخه ۱۸ یا بالاتر) و npm/yarn
*   [Python](https://www.python.org/downloads/) (نسخه ۳.۱۱ یا بالاتر)

### ۱. شبیه‌سازی مخزن (Clone Repository)

```bash
git clone <URL_مخزن_شما>
cd Detective-1
```
> **توجه:** `<URL_مخزن_شما>` را با آدرس واقعی مخزن جایگزین کنید.

### ۲. پیکربندی متغیرهای محیطی

پروژه از فایل‌های `.env` برای مدیریت متغیرهای محیطی در بخش‌های مختلف استفاده می‌کند.
1.  **Backend:** یک فایل `.env` در مسیر `backend/.env` ایجاد کنید و محتوای `backend/.env.example` را در آن کپی کرده و مقادیر را تنظیم کنید.
2.  **Frontend:** یک فایل `.env.local` در مسیر `frontend/.env.local` ایجاد کنید و محتوای `frontend/.env.example` را در آن کپی کرده و مقادیر را تنظیم کنید.

### ۳. راه‌اندازی Backend (FastAPI, PostgreSQL, Neo4j, Redis, Celery)

پروژه از Docker Compose برای مدیریت سرویس‌های بک‌اند (FastAPI، PostgreSQL، Neo4j، Redis و Celery) استفاده می‌کند.

1.  **ساخت و اجرای سرویس‌ها:**
    از ریشه پروژه، دستور زیر را اجرا کنید:
    ```bash
    docker-compose up --build -d
    ```
    این دستور Docker images را build کرده و سرویس‌ها را در پس‌زمینه اجرا می‌کند.

2.  **اجرای Migrationهای دیتابیس (PostgreSQL):**
    پس از بالا آمدن سرویس‌ها، migrationهای دیتابیس را اجرا کنید:
    ```bash
    docker-compose exec backend alembic upgrade head
    ```

3.  **(اختیاری) راه‌اندازی اولیه Neo4j:**
    اگر نیاز به تنظیمات اولیه یا ایجاد کاربر در Neo4j دارید، می‌توانید از طریق Neo4j Browser (معمولاً در `http://localhost:7474` اگر پورت آن در `docker-compose.yml` expose شده باشد) اقدام کنید. اطلاعات ورود پیش‌فرض در `docker-compose.yml` یا `backend/.env` قابل تنظیم است.

### ۴. راه‌اندازی Frontend (Next.js)

1.  **نصب وابستگی‌ها:**
    وارد دایرکتوری `frontend` شوید و وابستگی‌ها را نصب کنید:
    ```bash
    cd frontend
    npm install # یا yarn install
    ```

2.  **اجرای سرور توسعه:**
    در همان دایرکتوری `frontend`، سرور توسعه را اجرا کنید:
    ```bash
    npm run dev # یا yarn dev
    ```
    فرانت‌اند در `http://localhost:3000` قابل دسترسی خواهد بود.

### ۵. دسترسی به پنل‌ها و ابزارها

*   **FastAPI Backend API Docs:** `http://localhost:8000/docs`
*   **Frontend Application:** `http://localhost:3000`
*   **Neo4j Browser:** `http://localhost:7474` (اگر در `docker-compose.yml` پورت آن را expose کرده‌اید)
*   **Redis Commander:** `http://localhost:8081` (برای مدیریت Redis، اگر فعال شده باشد)
*   **Celery Flower:** `http://localhost:5555` (برای نظارت بر Celery tasks)

---

## 🧪 تست‌ها

برای اجرای تست‌ها در هر بخش:

### Backend Tests (Python)

```bash
docker-compose exec backend pytest
```

### Frontend Tests (Next.js/React)

```bash
cd frontend