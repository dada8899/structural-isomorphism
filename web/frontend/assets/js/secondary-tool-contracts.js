/** Strict client-side contracts for Stress, Diagnose, Apply and Struct Lint. */
(function (root) {
  'use strict';

  var CONTRACT_VERSION = 'secondary-tools-v2';
  var REQUEST_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{11,63}$/;
  var CANDIDATE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
  var CLAIM_ID = /^lint-[0-9a-f]{16}$/;

  function plain(value) {
    if (!value || Object.prototype.toString.call(value) !== '[object Object]') return false;
    var proto = Object.getPrototypeOf(value);
    return proto === Object.prototype || proto === null;
  }

  function exact(value, keys) {
    if (!plain(value)) return false;
    var actual = Object.keys(value).sort();
    var expected = keys.slice().sort();
    return actual.length === expected.length && actual.every(function (key, i) {
      return key === expected[i];
    });
  }

  function text(value, min, max) {
    return typeof value === 'string' && value.trim().length >= min && value.length <= max;
  }

  function nullableText(value, max) {
    return value === null || text(value, 1, max);
  }

  function normalizeSource(value) {
    return String(value || '').normalize('NFKC').replace(/\s+/g, ' ').trim();
  }

  function createRequestId(prefix) {
    var head = String(prefix || 'secondary').replace(/[^A-Za-z0-9_-]/g, '').slice(0, 16) || 'secondary';
    var random = '';
    try {
      if (root.crypto && typeof root.crypto.randomUUID === 'function') {
        random = root.crypto.randomUUID().replace(/-/g, '');
      }
    } catch (error) { random = ''; }
    if (!random) {
      random = Date.now().toString(36) + Math.random().toString(36).slice(2, 14);
    }
    return (head + '-' + random).slice(0, 64);
  }

  function validateEvidence(value, expectedLabel, sourceKind) {
    if (!exact(value, [
      'schema_version', 'evidence_level', 'candidate', 'source', 'result',
      'independence', 'counterexamples', 'ledger'
    ])) return false;
    if (value.schema_version !== 'evidence-envelope-v1' || value.evidence_level !== 'candidate') return false;
    if (!exact(value.candidate, ['status', 'kind', 'label', 'score'])) return false;
    if (value.candidate.status !== 'recorded' || !text(value.candidate.kind, 1, 100)) return false;
    if (expectedLabel !== undefined && value.candidate.label !== expectedLabel) return false;
    if (!nullableText(value.candidate.label, 1000) || value.candidate.score !== null) return false;

    if (!exact(value.source, ['status', 'kind', 'label', 'url', 'source_review'])) return false;
    if (['recorded', 'not_recorded'].indexOf(value.source.status) === -1) return false;
    if (['internal_kb', 'not_recorded'].indexOf(value.source.kind) === -1) return false;
    if (sourceKind && value.source.kind !== sourceKind) return false;
    if (!nullableText(value.source.label, 1000) || value.source.url !== null || value.source.source_review !== null) return false;

    if (!exact(value.result, ['status', 'provenance', 'verdict', 'summary'])) return false;
    if (['recorded', 'not_recorded'].indexOf(value.result.status) === -1) return false;
    if (['NOT_TESTED', 'INTERNAL_AI_SCREEN'].indexOf(value.result.provenance) === -1) return false;
    if (['NOT_TESTED', 'INCONCLUSIVE'].indexOf(value.result.verdict) === -1) return false;
    if (!nullableText(value.result.summary, 1000)) return false;
    if (sourceKind === 'internal_kb') {
      if (value.source.status !== 'recorded' || value.source.label !== 'Structural KB record' ||
          value.result.status !== 'not_recorded' || value.result.provenance !== 'NOT_TESTED' ||
          value.result.verdict !== 'NOT_TESTED') return false;
    } else if (value.source.status !== 'not_recorded' || value.source.kind !== 'not_recorded' ||
               value.source.label !== null || value.result.status !== 'recorded' ||
               value.result.provenance !== 'INTERNAL_AI_SCREEN' ||
               value.result.verdict !== 'INCONCLUSIVE') return false;

    if (!exact(value.independence, ['status', 'kind', 'summary'])) return false;
    if (value.independence.status !== 'not_recorded' || value.independence.kind !== 'not_recorded') return false;
    if (!nullableText(value.independence.summary, 1000)) return false;

    if (!exact(value.counterexamples, ['status', 'summary'])) return false;
    if (['not_recorded', 'gap_recorded'].indexOf(value.counterexamples.status) === -1) return false;
    if (!nullableText(value.counterexamples.summary, 1000)) return false;

    if (!exact(value.ledger, ['status', 'claim_id', 'version', 'recorded_at', 'artifact_sha256', 'url'])) return false;
    if (value.ledger.status !== 'not_recorded') return false;
    return ['claim_id', 'version', 'recorded_at', 'artifact_sha256', 'url'].every(function (key) {
      return value.ledger[key] === null;
    });
  }

  function validateCandidateReference(value) {
    if (value === null) return true;
    if (!exact(value, [
      'id', 'name', 'domain', 'description', 'retrieval_rank', 'candidate_note', 'evidence'
    ])) return false;
    return CANDIDATE_ID.test(value.id) && text(value.name, 1, 200) &&
      typeof value.domain === 'string' && value.domain.length <= 120 &&
      typeof value.description === 'string' && value.description.length <= 600 &&
      Number.isInteger(value.retrieval_rank) && value.retrieval_rank >= 1 && value.retrieval_rank <= 30 &&
      nullableText(value.candidate_note, 600) &&
      validateEvidence(value.evidence, value.name, 'internal_kb');
  }

  function validateStressPayload(value, requestId, claim) {
    if (!exact(value, [
      'contract_version', 'request_id', 'claim', 'screening_outcome', 'screening_basis',
      'source', 'target', 'structural_correspondences', 'weakest_link', 'rationale',
      'candidate_reference', 'evidence'
    ])) return null;
    if (value.contract_version !== CONTRACT_VERSION || value.request_id !== requestId || value.claim !== claim) return null;
    if (['not_broken_in_screen', 'breaks_in_screen', 'condition_dependent'].indexOf(value.screening_outcome) === -1) return null;
    if (value.screening_basis !== 'internal_ai_red_team' || !text(value.source, 1, 400) || !text(value.target, 1, 400)) return null;
    if (!Array.isArray(value.structural_correspondences) || value.structural_correspondences.length < 1 || value.structural_correspondences.length > 12) return null;
    var validCorrespondences = value.structural_correspondences.every(function (item) {
      return exact(item, ['claim', 'screening_outcome', 'stress_result']) &&
        text(item.claim, 1, 600) && text(item.stress_result, 1, 1000) &&
        ['not_broken', 'breaks', 'uncertain'].indexOf(item.screening_outcome) !== -1;
    });
    if (!validCorrespondences || !text(value.weakest_link, 1, 1000) || !text(value.rationale, 1, 1200)) return null;
    if (!validateCandidateReference(value.candidate_reference)) return null;
    return validateEvidence(value.evidence, claim) ? value : null;
  }

  function validateState(value) {
    return exact(value, ['state_id', 'name', 'definition', 'typical_signal']) &&
      /^[a-z][a-z0-9_]{2,63}$/.test(value.state_id) && text(value.name, 1, 120) &&
      text(value.definition, 1, 500) && text(value.typical_signal, 1, 500);
  }

  function validTextList(value, maxItems, maxChars) {
    return Array.isArray(value) && value.length <= maxItems && value.every(function (item) {
      return text(item, 1, maxChars);
    });
  }

  function validateDiagnosePayload(value, requestId, situation) {
    if (!exact(value, [
      'contract_version', 'request_id', 'situation', 'assessment_kind', 'primary_state',
      'secondary_state', 'reasoning', 'evolution', 'signals_to_watch', 'recommendations',
      'candidate_reference', 'evidence'
    ])) return null;
    if (value.contract_version !== CONTRACT_VERSION || value.request_id !== requestId || value.situation !== situation) return null;
    if (value.assessment_kind !== 'structural_state_hypothesis' || !validateState(value.primary_state)) return null;
    if (value.secondary_state !== null && !validateState(value.secondary_state)) return null;
    if (value.secondary_state && value.secondary_state.state_id === value.primary_state.state_id) return null;
    if (!text(value.reasoning, 1, 1500) || !text(value.evolution, 1, 1200)) return null;
    if (!validTextList(value.signals_to_watch, 6, 500) || !validTextList(value.recommendations, 5, 800)) return null;
    if (!validateCandidateReference(value.candidate_reference)) return null;
    return validateEvidence(value.evidence, situation) ? value : null;
  }

  function validateMethodCandidate(value, expectedRank) {
    if (!exact(value, [
      'id', 'name', 'domain', 'type_id', 'description', 'retrieval_rank',
      'candidate_note', 'evidence'
    ])) return false;
    return CANDIDATE_ID.test(value.id) && text(value.name, 1, 200) &&
      typeof value.domain === 'string' && value.domain.length <= 120 &&
      typeof value.type_id === 'string' && value.type_id.length <= 120 &&
      typeof value.description === 'string' && value.description.length <= 600 &&
      value.retrieval_rank === expectedRank && nullableText(value.candidate_note, 240) &&
      validateEvidence(value.evidence, value.name, 'internal_kb');
  }

  function validateApplyPayload(value, requestId, method) {
    if (!exact(value, [
      'contract_version', 'request_id', 'method', 'signature', 'signature_origin',
      'keywords', 'count', 'candidates', 'evidence'
    ])) return null;
    if (value.contract_version !== CONTRACT_VERSION || value.request_id !== requestId || value.method !== method) return null;
    if (!text(value.signature, 1, 600) || ['model_generated', 'input_fallback'].indexOf(value.signature_origin) === -1) return null;
    if (!validTextList(value.keywords, 6, 30) || !Number.isInteger(value.count) || value.count < 0 || value.count > 20) return null;
    if (!Array.isArray(value.candidates) || value.count !== value.candidates.length) return null;
    var ids = Object.create(null);
    for (var i = 0; i < value.candidates.length; i += 1) {
      var candidate = value.candidates[i];
      if (!validateMethodCandidate(candidate, i + 1) || ids[candidate.id]) return null;
      ids[candidate.id] = true;
    }
    return validateEvidence(value.evidence, method) ? value : null;
  }

  function validateLintPayload(value, requestId, documentText) {
    if (!exact(value, [
      'contract_version', 'request_id', 'screening_kind', 'summary', 'claims', 'evidence'
    ])) return null;
    if (value.contract_version !== CONTRACT_VERSION || value.request_id !== requestId ||
        value.screening_kind !== 'internal_ai_document_screen' || !text(value.summary, 1, 1200)) return null;
    if (!Array.isArray(value.claims) || value.claims.length > 30) return null;
    var normalizedDocument = normalizeSource(documentText);
    var ids = Object.create(null);
    for (var i = 0; i < value.claims.length; i += 1) {
      var claim = value.claims[i];
      if (!exact(claim, [
        'claim_id', 'quote', 'claim_type', 'structure', 'failure_mode', 'review_priority',
        'suggestion', 'reference_candidate', 'evidence'
      ])) return null;
      if (!CLAIM_ID.test(claim.claim_id) || ids[claim.claim_id] ||
          !text(claim.quote, 1, 600) || normalizedDocument.indexOf(normalizeSource(claim.quote)) === -1) return null;
      ids[claim.claim_id] = true;
      if (['assumption', 'analogy', 'causal_judgment'].indexOf(claim.claim_type) === -1 ||
          ['high', 'medium', 'low'].indexOf(claim.review_priority) === -1) return null;
      if (!text(claim.structure, 1, 800) || !text(claim.failure_mode, 1, 800) || !text(claim.suggestion, 1, 800)) return null;
      if (!validateCandidateReference(claim.reference_candidate) || !validateEvidence(claim.evidence, claim.quote)) return null;
    }
    return validateEvidence(value.evidence, '用户提交的策略文档') ? value : null;
  }

  var api = {
    CONTRACT_VERSION: CONTRACT_VERSION,
    createRequestId: createRequestId,
    validateEvidence: validateEvidence,
    validateStressPayload: validateStressPayload,
    validateDiagnosePayload: validateDiagnosePayload,
    validateApplyPayload: validateApplyPayload,
    validateLintPayload: validateLintPayload
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.SecondaryToolContracts = api;
}(typeof window !== 'undefined' ? window : globalThis));
