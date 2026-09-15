import assert from 'node:assert/strict';
import test from 'node:test';
import {
  ALLOWED_METHODS,
  FORWARDED_REQUEST_HEADERS,
  FORWARDED_RESPONSE_HEADERS,
  isValidSegment,
  selectRequestHeaders,
  selectResponseHeaders,
  upstreamTimeoutMs,
  ANALYSIS_UPSTREAM_TIMEOUT_MS,
  DEFAULT_UPSTREAM_TIMEOUT_MS,
} from '../lib/proxy.mjs';

// --- P0 regression: the error branch must not relay content-length ----------
// The upstream answered 401 with an 84-byte JSON body. The proxy replaced the
// body with a 27-byte envelope but forwarded `content-length: 84`, so the client
// aborted with "end of response with 57 bytes missing" and the 401 was reported
// to the user as "the upstream is unavailable".

test('a replaced body never carries the upstream content-length',()=>{
  const upstream = new Headers({'content-type':'application/json','content-length':'84'});
  const selected = selectResponseHeaders(upstream,{bodyIsUnchanged:false});
  assert.equal(selected['content-length'],undefined);
  assert.equal(selected['content-type'],'application/json');
});

test('an unchanged body keeps the upstream content-length',()=>{
  const upstream = new Headers({'content-type':'application/json','content-length':'84'});
  const selected = selectResponseHeaders(upstream,{bodyIsUnchanged:true});
  assert.equal(selected['content-length'],'84');
});

test('content-length is not in the static allowlist',()=>{
  // It is added conditionally, never copied blindly.
  assert.equal(FORWARDED_RESPONSE_HEADERS.includes('content-length'),false);
});

test('the error envelope is self-consistent when built from the selection',()=>{
  const upstream = new Headers({'content-type':'application/json','content-length':'84'});
  const headers = new Headers(selectResponseHeaders(upstream,{bodyIsUnchanged:false}));
  const envelope = JSON.stringify({detail:'upstream error'});
  // The declared length, if the framework sets one, must describe the body we send.
  headers.set('content-length',String(Buffer.byteLength(envelope)));
  assert.equal(Number(headers.get('content-length')),27);
});

// --- credential headers are never forwarded ---------------------------------
test('request headers are allowlisted',()=>{
  const incoming = new Headers({
    'content-type':'application/json',
    'x-api-key':'tenant-key',
    cookie:'session=secret',
    authorization:'Bearer secret',
    'x-forwarded-for':'10.0.0.1',
  });
  const selected = selectRequestHeaders(incoming);
  assert.deepEqual(Object.keys(selected).sort(),['content-type','x-api-key']);
  assert.equal(selected.cookie,undefined);
  assert.equal(selected.authorization,undefined);
});

test('a missing or empty header is omitted rather than forwarded blank',()=>{
  assert.deepEqual(selectRequestHeaders(new Headers()),{});
  assert.deepEqual(selectResponseHeaders(null,{bodyIsUnchanged:true}),{});
  assert.deepEqual(selectRequestHeaders(new Headers({'x-api-key':''})),{});
});

// --- path segments ---------------------------------------------------------
test('only methods the workbench performs are proxied',()=>{
  assert.deepEqual([...ALLOWED_METHODS],['GET','POST']);
  assert.equal(ALLOWED_METHODS.includes('DELETE'),false);
  assert.equal(ALLOWED_METHODS.includes('PUT'),false);
});

test('traversal and encoded separators are rejected',()=>{
  for (const segment of ['..','.', '', '%2e%2e', 'a/b', 'a\\b', 'a%2fb', 'a b', 'a?b']) {
    assert.equal(isValidSegment(segment),false,`${JSON.stringify(segment)} must be rejected`);
  }
  for (const segment of ['public-pilot','documents','assess','a_b','a.b','a~b','v1']) {
    assert.equal(isValidSegment(segment),true,`${JSON.stringify(segment)} must be accepted`);
  }
  assert.equal(isValidSegment(undefined),false);
  assert.equal(isValidSegment(null),false);
  assert.equal(isValidSegment(7),false);
});

test('the request allowlist does not grow by accident',()=>{
  assert.deepEqual([...FORWARDED_REQUEST_HEADERS],['content-type','accept','x-api-key','x-correlation-id']);
});

test('document analysis receives the long upstream timeout',()=>{
  assert.equal(upstreamTimeoutMs(['documents','analyze']),ANALYSIS_UPSTREAM_TIMEOUT_MS);
  assert.ok(ANALYSIS_UPSTREAM_TIMEOUT_MS>120_000);
  assert.equal(upstreamTimeoutMs(['public-pilot']),DEFAULT_UPSTREAM_TIMEOUT_MS);
  assert.equal(upstreamTimeoutMs(null),DEFAULT_UPSTREAM_TIMEOUT_MS);
});
