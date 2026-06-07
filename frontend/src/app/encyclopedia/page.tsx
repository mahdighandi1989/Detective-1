'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';

type Classification = 'public' | 'confidential' | 'secret' | 'top_secret';
type ContentType = 'raw' | 'processed';

interface Source {
  id: string;
  url?: string;
  title?: string;
  credibilityScore?: number;
}

interface Article {
  id: string;
  title: string;
  summary?: string;
  content: string;
  contentType: ContentType;
  category?: string;
  tags: string[];
  classification: Classification;
  sources: Source[];
  createdAt: string;
  updatedAt: string;
  relatedPersonIds?: string[];
}

interface SearchResult extends Article {
  score?: number;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') ||
  'http://localhost:8000';

const CLASSIFICATION_LABELS: Record<Classification, string> = {
  public: 'عمومی',
  confidential: 'محرمانه',
  secret: 'سری',
  top_secret: 'فوق سری',
};

const CLASSIFICATION_COLORS: Record<Classification, string> = {
  public: 'bg-green-100 text-green-800 border-green-300',
  confidential: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  secret: 'bg-orange-100 text-orange-800 border-orange-300',
  top_secret: 'bg-red-100 text-red-800 border-red-300',
};

const CONTENT_TYPE_LABELS: Record<ContentType, string> = {
  raw: 'خام',
  processed: 'پخته/خلاصه‌شده',
};

function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return (
    window.localStorage.getItem('detective1_token') ||
    window.localStorage.getItem('access_token')
  );
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let detail = `خطای سرور (${res.status})`;
    try {
      const data = await res.json();
      detail = data?.detail || data?.message || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }

  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

const EMPTY_FORM = {
  title: '',
  content: '',
  contentType: 'raw' as ContentType,
  category: '',
  tags: '',
  classification: 'confidential' as Classification,
  sourceUrls: '',
};

export default function EncyclopediaPage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(
    null
  );
  const [searching, setSearching] = useState(false);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [submitting, setSubmitting] = useState(false);
  const [analyzing, setAnalyzing] = useState<string | null>(null);

  const [selected, setSelected] = useState<Article | null>(null);

  const loadArticles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<Article[] | { items: Article[] }>(
        '/api/encyclopedia/articles'
      );
      const list = Array.isArray(data) ? data : data.items ?? [];
      setArticles(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'خطا در بارگذاری مقالات');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadArticles();
  }, [loadArticles]);

  const handleSemanticSearch = useCallback(async () => {
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    setError(null);
    try {
      const data = await apiFetch<SearchResult[] | { results: SearchResult[] }>(
        `/api/encyclopedia/search?q=${encodeURIComponent(q)}`
      );
      const results = Array.isArray(data) ? data : data.results ?? [];
      setSearchResults(results);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'خطا در جستجوی معنایی');
    } finally {
      setSearching(false);
    }
  }, [searchQuery]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        title: form.title.trim(),
        content: form.content.trim(),
        content_type: form.contentType,
        category: form.category.trim() || null,
        tags: form.tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
        classification: form.classification,
        source_urls: form.sourceUrls
          .split('\n')
          .map((u) => u.trim())
          .filter(Boolean),
        auto_summarize: true,
        auto_categorize: true,
      };
      await apiFetch<Article>('/api/encyclopedia/articles', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setForm({ ...EMPTY_FORM });
      setShowForm(false);
      await loadArticles();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'خطا در ایجاد مقاله');
    } finally {
      setSubmitting(false);
    }
  };

  const handleAnalyze = async (article: Article) => {
    setAnalyzing(article.id);
    setError(null);
    try {
      await apiFetch<Article>(
        `/api/encyclopedia/articles/${article.id}/analyze`,
        { method: 'POST' }
      );
      await loadArticles();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'خطا در تحلیل مقاله');
    } finally {
      setAnalyzing(null);
    }
  };

  const handleDelete = async (article: Article) => {
    if (!window.confirm(`حذف مقاله «${article.title}»؟`)) return;
    setError(null);
    try {
      await apiFetch<void>(`/api/encyclopedia/articles/${article.id}`, {
        method: 'DELETE',
      });
      setSelected(null);
      await loadArticles();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'خطا در حذف مقاله');
    }
  };

  const displayed: Article[] = searchResults ?? articles;

  return (
    <div className="min-h-screen bg-slate-50" dir="rtl">
      <header className="border-b bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              دانشنامهٔ اطلاعاتی
            </h1>
            <p className="text-sm text-slate-500">
              ذخیره، دسته‌بندی و تحلیل خودکار محتوای اطلاعاتی، نفوذ و ضدجاسوسی
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/persons"
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
            >
              اشخاص
            </Link>
            <Link
              href="/graph"
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
            >
              نمودار ارتباطی
            </Link>
            <button
              onClick={() => setShowForm((s) => !s)}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
            >
              {showForm ? 'بستن فرم' : '+ ورودی جدید'}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {/* جستجوی معنایی */}
        <div className="mb-6 rounded-lg border bg-white p-4 shadow-sm">
          <label className="mb-2 block text-sm font-medium text-slate-700">
            جستجوی معنایی (Semantic Search)
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSemanticSearch();
              }}
              placeholder="مثلاً: روش‌های شناسایی نفوذ سازمانی…"
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <button
              onClick={handleSemanticSearch}
              disabled={searching}
              className="rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-900 disabled:opacity-50"
            >
              {searching ? 'در حال جستجو…' : 'جستجو'}
            </button>
            {searchResults !== null && (
              <button
                onClick={() => {
                  setSearchResults(null);
                  setSearchQuery('');
                }}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
              >
                پاک‌کردن
              </button>
            )}
          </div>
          {searchResults !== null && (
            <p className="mt-2 text-xs text-slate-500">
              {searchResults.length} نتیجهٔ مرتبط بر اساس embeddings
            </p>
          )}
        </div>

        {/* فرم ایجاد */}
        {showForm && (
          <form
            onSubmit={handleCreate}
            className="mb-6 space-y-4 rounded-lg border bg-white p-5 shadow-sm"
          >
            <h2 className="text-lg font-semibold text-slate-900">
              ورودی جدید دانشنامه
            </h2>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  عنوان
                </label>
                <input
                  type="text"
                  required
                  value={form.title}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, title: e.target.value }))
                  }
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  دسته‌بندی
                </label>
                <input
                  type="text"
                  value={form.category}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, category: e.target.value }))
                  }
                  placeholder="مثلاً: نفوذ، ضدجاسوسی"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <p className="mt-1 text-[11px] text-slate-400">
                  در صورت خالی‌بودن، به‌صورت خودکار دسته‌بندی می‌شود.
                </p>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  سطح طبقه‌بندی
                </label>
                <select
                  value={form.classification}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      classification: e.target.value as Classification,
                    }))
                  }
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  {(Object.keys(CLASSIFICATION_LABELS) as Classification[]).map(
                    (c) => (
                      <option key={c} value={c}>
                        {CLASSIFICATION_LABELS[c]}
                      </option>
                    ),
                  )}
                </select>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  نوع محتوا
                </label>
                <select
                  value={form.contentType}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      contentType: e.target.value as ContentType,
                    }))
                  }
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  {(Object.keys(CONTENT_TYPE_LABELS) as ContentType[]).map(
                    (t) => (
                      <option key={t} value={t}>
                        {CONTENT_TYPE_LABELS[t]}
                      </option>
                    ),
                  )}
                </select>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  برچسب‌ها
                </label>
                <input
                  type="text"
                  value={form.tags}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, tags: e.target.value }))
                  }
                  placeholder="با کاما جدا کنید"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  منابع (هر خط یک نشانی)
                </label>
                <textarea
                  rows={2}
                  value={form.sourceUrls}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, sourceUrls: e.target.value }))
                  }
                  placeholder="https://…"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  محتوا
                </label>
                <textarea
                  rows={6}
                  required
                  value={form.content}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, content: e.target.value }))
                  }
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setForm({ ...EMPTY_FORM });
                  setShowForm(false);
                }}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
              >
                انصراف
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
              >
                {submitting ? 'در حال ذخیره…' : 'ذخیره و تحلیل خودکار'}
              </button>
            </div>
          </form>
        )}

        {/* خطا */}
        {error && (
          <div className="mb-6 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        )}

        {/* فهرست مقالات */}
        {loading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-44 animate-pulse rounded-lg border bg-white p-4 shadow-sm"
              >
                <div className="mb-3 h-4 w-2/3 rounded bg-slate-200" />
                <div className="space-y-2">
                  <div className="h-3 w-full rounded bg-slate-100" />
                  <div className="h-3 w-5/6 rounded bg-slate-100" />
                  <div className="h-3 w-4/6 rounded bg-slate-100" />
                </div>
              </div>
            ))}
          </div>
        ) : displayed.length === 0 ? (
          <div className="rounded-lg border border-dashed bg-white py-16 text-center">
            <p className="text-sm font-medium text-slate-700">
              {searchResults !== null
                ? 'نتیجه‌ای برای جستجوی شما یافت نشد.'
                : 'هنوز مقاله‌ای ثبت نشده است.'}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              برای افزودن محتوای جدید روی «+ ورودی جدید» بزنید.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {displayed.map((article) => (
              <article
                key={article.id}
                onClick={() => setSelected(article)}
                className="flex cursor-pointer flex-col rounded-lg border bg-white p-4 shadow-sm transition hover:shadow-md"
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <h3 className="line-clamp-2 text-sm font-bold text-slate-900">
                    {article.title}
                  </h3>
                  <span
                    className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium ${CLASSIFICATION_COLORS[article.classification]}`}
                  >
                    {CLASSIFICATION_LABELS[article.classification]}
                  </span>
                </div>
                <p className="mb-3 line-clamp-3 flex-1 text-xs text-slate-600">
                  {article.summary || article.content}
                </p>
                {article.tags.length > 0 && (
                  <div className="mb-3 flex flex-wrap gap-1">
                    {article.tags.slice(0, 4).map((tag) => (
                      <span
                        key={tag}
                        className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex items-center justify-between border-t pt-2 text-[11px] text-slate-400">
                  <span>{CONTENT_TYPE_LABELS[article.contentType]}</span>
                  <span>{article.sources.length} منبع</span>
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleAnalyze(article);
                    }}
                    disabled={analyzing === article.id}
                    className="flex-1 rounded-md bg-slate-800 px-2 py-1.5 text-[11px] font-medium text-white transition hover:bg-slate-900 disabled:opacity-50"
                  >
                    {analyzing === article.id ? 'در حال تحلیل…' : 'تحلیل مجدد'}
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(article);
                    }}
                    className="rounded-md border border-red-300 px-2 py-1.5 text-[11px] font-medium text-red-600 transition hover:bg-red-50"
                  >
                    حذف
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>

      {/* مودال جزئیات مقاله */}
      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
          onClick={() => setSelected(null)}
        >
          <div
            className="my-8 w-full max-w-2xl rounded-xl bg-white p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
            dir="rtl"
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-slate-900">
                  {selected.title}
                </h2>
                {selected.category && (
                  <p className="mt-1 text-xs text-slate-500">
                    دسته: {selected.category}
                  </p>
                )}
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-slate-400 transition hover:text-slate-700"
                aria-label="بستن"
              >
                ✕
              </button>
            </div>

            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span
                className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${CLASSIFICATION_COLORS[selected.classification]}`}
              >
                {CLASSIFICATION_LABELS[selected.classification]}
              </span>
              <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
                {CONTENT_TYPE_LABELS[selected.contentType]}
              </span>
              {selected.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600"
                >
                  #{tag}
                </span>
              ))}
            </div>

            {selected.summary && (
              <div className="mb-4 rounded-lg bg-blue-50 p-3">
                <p className="mb-1 text-xs font-semibold text-blue-800">
                  خلاصهٔ خودکار
                </p>
                <p className="text-sm leading-relaxed text-slate-700">
                  {selected.summary}
                </p>
              </div>
            )}

            <div className="mb-4 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg border bg-slate-50 p-3 text-sm leading-relaxed text-slate-800">
              {selected.content}
            </div>

            {selected.sources.length > 0 && (
              <div className="mb-4">
                <p className="mb-2 text-xs font-semibold text-slate-700">منابع</p>
                <ul className="space-y-1">
                  {selected.sources.map((s) => (
                    <li key={s.id} className="text-xs text-slate-600">
                      {s.url ? (
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline"
                        >
                          {s.title || s.url}
                        </a>
                      ) : (
                        s.title || 'منبع نامشخص'
                      )}
                      {typeof s.credibilityScore === 'number' && (
                        <span className="mr-2 text-slate-400">
                          اعتبار: {s.credibilityScore}%
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex items-center justify-end gap-2 border-t pt-4">
              <button
                onClick={() => handleAnalyze(selected)}
                disabled={analyzing === selected.id}
                className="rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-900 disabled:opacity-50"
              >
                {analyzing === selected.id ? 'در حال تحلیل…' : 'تحلیل مجدد'}
              </button>
              <button
                onClick={() => handleDelete(selected)}
                className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-600 transition hover:bg-red-50"
              >
                حذف مقاله
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}