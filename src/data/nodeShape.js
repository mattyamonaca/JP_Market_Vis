// 全体マップのノード（円＋リングのスプライト。Issue #28）の当たり判定。
// テクスチャは 128px 正方形の中心に、外縁がちょうど正方形の縁（UV 半径 0.5）に接する円を描く。
// スプライトの既定 raycast は正方形全体で交差判定するため、UV 座標が円の内側にある交点だけを採用する。
export const TEXTURE_SIZE = 128;
export const RING_WIDTH = { normal: 5, hover: 9 };
// 円の外縁（リングの外側）の UV 半径。描画された円と選択領域を一致させる
export const CIRCLE_UV_RADIUS = 0.5;

export function isInsideNodeCircle(uv, radius = CIRCLE_UV_RADIUS) {
  if (!uv || !Number.isFinite(uv.x) || !Number.isFinite(uv.y)) return false;
  return Math.hypot(uv.x - 0.5, uv.y - 0.5) <= radius;
}

// raycast の交点配列から、円の外側（透明な四隅）の交点を取り除く。start 以降がこのスプライトの交点
export function keepCircleHits(intersects, start) {
  for (let i = intersects.length - 1; i >= start; i -= 1) {
    if (!isInsideNodeCircle(intersects[i].uv)) intersects.splice(i, 1);
  }
  return intersects;
}
