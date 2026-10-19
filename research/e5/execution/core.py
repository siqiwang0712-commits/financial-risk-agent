"""Pre-outcome boundaries. Engineering machinery does not establish qualification."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class GateError(ValueError):
    """A scientific or provenance gate failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def timestamp(value: str) -> datetime:
    require(isinstance(value, str), 'timestamp must be text')
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GateError('invalid timestamp') from exc
    require(result.tzinfo is not None and result.utcoffset().total_seconds() == 0,
            'explicit UTC timestamp required')
    return result


def hash_string(value: Any) -> None:
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None,
            'SHA256 required')


def read_json(path: Path) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON field')
            result[key] = value
        return result
    def invalid(value):
        raise GateError('nonfinite JSON: ' + value)
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=invalid)


def freeze_json(path: Path, value: Any) -> str:
    """Atomic create-only publication; an identical rerun verifies without writes."""
    raw = canonical(value) + b'\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.is_symlink(), 'symlink output forbidden')
    if path.exists():
        require(path.read_bytes() == raw, 'frozen artifact overwrite forbidden')
        return file_hash(path)
    fd, temporary = tempfile.mkstemp(prefix='.e5-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)  # Atomic no-replace even across concurrent writers.
        except FileExistsError:
            require(path.read_bytes() == raw, 'concurrent frozen artifact mismatch')
    finally:
        os.unlink(temporary)
    return file_hash(path)


def verify_files(root: Path, manifest: dict[str, str]) -> None:
    require(bool(manifest), 'empty identity manifest')
    for name, expected in manifest.items():
        path = root / name
        require(path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(),
                'identity path escape')
        hash_string(expected)
        require(path.is_file() and file_hash(path) == expected, 'identity drift: ' + name)


FEATURE_FIELDS = {'case_id', 'cik', 'accession', 'filing_timestamp', 'prediction_cutoff',
                  'schema_hash', 'extraction_code_hash', 'preprocessing_hash',
                  'reference_distribution_hash', 'sources', 'features'}
SOURCE_FIELDS = {'sha256', 'available_at', 'filing_timestamp', 'accession', 'cik', 'role'}


def validate_features(packet: dict, *, schema_hash: str, code_hash: str) -> str:
    require(set(packet) == FEATURE_FIELDS, 'feature schema fields differ')
    require(isinstance(packet['case_id'], str) and bool(packet['case_id']), 'case ID required')
    require(re.fullmatch(r'\d{10}', packet['cik']) is not None, 'normalized CIK required')
    require(re.fullmatch(r'\d{10}-\d{2}-\d{6}', packet['accession']) is not None,
            'SEC accession required')
    cutoff = timestamp(packet['prediction_cutoff'])
    require(timestamp(packet['filing_timestamp']) <= cutoff, 'future index filing')
    for key in ('schema_hash', 'extraction_code_hash', 'preprocessing_hash', 'reference_distribution_hash'):
        hash_string(packet[key])
    require(packet['schema_hash'] == schema_hash, 'feature schema drift')
    require(packet['extraction_code_hash'] == code_hash, 'extraction code drift')
    require(isinstance(packet['sources'], list) and bool(packet['sources']), 'source provenance required')
    for source in packet['sources']:
        require(set(source) == SOURCE_FIELDS, 'source schema differs')
        require(source['role'] == 'INDEX_FILING', 'only index-accession facts are admitted by this schema')
        require(source['cik'] == packet['cik'], 'cross-CIK source substitution')
        require(source['accession'] == packet['accession'], 'cross-accession source substitution')
        require(timestamp(source['filing_timestamp']) == timestamp(packet['filing_timestamp']),
                'source index filing timestamp mismatch')
        hash_string(source['sha256'])
        require(timestamp(source['available_at']) <= cutoff, 'post-cutoff source availability')
        require(timestamp(source['filing_timestamp']) <= cutoff, 'post-cutoff source filing')
        require(re.fullmatch(r'\d{10}-\d{2}-\d{6}', source['accession']) is not None,
                'source accession required')
    require(isinstance(packet['features'], dict) and bool(packet['features']), 'features required')
    for value in packet['features'].values():
        require(value is None or type(value) in (int, float) and math.isfinite(value),
                'numeric feature or explicit missing value required')
    return digest(packet)


PROPOSAL_FIELDS = {'case_id', 'cik', 'accession', 'prediction_cutoff', 'input_hash',
                   'feature_schema_hash', 'producer_identity', 'generation_timestamp',
                   'raw_structured_output', 'normalized_risk_score', 'proposed_decision'}
PRODUCER_FIELDS = {'version', 'code_hash', 'model', 'prompt_hash', 'tool_definition_hash',
                   'generation_parameters', 'score_semantics'}


def validate_proposal(packet: dict, *, producer_hash: str) -> str:
    require(set(packet) == PROPOSAL_FIELDS | {'proposal_hash'}, 'proposal fields differ')
    body = {key: value for key, value in packet.items() if key != 'proposal_hash'}
    require(digest(body) == packet['proposal_hash'], 'mutated ProposalPacket')
    identity = packet['producer_identity']
    require(set(identity) == PRODUCER_FIELDS and digest(identity) == producer_hash,
            'producer/model/prompt identity mismatch')
    hash_string(identity['code_hash'])
    require(bool(identity['model']) and bool(identity['version']), 'producer identity required')
    for key in ('input_hash', 'feature_schema_hash'):
        hash_string(packet[key])
    timestamp(packet['prediction_cutoff'])
    timestamp(packet['generation_timestamp'])
    score = packet['normalized_risk_score']
    require(score is None or type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1,
            'normalized score required; not a probability without calibration')
    require(packet['proposed_decision'] in {'PASS', 'FLAG', 'REVIEW', 'ABSTAIN'}, 'bad proposal decision')
    return packet['proposal_hash']


class FrozenProposalProducer:
    """Execute an explicitly supplied producer once; never supply a mock fallback.

    Qualification of the callable, score normalization and source semantics is a
    separate mandatory gate. This wrapper is not the actual qualified Agent.
    """
    def __init__(self, identity: dict, produce: Callable[[dict], dict]):
        require(set(identity) == PRODUCER_FIELDS, 'producer identity fields differ')
        self.identity_bytes = canonical(identity)
        self.produce = produce

    def run(self, feature: dict, output: Path) -> dict:
        identity = json.loads(self.identity_bytes)
        producer_hash = digest(identity)
        if output.exists():
            packet = read_json(output)
            validate_proposal(packet, producer_hash=producer_hash)
            require(packet['input_hash'] == digest(feature), 'proposal belongs to different input')
            return packet
        validate_features(feature, schema_hash=feature['schema_hash'], code_hash=feature['extraction_code_hash'])
        output.parent.mkdir(parents=True, exist_ok=True)
        lock = output.with_suffix(output.suffix + '.generation-lock')
        try:
            with lock.open('x') as stream:
                stream.write('Generation started. Incomplete execution needs explicit recovery; never silently regenerate.\n')
        except FileExistsError as exc:
            raise GateError('proposal generation already started; explicit recovery required') from exc
        result = self.produce(json.loads(canonical(feature)))
        require(set(result) == {'raw_structured_output', 'normalized_risk_score', 'proposed_decision'},
                'producer output schema differs')
        packet = {key: feature[key] for key in ('case_id', 'cik', 'accession', 'prediction_cutoff')}
        packet.update(input_hash=digest(feature), feature_schema_hash=feature['schema_hash'],
                      producer_identity=identity, generation_timestamp=utcnow(), **result)
        packet['proposal_hash'] = digest(packet)
        validate_proposal(packet, producer_hash=producer_hash)
        freeze_json(output, packet)
        lock.unlink()
        return packet


def shared_proposals(proposals: dict[str, dict], producer_hash: str) -> str:
    require(set(proposals) == {'S2', 'S3', 'S4'}, 'all proposal consumers required')
    hashes = [validate_proposal(p, producer_hash=producer_hash) for p in proposals.values()]
    require(len(set(hashes)) == 1, 'S2/S3/S4 regenerated or mismatched proposal')
    return hashes[0]


def verified_label(row: dict) -> int | None:
    require(set(row) >= {'status', 'label'}, 'explicit outcome status and label required')
    if row['status'] == 'VERIFIED':
        require(type(row['label']) is int and row['label'] in (0, 1), 'VERIFIED binary label required')
        return row['label']
    require(row['status'] in {'REQUIRES_REVIEW', 'INSUFFICIENT_DATA', 'MISSING'}, 'unknown outcome status')
    require(row['label'] is None, 'nonverified outcome cannot become negative')
    return None


def outcome_barrier(root: Path, attestation: dict, *, outcome_paths: list[Path],
                    prediction_stage: bool) -> None:
    """Path/identity gate, not a claim of OS-level isolation or reviewer blinding."""
    if prediction_stage:
        require(not any(p.exists() for p in outcome_paths), 'outcome directory mounted too early')
        return
    required = {'mandate', 'e5p_core', 'e5r_protocol', 'utility', 'power', 'inference',
                'type1', 'S0', 'S1', 'producer', 'calibration', 'study_policy', 'S2',
                'S3', 'S4', 'endpoint', 'cohort', 'historical_overlap', 'feature_schema',
                'features', 'source_timestamps', 'proposals', 'proposal_equality',
                'certificates', 'predictions', 'prediction_audit', 'operational_isolation'}
    require(set(attestation) == {'gates', 'files', 'prediction_frozen_at'}, 'attestation schema differs')
    require(set(attestation['gates']) == required, 'incomplete pre-outcome barrier')
    require(all(value is True for value in attestation['gates'].values()), 'pre-outcome gate unsatisfied')
    timestamp(attestation['prediction_frozen_at'])
    require(timestamp(attestation['prediction_frozen_at']) <= datetime.now(UTC),
            'prediction freeze is in the future')
    verify_files(root, attestation['files'])


def exact_previous_270(path: Path) -> set[str]:
    require(file_hash(path) == 'd73b371ccb026f556387cf6ff8ba204a4fde0664dcd780f099f12aa005e36603',
            'C01 exact artifact hash mismatch; approximation cannot close C01')
    rows = read_json(path)
    require(isinstance(rows, list) and len(rows) == 270, 'C01 cardinality')
    ciks = {str(row['cik']).zfill(10) if isinstance(row, dict) else str(row).zfill(10) for row in rows}
    require(len(ciks) == 270, 'C01 duplicate companies')
    return ciks


def disjoint(ciks: list[str], historical: set[str]) -> None:
    require(len(ciks) == len(set(ciks)), 'one company per study required')
    require(not set(ciks) & historical, 'historical company overlap')


def verify_certificate_binding(certificate: dict, *, proposal_hash: str, policy) -> None:
    from finrisk.assurance.certificate import verify_decision_certificate
    require(certificate.get('policy_hash') == policy.policy_hash, 'certificate policy mismatch')
    require(certificate.get('component_versions', {}).get('proposal_hash') == proposal_hash,
            'certificate belongs to another proposal')
    require(verify_decision_certificate(certificate, policy), 'certificate verification failed')
