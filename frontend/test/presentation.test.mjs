import assert from 'node:assert/strict';
import test from 'node:test';
import {displayReliability,displayScore,evidenceLocator,normalizeDecision,safeApiJson} from '../lib/presentation.mjs';

test('uncalibrated reliability is never rendered as probability',()=>assert.match(displayReliability('UNCALIBRATED',0.9),/not a probability/));
test('decision states and missing scores are explicit',()=>{for(const state of ['ABSTAIN','REVIEW','PASS','FLAG'])assert.equal(normalizeDecision(state),state);assert.equal(displayScore(null),'N/A')});
test('evidence association retains source document and page',()=>assert.equal(evidenceLocator({source:'SEC',document:'10-K',page:42}),'SEC · 10-K · page 42'));
test('API failures expose safe server detail',async()=>{const response=new Response(JSON.stringify({detail:'safe error'}),{status:422});await assert.rejects(()=>safeApiJson(response),/safe error/)});
