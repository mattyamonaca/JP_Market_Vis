// 全体マップのノード（白い円に業種色の縁、円の中に企業名）の大きさとラベル表示の規則。
// 描画（nodeCanvasObject）と当たり判定（nodePointerAreaPaint）が同じ半径を使うので、見た目とホバー・クリックの対象が一致する。
export const NODE_MIN_RADIUS = 4; // グラフ座標単位。全体表示（倍率 0.3 程度）でも関係数 1〜2 の企業が点として見える大きさ
export const HOVER_SCALE = 1.2; // ホバー中の拡大率
export const LABEL_MIN_DEGREE = 60; // 主要ハブはズームに関係なく常時ラベル

// 半径は関係数の平方根に比例（面積が関係数に比例する）
export function nodeRadius(degree) {
  return Math.max(NODE_MIN_RADIUS, Math.sqrt(Math.max(0, degree || 0)) * 2.8);
}

// 縁の太さ（グラフ座標単位）。円の内側に描くので、縁の外側＝半径
export function ringWidth(radius, hover = false) {
  return hover ? Math.min(4, Math.max(1.2, radius * 0.25)) : Math.min(2.4, Math.max(0.6, radius * 0.14));
}

// 円の中に書く企業名の配置。文字の大きさは円の画面上の半径に応じて 11〜20px（fontMax）。
// 1) 1 行で fontMax の 75% 以上の大きさで入ればそのまま、2) 入らなければ語の境界で 2 行に分けて収まる最大の文字で、
// 3) それでも駄目なら 1 行で最小まで縮めて試し、入らなければ null（drawLabels が円の上に出す）。measure12 は 12px での文字幅（画面 px）
export const INSIDE_FONT = { min: 11, max: 20, fill: 0.86 };
export function insideLayout(screenRadius, name, measure12) {
  const fontMax = Math.min(INSIDE_FONT.max, Math.max(INSIDE_FONT.min, screenRadius * 0.38));
  const diameter = screenRadius * 2 * INSIDE_FONT.fill;
  const width = (text, font) => measure12(text) * font / 12;
  const single = (minFont) => { for (let font = fontMax; font >= minFont; font -= 1) if (width(name, font) <= diameter) return { font, lines: [name] }; return null; };
  const one = single(Math.max(INSIDE_FONT.min, Math.ceil(fontMax * 0.75)));
  if (one) return one;
  if (name.length >= 4) {
    for (const lines of splitCandidates(name)) {
      for (let font = fontMax; font >= INSIDE_FONT.min; font -= 1) {
        // 2 行目は中心から font×0.65 ずれるので、その高さでの弦の長さに収める
        const chord = 2 * Math.sqrt(Math.max(0, screenRadius ** 2 - (font * 0.65) ** 2)) * INSIDE_FONT.fill;
        if (font * 2.4 <= diameter && lines.every((line) => width(line, font) <= chord)) return { font, lines };
      }
    }
  }
  return single(INSIDE_FONT.min);
}
// 企業名を 2 行に分ける候補（中央に近い順）: 「・」や空白の後ろ、よく使われる語の前後。最後に中央での分割
const SEPARATORS = '・ 　＆&';
const WORDS = ['ホールディングス', 'ホールディング', 'グループ', 'フィナンシャル', 'インターネット', 'テクノロジーズ', 'テクノロジー', 'ソリューションズ', 'ソリューション',
  'エンジニアリング', 'システムズ', 'システム', 'サービス', 'マネジメント', 'ネットワーク', 'コーポレーション', 'コミュニケーションズ', 'エレクトロニクス',
  'インダストリーズ', 'インダストリー', 'パートナーズ', 'キャピタル', 'リアルエステート', 'ロジスティクス', 'ファーマ', 'ジャパン', 'ハウス', 'リース',
  '不動産', '工業', '製作所', '電機', '電気', '銀行', '証券', '商事', '物産', '産業', '製薬', '化学', '建設', '運輸', '鉄道', '自動車', '日本'];
export function splitCandidates(name) {
  const mid = name.length / 2, cuts = new Set();
  [...name].forEach((c, i) => { if (SEPARATORS.includes(c)) cuts.add(i + 1); });
  for (const word of WORDS) for (let i = name.indexOf(word); i >= 0; i = name.indexOf(word, i + 1)) { cuts.add(i); cuts.add(i + word.length); }
  const valid = [...cuts].filter((i) => i > 0 && i < name.length).sort((a, b) => Math.abs(a - mid) - Math.abs(b - mid));
  const middle = Math.ceil(mid);
  if (!valid.includes(middle)) valid.push(middle);
  return valid.map((i) => [name.slice(0, i).trim(), name.slice(i).trim()]).filter(([a, b]) => a && b);
}

// 円の上にラベルを描く条件（円の中に名前が入らない場合）: ホバー中と主要ハブは常時。拡大するほど関係数の小さい企業にも表示する
export function showsLabel(degree, zoom, hovered = false) {
  if (hovered || degree >= LABEL_MIN_DEGREE) return true;
  if (zoom >= 8) return true;
  if (zoom >= 4) return degree >= 3;
  if (zoom >= 2) return degree >= 8;
  if (zoom >= 1) return degree >= 30;
  return false;
}
