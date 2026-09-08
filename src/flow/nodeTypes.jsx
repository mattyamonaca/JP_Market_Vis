import React from 'react';
import { Handle, Position } from '@xyflow/react';
import { SEGMENT_JA } from '../data/graph.js';

const SEGMENT_COLORS = {
  prime: '#facc15',
  standard: '#38bdf8',
  growth: '#4ade80',
};

// 中心企業ノード
export function CenterNode({ data }) {
  return (
    <div
      style={{
        background: 'linear-gradient(135deg, #1e293b, #334155)',
        border: '3px solid #facc15',
        borderRadius: 12,
        padding: '14px 22px',
        minWidth: 180,
        textAlign: 'center',
        boxShadow: '0 0 24px rgba(250, 204, 21, 0.35)',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <div style={{ fontSize: 16, fontWeight: 700, color: '#f1f5f9' }}>{data.label}</div>
      <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
        {data.code} ・ {SEGMENT_JA[data.segment] ?? ''} ・ {data.industry ?? ''}
      </div>
      <div style={{ fontSize: 12, color: '#facc15', marginTop: 2 }}>関係 {data.degree} 件</div>
    </div>
  );
}

// 隣接ノード（上場企業: クリックで中心に移動可能）
export function ListedNode({ data }) {
  const segColor = SEGMENT_COLORS[data.segment] ?? '#64748b';
  return (
    <div
      style={{
        background: '#1e293b',
        border: `2px solid ${segColor}`,
        borderRadius: 10,
        padding: '8px 14px',
        minWidth: 130,
        textAlign: 'center',
        cursor: 'pointer',
        opacity: data.dimmed ? 0.25 : 1,
        transition: 'opacity 0.2s ease',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <div style={{ fontSize: 14, fontWeight: 600, color: '#f1f5f9' }}>{data.label}</div>
      <div style={{ fontSize: 12, color: segColor, marginTop: 2 }}>
        {data.code} ・ {SEGMENT_JA[data.segment] ?? '上場'}
      </div>
    </div>
  );
}

// 隣接ノード（非上場エンティティ）
export function EntityNode({ data }) {
  return (
    <div
      style={{
        background: 'rgba(30, 41, 59, 0.6)',
        border: '2px dashed #64748b',
        borderRadius: 10,
        padding: '8px 14px',
        minWidth: 120,
        textAlign: 'center',
        opacity: data.dimmed ? 0.25 : 1,
        transition: 'opacity 0.2s ease',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <div style={{ fontSize: 12, fontWeight: 500, color: '#cbd5e1' }}>{data.label}</div>
      <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>非上場</div>
    </div>
  );
}

export const nodeTypes = {
  center: CenterNode,
  listed: ListedNode,
  entity: EntityNode,
};
