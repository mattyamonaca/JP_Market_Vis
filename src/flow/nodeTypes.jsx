import React from 'react';
import { Handle, Position } from '@xyflow/react';
import { SEGMENT_COLORS, SEGMENT_JA } from '../data/graph.js';

// 白基調（Issue #23）: カードは白地に細い枠。市場区分は枠と小さな文字の色で示す
const cardBase = {
  background: 'var(--bg)',
  borderRadius: 10,
  textAlign: 'center',
  transition: 'opacity 0.2s ease',
};

// 中心企業ノード
export function CenterNode({ data }) {
  return (
    <div
      style={{
        ...cardBase,
        border: '2px solid var(--accent)',
        padding: '14px 22px',
        minWidth: 180,
        boxShadow: '0 4px 18px rgba(15, 23, 42, 0.12)',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{data.label}</div>
      <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>
        {data.code} ・ {SEGMENT_JA[data.segment] ?? ''} ・ {data.industry ?? ''}
      </div>
      <div style={{ fontSize: 12, color: 'var(--accent)', marginTop: 2, fontWeight: 600 }}>関係 {data.degree} 件</div>
    </div>
  );
}

// 隣接ノード（上場企業: クリックで中心に移動可能）
export function ListedNode({ data }) {
  const segColor = SEGMENT_COLORS[data.segment] ?? 'var(--text-3)';
  return (
    <div
      style={{
        ...cardBase,
        border: `2px solid ${segColor}`,
        padding: '8px 14px',
        minWidth: 130,
        cursor: 'pointer',
        opacity: data.dimmed ? 0.25 : 1,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{data.label}</div>
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
        ...cardBase,
        background: 'var(--surface)',
        border: '1.5px dashed var(--border-strong)',
        padding: '8px 14px',
        minWidth: 120,
        opacity: data.dimmed ? 0.25 : 1,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{data.label}</div>
      <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>非上場</div>
    </div>
  );
}

export const nodeTypes = {
  center: CenterNode,
  listed: ListedNode,
  entity: EntityNode,
};
