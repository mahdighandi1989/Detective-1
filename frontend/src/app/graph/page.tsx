'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlowProvider,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type NodeMouseHandler,
  MarkerType,
  Position,
} from 'reactflow';
import 'reactflow/dist/style.css';

// ---------------------------------------------------------------------------
// Types — هم‌ارز با data shape برگشتی از backend (backend/app/api/routes/graph.py)
// ---------------------------------------------------------------------------

type RiskLevel = 'clean' | 'suspect' | 'infiltrator' | 'transformed' | 'unknown';

interface GraphPersonNode {
  id: string;
  label: string;
  current_position?: string | null;
  previous_position?: string | null;
  risk_level: RiskLevel;
  risk_score?: number | null;
  photo_url?: string | null;
  classification?: string | null;
}

interface GraphRelationEdge {
  id: string;
  source: string;
  target: string;
  relation_type?: string | null;
  label?: string | null;
  weight?: number | null;
}

interface GraphResponse {
  nodes: GraphPersonNode[];
  edges: GraphRelationEdge[];
}

// ---------------------------------------------------------------------------
// رنگ‌بندی بر اساس سطح خطر (طبق AC: نمودار با رنگ‌بندی بر اساس سطح خطر)
// ---------------------------------------------------------------------------

const RISK_META: Record<
  RiskLevel,
  { label: string; color: string; bg: string; border: string }
> = {
  clean: {
    label: 'پاک',
    color: '#16a34a',
    bg: 'rgba(22,163,74,0.12)',
    border: '#16a34a',
  },
  suspect: {
    label: 'مشکوک',
    color: '#d97706',
    bg: 'rgba(217,119,6,0.12)',
    border: '#d97706',
  },
  infiltrator: {
    label: 'نفوذی',
    color: '#dc2626',
    bg: 'rgba(220,38,38,0.12)',
    border: '#dc2626',
  },
  transformed: {
    label: 'استحاله‌یافته',
    color: '#9333ea',
    bg: 'rgba(147,51,234,0.12)',
    border: '#9333ea',
  },
  unknown: {
    label: 'نامشخص',
    color: '#64748b',
    bg: 'rgba(100,116,139,0.12)',
    border: '#64748b',
  },
};

function normalizeRisk(level: string | null | undefined): RiskLevel {
  if (!level) return 'unknown';
  const l = level.toLowerCase();
  if (l in RISK_META) return l as RiskLevel;
  // mapping احتمالی از مقادیر فارسی/جایگزین
  const map: Record<string, RiskLevel> = {
    pak: 'clean',
    mashkook: 'suspect',
    nofoozi: 'infiltrator',
    estehale: 'transformed',
    spy: 'infiltrator',
    agent: 'infiltrator',
  };
  return map[l] ?? 'unknown';
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') ||
  'http://localhost:8000';

// ---------------------------------------------------------------------------
// Layout ساده دایره‌ای برای node ها وقتی موقعیت از سرور نمی‌آید
// ---------------------------------------------------------------------------

function circularLayout(count: number, index: number) {
  const radius = Math.max(220, count * 45);
  const angle = (index / Math.max(count, 1)) * 2 * Math.PI;
  return {
    x: 600 + radius * Math.cos(angle),
    y: 400 + radius * Math.sin(angle),
  };
}

// ---------------------------------------------------------------------------
// تبدیل پاسخ API به nodes/edges مخصوص React Flow
// ---------------------------------------------------------------------------

function buildNodes(data: GraphResponse): Node[] {
  return data.nodes.map((p, i) => {
    const risk = normalizeRisk(p.risk_level);
    const meta = RISK_META[risk];
    return {
      id: p.id,
      type: 'default',
      position: circularLayout(data.nodes.length, i),
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: {
        label: (
          <div style={{ textAlign: 'right', direction: 'rtl' }}>
            <div style={{ fontWeight: 700, fontSize: 13 }}>{p.label}</div>
            {p.current_position ? (
              <div style={{ fontSize: 10, opacity: 0.8 }}>
                {p.current_position}
              </div>
            ) : null}
            <div
              style={{
                fontSize: 10,
                marginTop: 2,
                color: meta.color,
                fontWeight: 600,
              }}
            >
              {meta.label}
              {typeof p.risk_score === 'number'
                ? ` (${Math.round(p.risk_score)})`
                : ''}
            </div>
          </div>
        ),
        person: p,
        risk,
      },
      style: {
        background: meta.bg,
        border: `2px solid ${meta.border}`,
        borderRadius: 12,
        padding: 8,
        minWidth: 150,
        boxShadow: '0 1px 4px rgba(0,0,0,0.1)',
      },
    };
  });
}

function buildEdges(data: GraphResponse): Edge[] {
  return data.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label || e.relation_type || '',
    animated: false,
    style: { stroke: '#94a3b8', strokeWidth: e.weight ? 1 + e.weight : 1.5 },
    labelStyle: { fontSize: 10, fill: '#475569' },
    markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
  }));
}

// ---------------------------------------------------------------------------
// داده‌های نمونه برای زمانی که backend در دسترس نیست
// ---------------------------------------------------------------------------

const FALLBACK_DATA: GraphResponse = {
  nodes: [
    {
      id: 'p1',
      label: 'شخص نمونه ۱',
      current_position: 'سمت فعلی',
      risk_level: 'infiltrator',
      risk_score: 82,
    },
    {
      id: 'p2',
      label: 'شخص نمونه ۲',
      current_position: 'سمت فعلی',
      risk_level: 'suspect',
      risk_score: 55,
    },
    {
      id: 'p3',
      label: 'شخص نمونه ۳',
      current_position: 'سمت فعلی',
      risk_level: 'clean',
      risk_score: 10,
    },
    {
      id: 'p4',
      label: 'شخص نمونه ۴',
      current_position: 'سمت فعلی',
      risk_level: 'transformed',
      risk_score: 64,
    },
  ],
  edges: [
    { id: 'e1', source: 'p1', target: 'p2', relation_type: 'ارتباط کاری' },
    { id: 'e2', source: 'p2', target: 'p3', relation_type: 'آشنایی' },
    { id: 'e3', source: 'p1', target: 'p4', relation_type: 'ارتباط مالی' },
  ],
};

// ---------------------------------------------------------------------------
// کامپوننت داخلی گراف
// ---------------------------------------------------------------------------

function GraphCanvas() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [usingFallback, setUsingFallback] = useState(false);
  const [selected, setSelected] = useState<GraphPersonNode | null>(null);
  const [riskFilter, setRiskFilter] = useState<RiskLevel | 'all'>('all');

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    setUsingFallback(false);
    try {
      const token =
        typeof window !== 'undefined'
          ? localStorage.getItem('access_token')
          : null;
      const res = await fetch(`${API_BASE}/api/graph`, {
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        cache: 'no-store',
      });
      if (!res.ok) {
        throw new Error(`خطای سرور: ${res.status}`);
      }
      const data: GraphResponse = await res.json();
      setNodes(buildNodes(data));
      setEdges(buildEdges(data));
    } catch (err) {
      // در صورت در دسترس نبودن backend، داده نمونه نمایش داده می‌شود
      setUsingFallback(true);
      setError(
        err instanceof Error
          ? err.message
          : 'اتصال به سرور برقرار نشد؛ داده نمونه نمایش داده می‌شود.',
      );
      setNodes(buildNodes(FALLBACK_DATA));
      setEdges(buildEdges(FALLBACK_DATA));
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  const onConnect = useCallback(
    (connection: Connection) =>
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
            style: { stroke: '#94a3b8', strokeWidth: 1.5 },
          },
          eds,
        ),
      ),
    [setEdges],
  );

  const onNodeClick = useCallback<NodeMouseHandler>((_, node) => {
    const person = (node.data as { person?: GraphPersonNode })?.person;
    if (person) setSelected(person);
  }, []);

  // اعمال فیلتر سطح خطر روی نمایش node ها
  const filteredNodes = useMemo(() => {
    if (riskFilter === 'all') return nodes;
    return nodes.map((n) => ({
      ...n,
      hidden: (n.data as { risk?: RiskLevel })?.risk !== riskFilter,