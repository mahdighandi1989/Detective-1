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