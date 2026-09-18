// 全体マップのノード（2D の塗りの円＋細いリング）の大きさとラベル表示の規則。
// 描画（nodeCanvasObject）と当たり判定（nodePointerAreaPaint）が同じ半径を使うので、見た目とホバー・クリックの対象が一致する。
export const NODE_MIN_RADIUS = 3.5; // グラフ座標単位。全体表示（倍率 0.3 程度）でも関係数 1〜2 の企業が点として見える大きさ
export const HOVER_SCALE = 1.2; // ホバー中の拡大率
export const LABEL_MIN_DEGREE = 60; // 主要ハブはズームに関係なく常時ラベル

// 半径は関係数の平方根に比例（面積が関係数に比例する）
export function nodeRadius(degree) {
  return Math.max(NODE_MIN_RADIUS, Math.sqrt(Math.max(0, degree || 0)) * 2.2);
}

// リングの太さ（グラフ座標単位）。円の内側に描くので、リングの外縁＝半径
export function ringWidth(radius, hover = false) {
  return hover ? Math.min(3.2, Math.max(1, radius * 0.22)) : Math.min(2.2, Math.max(0.5, radius * 0.12));
}

// 同色を k（0〜1）だけ暗くした色（リング用）
export function shade(hex, k) {
  return '#' + [1, 3, 5].map((i) => Math.round(parseInt(hex.slice(i, i + 2), 16) * (1 - k)).toString(16).padStart(2, '0')).join('');
}

// ラベルを描く条件: ホバー中と主要ハブは常時。拡大するほど関係数の小さい企業にも表示する
export function showsLabel(degree, zoom, hovered = false) {
  if (hovered || degree >= LABEL_MIN_DEGREE) return true;
  if (zoom >= 8) return true;
  if (zoom >= 4) return degree >= 3;
  if (zoom >= 2) return degree >= 8;
  if (zoom >= 1) return degree >= 30;
  return false;
}
