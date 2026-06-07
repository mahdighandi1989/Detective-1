'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';

// ---------------------------------------------------------------------------
// Types (cross-tier: mirror of backend/app/schemas/person.py)
// ---------------------------------------------------------------------------

export type RiskCategory =
  | 'clean'
  | 'suspect'
  | 'infiltrator'
  | 'transformed'
  | 'unknown';

export interface PersonPosition {
  title: string;
  organization?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current: boolean;
}

export interface PersonSummary {
  id: string;
  full_name: string;
  aliases: string[];
  photo_url?: string | null;
  current_position?: string | null;
  current_organization?: string | null;
  risk_category: RiskCategory;
  risk_score: number; // 0..100
  classification_level: 'public' | 'restricted' | 'confidential' | 'secret';
  positions_count: number;
  sources_count: number;
  last_updated: string; // ISO
  created_at: string; // ISO
}

interface PersonListResponse {
  items: PersonSummary[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Constants & helpers
// ---------------------------------------------------------------------------

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') ||
  'http://localhost:8000';

const PAGE_SIZE = 12;

const RISK_META: Record<
  RiskCategory,
  { label: string; dot: string; ring: string; badge: string; order: number }
> = {
  infiltrator: {
    label: 'نفوذی',
    dot: 'bg-red-500',
    ring: 'ring-red-500/40',
    badge: 'bg-red-500/10 text-red-400 border-red-500/30',
    order: 0,
  },
  suspect: {
    label: 'مشکوک',
    dot: 'bg-amber-500',
    ring: 'ring-amber-500/40',
    badge: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    order: 1,
  },
  transformed: {
    label: 'استحاله‌یافته',
    dot: 'bg-purple-500',
    ring: 'ring-purple-500/40',
    badge: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
    order: 2,
  },
  clean: {
    label: 'پاک',
    dot: 'bg-emerald-500',
    ring: 'ring-emerald-500/40',
    badge: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    order: 3,
  },
  unknown: {
    label: 'نامشخص',
    dot: 'bg-slate-500',
    ring: 'ring-slate-500/40',
    badge: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
    order: 4,
  },
};

const CLASSIFICATION_LABEL: Record<PersonSummary['classification_level'], string> =
  {
    public: 'عمومی',
    restricted: 'محدود',
    confidential: 'محرمانه',
    secret: 'سری',
  };

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return (
    window.localStorage.getItem('access_token') ||
    window.localStorage.getItem('token')
  );
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat('fa-IR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '؟';
  if (parts.length === 1) return parts[0].slice(0, 2);
  return parts[0][0] + parts[parts.length - 1][0];
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RiskBadge({ category }: { category: RiskCategory }) {
  const meta = RISK_META[category] ?? RISK_META.unknown;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.badge}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}

function RiskMeter({ score, category }: { score: number; category: RiskCategory }) {
  const meta = RISK_META[category] ?? RISK_META.unknown;
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div className="w-full">
      <div className="mb-1 flex items-center justify-between text-[11px] text-slate-400">
        <span>سطح خطر</span>
        <span className="font-mono">{clamped}٪</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-700/60">
        <div
          className={`h-full rounded-full ${meta.dot} transition-all`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}

function PersonCard({ person }: { person: PersonSummary }) {
  const meta = RISK_META[person.risk_category] ?? RISK_META.unknown;
  return (
    <Link
      href={`/persons/${person.id}`}
      className={`group relative flex flex-col gap-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4 shadow-sm ring-1 ring-transparent transition hover:border-slate-700 hover:bg-slate-900 hover:ring-2 hover:${meta.ring}`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`relative h-14 w-14 shrink-0 overflow-hidden rounded-lg bg-slate-800 ring-2 ${meta.ring}`}
        >
          {person.photo_url ? (
            <Image
              src={person.photo_url}
              alt={person.full_name}
              fill
              sizes="56px"
              className="object-cover"
              unoptimized
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm font-semibold text-slate-300">
              {initials(person.full_name)}
            </div>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-slate-100">
              {person.full_name}
            </h3>
          </div>
          {person.aliases.length > 0 && (
            <p className="truncate text-xs text-slate-500">
              {person.aliases.join('، ')}
            </p>
          )}
          <p className="mt-0.5 truncate text-xs text-slate-400">
            {person.current_position || 'سمت نامشخص'}
            {person.current_organization
              ? ` — ${person.current_organization}`
              : ''}
          </p>
        </div>

        <RiskBadge category={person.risk_category} />
      </div>

      <RiskMeter score={person.risk_score} category={person.risk_category} />

      <div className="flex items-center justify-between border-t border-slate-800 pt-3 text-[11px] text-slate-500">
        <span>{person.positions_count} سمت</span>
        <span>{person.sources_count} منبع</span>
        <span className="rounded border border-slate-700 px-1.5 py-0.5">
          {CLASSIFICATION_LABEL[person.classification_level]}
        </span>
        <span title={person.last_updated}>{formatDate(person.last_updated)}</span>
      </div>
    </Link>
  );
}

function PersonCardSkeleton() {
  return (
    <div className="flex animate-pulse flex-col gap-4 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-start gap-3">
        <div className="h-14 w-14 rounded-lg bg-slate-800" />
        <div className="flex-1 space-y-2">
          <div className="h-3 w-3/4 rounded bg-slate-800" />
          <div className="h-2 w-1/2 rounded bg-slate-800" />
          <div className="h-2 w-2/3 rounded bg-slate-800" />
        </div>
      </div>
      <div className="h-1.5 w-full rounded-full bg-slate-800" />
      <div className="h-3 w-full rounded bg-slate-800" />
    </div>
  );
}

function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  return (
    <div className="col-span-full flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-slate-900/40 py-16 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 text-2xl">
        🔍
      </div>
      <h3 className="text-sm font-semibold text-slate-200">
        {hasFilters ? 'هیچ شخصی با این فیلترها یافت نشد' : 'هنوز شخصی ثبت نشده'}
      </h3>
      <p className="mt-1 max-w-sm text-xs text-slate-500">
        {hasFilters
          ? 'فیلترها را تغییر دهید یا عبارت جستجو را پاک کنید.'
          : 'برای شروع شناسایی، یک پروفایل جدید ایجاد کنید تا Agent جستجوگر سوابق آن را گردآوری کند.'}
      </p>
      {!hasFilters && (
        <Link
          href="/persons/new"
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500"
        >
          + افزودن شخص
        </Link>
      )}
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="col-span-full flex flex-col items-center justify-center rounded-xl border border-red-900/50 bg-red-950/20 py-16 text-center">
      <div className="mb-3 text-2xl">⚠️</div>
      <h3 className="text-sm font-semibold text-red-300">خطا در دریافت داده‌ها</h3>
      <p className="mt-1 max-w-md text-xs text-red-400/80">{message}</p>
      <button
        onClick={onRetry}
        className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-200 transition hover:bg-red-500/20"
      >
        تلاش مجدد
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const RISK_ORDER: RiskCategory[] = [
  'infiltrator',
  'suspect',
  'transformed',
  'clean',
  'unknown',
];

const RISK_FILTERS: Array<{ value: RiskCategory | 'all'; label: string }> = [
  { value: 'all', label: 'همه' },
  ...RISK_ORDER.map((value) => ({ value, label: RISK_META[value].label })),
];

export default function PersonsPage() {
  const [persons, setPersons] = useState<PersonSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [riskFilter, setRiskFilter] = useState<RiskCategory | 'all'>('all');

  const loadPersons = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE}/api/v1/persons?page=1&page_size=100`,
        {
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          cache: 'no-store',
        },
      );
      if (!res.ok) {
        throw new Error(`خطای سرور: ${res.status}`);
      }
      const data: PersonListResponse | PersonSummary[] = await res.json();
      const items = Array.isArray(data) ? data : data.items ?? [];
      setPersons(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'اتصال به سرور برقرار نشد.');
      setPersons([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPersons();
  }, [loadPersons]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return persons
      .filter((p) =>
        riskFilter === 'all' ? true : p.risk_category === riskFilter,
      )
      .filter((p) => {
        if (!q) return true;
        const haystack = [
          p.full_name,
          p.current_position ?? '',
          p.current_organization ?? '',
          ...p.aliases,
        ]
          .join(' ')
          .toLowerCase();
        return haystack.includes(q);
      })
      .sort(
        (a, b) =>
          (RISK_META[a.risk_category]?.order ?? 99) -
            (RISK_META[b.risk_category]?.order ?? 99) ||
          b.risk_score - a.risk_score,
      );
  }, [persons, query, riskFilter]);

  const hasFilters = query.trim().length > 0 || riskFilter !== 'all';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100" dir="rtl">
      <div className="mx-auto max-w-7xl px-4 py-6">
        {/* Header */}
        <div className="mb-6 flex flex-col gap-4 border-b border-slate-800 pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-50">اشخاص</h1>
            <p className="mt-1 text-sm text-slate-400">
              پروفایل‌های شناسایی‌شده به همراه سطح خطر و سوابق.
              {!loading && !error && (
                <span className="ml-1 text-slate-500">
                  ({filtered.length.toLocaleString('fa-IR')} نتیجه)
                </span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/graph"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800"
            >
              نمودار ارتباطی
            </Link>
            <Link
              href="/persons/new"
              className="inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500"
            >
              + افزودن شخص
            </Link>
          </div>
        </div>

        {/* Controls */}
        <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative w-full lg:max-w-sm">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="جستجو بر اساس نام، سمت یا سازمان…"
              className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 pl-9 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-600 focus:outline-none focus:ring-1 focus:ring-cyan-600"
            />
            <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-500">
              🔍
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {RISK_FILTERS.map((f) => {
              const active = riskFilter === f.value;
              return (
                <button
                  key={f.value}
                  onClick={() => setRiskFilter(f.value)}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                    active
                      ? 'border-cyan-500/50 bg-cyan-500/15 text-cyan-300'
                      : 'border-slate-800 bg-slate-900 text-slate-400 hover:bg-slate-800'
                  }`}
                >
                  {f.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Grid */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {loading ? (
            Array.from({ length: 8 }).map((_, i) => (
              <PersonCardSkeleton key={i} />
            ))
          ) : error ? (
            <ErrorState message={error} onRetry={loadPersons} />
          ) : filtered.length === 0 ? (
            <EmptyState hasFilters={hasFilters} />
          ) : (
            filtered.map((person) => (
              <PersonCard key={person.id} person={person} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}