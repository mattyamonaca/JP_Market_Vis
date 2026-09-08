// Rotate the layout without changing distances or the links' node references.
export function rotateNodes(nodes, angle) {
  const positioned = nodes.filter((node) => Number.isFinite(node.x) && Number.isFinite(node.y));
  if (!positioned.length || !Number.isFinite(angle)) return;
  const cx = positioned.reduce((sum, node) => sum + node.x, 0) / positioned.length;
  const cy = positioned.reduce((sum, node) => sum + node.y, 0) / positioned.length;
  const cos = Math.cos(angle), sin = Math.sin(angle);
  for (const node of positioned) {
    const x = node.x - cx, y = node.y - cy;
    node.x = cx + x * cos - y * sin;
    node.y = cy + x * sin + y * cos;
    if (Number.isFinite(node.fx)) node.fx = node.x;
    if (Number.isFinite(node.fy)) node.fy = node.y;
    const vx = node.vx ?? 0, vy = node.vy ?? 0;
    node.vx = vx * cos - vy * sin;
    node.vy = vx * sin + vy * cos;
  }
}
