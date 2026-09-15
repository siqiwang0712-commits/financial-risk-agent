import assert from 'node:assert/strict';
import test from 'node:test';
import {isAssessmentPayload,isFiniteNumber,isPilotPayload,isRecord} from '../lib/guards.mjs';

// The guards are the only thing standing between a wrong-shaped 200 response and
// the renderer. Each case below is a shape the upstream can actually produce:
// `{}` from a swallowed body, an HTML error page parsed as JSON, and a partial
// payload whose arrays are missing.

test('isRecord accepts objects only',()=>{
  assert.equal(isRecord({}),true);
  assert.equal(isRecord([]),false);
  assert.equal(isRecord(null),false);
  assert.equal(isRecord('{}'),false);
  assert.equal(isRecord(7),false);
});

test('isFiniteNumber rejects NaN and Infinity',()=>{
  assert.equal(isFiniteNumber(0),true);
  assert.equal(isFiniteNumber(-1.5),true);
  assert.equal(isFiniteNumber(Number.NaN),false);
  assert.equal(isFiniteNumber(Number.POSITIVE_INFINITY),false);
  assert.equal(isFiniteNumber('1'),false);
});

test('pilot payload requires rows and annotation_status',()=>{
  assert.equal(isPilotPayload({snapshot:'v0.3.0',annotation_status:'pilot',rows:[]}),true);
  // `annotation_status` is rendered verbatim by PilotTable; without it the meta
  // line printed the literal string "annotation: undefined".
  assert.equal(isPilotPayload({snapshot:'v0.3.0',rows:[]}),false);
  assert.equal(isPilotPayload({snapshot:'v0.3.0',annotation_status:'pilot'}),false);
  assert.equal(isPilotPayload({}),false);
  assert.equal(isPilotPayload(null),false);
  const goodRow={entity:'Northstar',decision:'FLAG',score:70,coverage:0.8,reliability:'UNCALIBRATED',filing:'n-2025'};
  assert.equal(isPilotPayload({snapshot:'v',annotation_status:'pilot',rows:[goodRow]}),true);
  assert.equal(isPilotPayload({snapshot:'v',annotation_status:'pilot',rows:[{...goodRow,entity:{}}]}),false);
  assert.equal(isPilotPayload({snapshot:'v',annotation_status:'pilot',rows:[{...goodRow,score:Number.NaN}]}),false);
});

test('assessment payload rejects bodies that would crash a panel',()=>{
  const good={
    company:'Northstar',reporting_period:'2025',overall_score:70,
    risk_level:'Critical',final_decision:'FLAG',reliability_status:'UNCALIBRATED',
    evidence_quality:0.8,evidence_coverage:0.7,dimensions:{},
    confidence_components:{core_data_completeness:0.9},missing_information:[],
  };
  assert.equal(isAssessmentPayload(good),true);
  // `{}` - the body a swallowed error produces.
  assert.equal(isAssessmentPayload({}),false);
  // An HTML error page that parsed as JSON-ish text.
  assert.equal(isAssessmentPayload('<html></html>'),false);
  assert.equal(isAssessmentPayload(null),false);
  // Each container the panels iterate over is load-bearing.
  assert.equal(isAssessmentPayload({...good,dimensions:null}),false);
  assert.equal(isAssessmentPayload({...good,dimensions:[]}),false);
  assert.equal(isAssessmentPayload({...good,confidence_components:null}),false);
  assert.equal(isAssessmentPayload({...good,missing_information:null}),false);
  assert.equal(isAssessmentPayload({...good,company:undefined}),false);
  assert.equal(isAssessmentPayload({...good,risk_level:undefined}),false);
  assert.equal(isAssessmentPayload({...good,reporting_period:{}}),false);
  assert.equal(isAssessmentPayload({...good,evidence_coverage:Number.NaN}),false);
  assert.equal(isAssessmentPayload({...good,confidence_components:{bad:'0.5'}}),false);
  assert.equal(isAssessmentPayload({...good,missing_information:[{}]}),false);
  assert.equal(isAssessmentPayload({...good,dimensions:{liquidity:null}}),false);
});
