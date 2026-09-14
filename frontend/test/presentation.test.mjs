import assert from 'node:assert/strict';
import test from 'node:test';
import {displayRatio,displayReliability,displayScore,evidenceLocator,normalizeDecision,safeApiJson} from '../lib/presentation.mjs';

test('uncalibrated reliability is never rendered as probability',()=>assert.match(displayReliability('UNCALIBRATED',0.9),/not a probability/));
test('decision states and missing scores are explicit',()=>{for(const state of ['ABSTAIN','REVIEW','PASS','FLAG'])assert.equal(normalizeDecision(state),state);assert.equal(displayScore(null),'N/A')});
test('evidence association retains source document and page',()=>assert.equal(evidenceLocator({source:'SEC',document:'10-K',page:42}),'SEC · 10-K · page 42'));

// --- regression: the risk index must not print a float artefact -------------
// `String(score)` surfaced binary noise ("42.699999999999996") in the headline
// while the coverage figure beside it was formatted with `toFixed`.
test('displayScore rounds and degrades instead of printing noise',()=>{
  assert.equal(displayScore(42.699999999999996),'42.7');
  assert.equal(displayScore(95),'95');
  assert.equal(displayScore(0),'0');
  assert.equal(displayScore(24.0),'24');
  assert.equal(displayScore(undefined),'N/A');
  assert.equal(displayScore(Number.NaN),'N/A');
  assert.equal(displayScore('42.7'),'N/A');
});

test('displayRatio formats to fixed decimals or N/A',()=>{
  assert.equal(displayRatio(0.58333),'0.583');
  assert.equal(displayRatio(0.5,2),'0.50');
  assert.equal(displayRatio(0),'0.000');
  assert.equal(displayRatio(null),'N/A');
  assert.equal(displayRatio(undefined),'N/A');
  assert.equal(displayRatio(Number.NaN),'N/A');
});

// --- regression: page 0 is the backend's "not recorded" sentinel ------------
// `FinancialValue.page` is an `int` defaulting to 0 and PDF pages are 1-based, so
// 0 means "no page". The old truthiness test reached that conclusion by accident.
test('evidenceLocator treats page 0 and null as unrecorded, not as a page',()=>{
  assert.equal(evidenceLocator({source:'SEC',document:'10-K',page:0}),'SEC · 10-K');
  assert.equal(evidenceLocator({source:'SEC',document:'10-K',page:null}),'SEC · 10-K');
  assert.equal(evidenceLocator({document:'10-K'}),'10-K');
  assert.equal(evidenceLocator({document:'10-K',page:1}),'10-K · page 1');
});

test('evidenceLocator survives a partially populated record',()=>{
  assert.equal(evidenceLocator(null),'');
  assert.equal(evidenceLocator(undefined),'');
  assert.equal(evidenceLocator({}),'');
  assert.equal(evidenceLocator({source:null,document:null,page:null}),'');
});

test('API failures expose safe server detail',async()=>{const response=new Response(JSON.stringify({detail:'safe error'}),{status:422});await assert.rejects(()=>safeApiJson(response),/safe error/)});
