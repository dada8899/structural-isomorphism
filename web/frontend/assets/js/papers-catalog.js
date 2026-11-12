(function () {
  'use strict';

  const ASSET_VERSION = '20260714n2';
  const MANIFEST_URL = '/assets/data/papers-manifest.json?v=20260714n2';
  const SCHEMA_VERSION = 'papers-manifest-v2';
  const SLUG_PATTERN = '^(?!.*\\.\\.)(?!.*\\.$)[a-z0-9][a-z0-9._-]{1,119}$';
  const SLUG_RE = new RegExp(SLUG_PATTERN);
  const SOURCE_ROOT = '/dada8899/structural-isomorphism/';
  const GROUP_ORDER = ['unified', 'arxiv-drafts', 'phase-papers', 'tutorials'];
  const GROUP_COUNTS = Object.freeze({
    unified: 1,
    'arxiv-drafts': 4,
    'phase-papers': 14,
    tutorials: 1,
  });
  const STATUS_COUNTS = Object.freeze({
    'historical-record': 14,
    'historical-draft': 5,
    'historical-tutorial': 1,
  });
  const STATUS_LABELS = Object.freeze({
    'historical-record': Object.freeze({ zh: '历史结果记录', en: 'Historical result record' }),
    'historical-draft': Object.freeze({ zh: '历史研究稿', en: 'Historical research draft' }),
    'historical-tutorial': Object.freeze({ zh: '历史复现教程', en: 'Historical reproduction tutorial' }),
  });
  const REQUIRED_CONTRACT = Object.freeze({
    schema_version: 'empirical-result-card-v1',
    evidence_level: 'historical_internal_record',
    outcome_status: 'not_normalized_in_current_ledger',
    source_status: 'inspect_record',
    license_status: 'not_recorded_in_manifest',
    preregistration_status: 'not_recorded_in_manifest',
    ledger_status: 'not_bound',
    review_status: 'internal_only',
  });
  const CONTROL_RE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
  let manifestPromise = null;

  function own(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  function requiredText(value, field, maxLength) {
    if (
      typeof value !== 'string' || !value.trim() || value.length > maxLength ||
      CONTROL_RE.test(value)
    ) {
      throw new Error(`Invalid papers manifest field: ${field}`);
    }
    return value.trim();
  }

  function optionalText(value, field, maxLength) {
    if (value == null || value === '') return '';
    return requiredText(value, field, maxLength);
  }

  function integer(value, field, minimum) {
    if (!Number.isInteger(value) || value < minimum) {
      throw new Error(`Invalid papers manifest field: ${field}`);
    }
    return value;
  }

  function validateSlug(value) {
    const slug = requiredText(value, 'paper.slug', 120);
    if (!SLUG_RE.test(slug)) throw new Error(`Invalid paper slug: ${slug}`);
    return slug;
  }

  function validateSourceUrl(value) {
    const source = requiredText(value, 'paper.source_url', 500);
    let parsed;
    try {
      parsed = new URL(source);
    } catch (_error) {
      throw new Error('Invalid paper source URL');
    }
    if (
      parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || parsed.port ||
      parsed.username || parsed.password || parsed.search || parsed.hash ||
      !parsed.pathname.startsWith(SOURCE_ROOT)
    ) {
      throw new Error('Invalid paper source URL');
    }
    return parsed.toString();
  }

  function validateContract(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('Missing empirical result-card contract');
    }
    Object.keys(REQUIRED_CONTRACT).forEach((key) => {
      if (value[key] !== REQUIRED_CONTRACT[key]) {
        throw new Error(`Invalid empirical result-card contract: ${key}`);
      }
    });
    [
      'observed_fallback_zh', 'observed_fallback_en', 'boundary_zh',
      'boundary_en', 'next_test_zh', 'next_test_en',
    ].forEach((key) => requiredText(value[key], `result_contract.${key}`, 900));
    return value;
  }

  function validatePaper(value, seen, statusCounts) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('Invalid paper record');
    }
    const slug = validateSlug(value.slug);
    if (seen.has(slug)) throw new Error(`Duplicate paper slug: ${slug}`);
    seen.add(slug);
    if (own(value, 'external_link')) throw new Error('Paper records must use internal detail routes');
    requiredText(value.title_zh, 'paper.title_zh', 300);
    requiredText(value.title_en, 'paper.title_en', 300);
    optionalText(value.class, 'paper.class', 240);
    optionalText(value.alpha, 'paper.alpha', 240);
    requiredText(value.date, 'paper.date', 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value.date)) throw new Error('Invalid paper date');
    integer(value.words, 'paper.words', 1);
    integer(value.minutes, 'paper.minutes', 1);
    if (value.n_tail != null) integer(value.n_tail, 'paper.n_tail', 1);
    if (!own(STATUS_LABELS, value.status)) throw new Error('Invalid paper status');
    validateSourceUrl(value.source_url);
    statusCounts[value.status] += 1;
    return value;
  }

  function validateManifest(value) {
    if (
      !value || typeof value !== 'object' || Array.isArray(value) ||
      !value.meta || typeof value.meta !== 'object' || !Array.isArray(value.groups)
    ) {
      throw new Error('Invalid papers manifest');
    }
    const meta = value.meta;
    if (meta.schema_version !== SCHEMA_VERSION) throw new Error('Unsupported papers manifest schema');
    if (meta.asset_version !== ASSET_VERSION) throw new Error('Papers asset version drift');
    if (meta.slug_pattern !== SLUG_PATTERN) throw new Error('Papers slug contract drift');
    const contract = validateContract(meta.result_contract);
    const seenGroups = new Set();
    const seenPapers = new Set();
    const statusCounts = {
      'historical-record': 0,
      'historical-draft': 0,
      'historical-tutorial': 0,
    };
    const records = [];

    value.groups.forEach((group, groupIndex) => {
      if (!group || typeof group !== 'object' || Array.isArray(group)) {
        throw new Error('Invalid paper group');
      }
      if (group.id !== GROUP_ORDER[groupIndex] || seenGroups.has(group.id)) {
        throw new Error('Invalid paper group order or duplicate group');
      }
      seenGroups.add(group.id);
      requiredText(group.title_zh, 'group.title_zh', 240);
      requiredText(group.title_en, 'group.title_en', 240);
      requiredText(group.desc_zh, 'group.desc_zh', 800);
      requiredText(group.desc_en, 'group.desc_en', 800);
      if (!Array.isArray(group.papers) || group.papers.length !== GROUP_COUNTS[group.id]) {
        throw new Error(`Paper group count drift: ${group.id}`);
      }
      group.papers.forEach((paper) => records.push(validatePaper(paper, seenPapers, statusCounts)));
    });

    if (seenGroups.size !== GROUP_ORDER.length) throw new Error('Missing paper group');
    const counts = {
      total: integer(meta.total_items, 'meta.total_items', 1),
      records: integer(meta.historical_result_records, 'meta.historical_result_records', 1),
      drafts: integer(meta.historical_research_drafts, 'meta.historical_research_drafts', 1),
      tutorials: integer(meta.historical_tutorials, 'meta.historical_tutorials', 1),
    };
    if (
      counts.total !== records.length || counts.total !== 20 ||
      counts.records !== STATUS_COUNTS['historical-record'] ||
      counts.drafts !== STATUS_COUNTS['historical-draft'] ||
      counts.tutorials !== STATUS_COUNTS['historical-tutorial'] ||
      counts.total !== counts.records + counts.drafts + counts.tutorials
    ) {
      throw new Error('Papers manifest count drift');
    }
    Object.keys(STATUS_COUNTS).forEach((status) => {
      if (statusCounts[status] !== STATUS_COUNTS[status]) {
        throw new Error(`Papers status count drift: ${status}`);
      }
    });
    const bySlug = Object.create(null);
    records.forEach((record) => { bySlug[record.slug] = record; });
    return { manifest: value, contract, records, bySlug, counts };
  }

  function escapeHtml(value) {
    const node = document.createElement('span');
    node.textContent = String(value == null ? '' : value);
    return node.innerHTML;
  }

  function locale() {
    try {
      return window.i18n && window.i18n.getLang && window.i18n.getLang() === 'en' ? 'en' : 'zh';
    } catch (_error) {
      return 'zh';
    }
  }

  function localized(record, field, selectedLocale) {
    const lang = selectedLocale === 'en' ? 'en' : 'zh';
    return record[`${field}_${lang}`] || record[`${field}_zh`] || record[`${field}_en`] || '';
  }

  function paperUrl(slug) {
    return `/paper/${encodeURIComponent(validateSlug(slug))}`;
  }

  function markdownUrl(slug) {
    return `/assets/data/papers/${encodeURIComponent(validateSlug(slug))}.md?v=${ASSET_VERSION}`;
  }

  function slugFromLocation(locationLike) {
    const pathname = String(locationLike && locationLike.pathname || '');
    const pathMatch = pathname.match(/^\/paper\/([^/]+)$/);
    let raw = pathMatch ? pathMatch[1] : '';
    if (!raw && pathname.endsWith('/paper.html')) {
      raw = new URLSearchParams(String(locationLike.search || '')).get('doc') || '';
    }
    try {
      raw = decodeURIComponent(raw);
    } catch (_error) {
      throw new Error('Invalid encoded paper slug');
    }
    return validateSlug(raw);
  }

  function loadManifest(options) {
    const force = Boolean(options && options.force);
    if (force) manifestPromise = null;
    if (!manifestPromise) {
      manifestPromise = fetch(MANIFEST_URL, {
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      }).then((response) => {
        if (!response.ok) throw new Error(`Manifest request failed (${response.status})`);
        return response.json();
      }).then(validateManifest).catch((error) => {
        manifestPromise = null;
        throw error;
      });
    }
    return manifestPromise;
  }

  window.StructuralPapersCatalog = Object.freeze({
    ASSET_VERSION,
    MANIFEST_URL,
    STATUS_LABELS,
    escapeHtml,
    locale,
    localized,
    loadManifest,
    markdownUrl,
    paperUrl,
    slugFromLocation,
    validateManifest,
    validateSlug,
    validateSourceUrl,
  });
})();
