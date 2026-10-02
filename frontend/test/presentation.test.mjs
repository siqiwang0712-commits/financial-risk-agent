import assert from 'node:assert/strict';
import test from 'node:test';
import {authorizedDecision,displayReliability,displayScore,evidenceLocator,normalizeDecision,safeApiJson} from '../lib/presentation.mjs';

test('uncalibrated reliability is never rendered as probability',()=>assert.match(displayReliability('UNCALIBRATED',0.9),/not a probability/));
test('decision states and missing scores are explicit',()=>{for(const state of ['ABSTAIN','REVIEW','PASS','FLAG'])assert.equal(normalizeDecision(state),state);assert.equal(displayScore(null),'N/A')});
test('evidence association retains source document and page',()=>assert.equal(evidenceLocator({source:'SEC',document:'10-K',page:42}),'SEC · 10-K · page 42'));
test('API failures expose safe server detail',async()=>{const response=new Response(JSON.stringify({detail:'safe error'}),{status:422});await assert.rejects(()=>safeApiJson(response),/safe error/)});
test('a final decision is displayed only when Assurance and Certificate agree',()=>{
  const assurance={proposed_decision:'FLAG',final_decision:'REVIEW',policy_hash:'policy'};
  const certificate={proposed_decision:'FLAG',final_decision:'REVIEW',policy_hash:'policy',certificate_hash:'cert'};
  const payload={proposed_decision:'FLAG',final_decision:'REVIEW',assurance,decision_certificate:certificate,agent:null};
  assert.equal(authorizedDecision(payload),'REVIEW');
  assert.equal(authorizedDecision({...payload,final_decision:'FLAG'}),'UNAUTHORIZED');
  assert.equal(authorizedDecision({...payload,decision_certificate:{...certificate,policy_hash:'forged'}}),'UNAUTHORIZED');
  assert.equal(authorizedDecision({...payload,decision_certificate:null}),'UNAUTHORIZED');
  assert.equal(authorizedDecision({...payload,agent:{decision_certificate:{...certificate,certificate_hash:'other'}}}),'UNAUTHORIZED');
});
