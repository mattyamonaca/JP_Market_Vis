import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import CompanySources from '../src/components/CompanySources.jsx';

test('source dates are separate from collection dates and undated pages stay undated', () => {
 const html=renderToStaticMarkup(React.createElement(CompanySources,{collectedOn:'2026-09-21',sources:{
  name:{source_url:'https://example.com/company'},
  industry_33:{source_url:'https://example.com/report.pdf',document_date:'2026-07-01',retrieved:'2026-09-20',verification:'machine_extracted'},
 }}));
 assert.match(html,/2026-07-01/);assert.match(html,/2026-09-20/);assert.match(html,/2026-09-21/);
 assert.match(html,/記載なし・不明/);assert.match(html,/出典未確認/);assert.match(html,/自動抽出/);
});
test('unsafe source URLs never become clickable links', () => {
 const html=renderToStaticMarkup(React.createElement(CompanySources,{sources:{name:{source_url:'javascript:alert(1)'}}}));
 assert.ok(!html.includes('href='));assert.ok(!html.includes('javascript:'));
});
