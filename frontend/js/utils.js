/**
 * Unicorn Radar — Shared UI Formatting, Provenance & Epistemic Helpers (ES2022)
 */

export function escapeHtml(val) {
  if (val === null || val === undefined) return '';
  return String(val)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function safeExternalUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return null;
  const trimmed = rawUrl.trim();
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return null;
}

const INTERNAL_ID_TOKEN_RE =
  /\b(?:ev|path|edge|rel|slush-person|slush-company|slush-organization|imported_person|cala):[a-z0-9_-]{4,}\b/gi;

export function stripInternalIds(val) {
  if (val === null || val === undefined) return '';
  let str = String(val);
  // Strip parenthesized or bracketed internal ID lists, e.g. "(ev:0b05e4, ev:1234ab)" or "[ev:0b05e4]"
  str = str.replace(
    /[\(\[]\s*(?:(?:ev|path|edge|rel|slush-person|slush-company|slush-organization|imported_person|cala):[a-z0-9_-]{4,}\s*[,;/\s]*)+[\)\]]/gi,
    ''
  );
  // Strip any remaining bare internal ID tokens
  str = str.replace(INTERNAL_ID_TOKEN_RE, '');
  // Clean up double spaces or space before punctuation
  return str
    .replace(/\s+([,.;:!?])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

const DATASET_LABELS = {
  cala: 'Cala Graph',
  cala_company_dossier: 'Cala Dossier',
  cala_people_connectors: 'Cala Connectors',
  cala_roster: 'Cala Roster',
  cala_shared_bridges: 'Cala Graph',
  slush_people: 'Slush 2026',
  slush_companies: 'Slush 2026',
};

export function humanizeDatasetLabel(ds) {
  if (!ds) return 'Verified Source';
  if (DATASET_LABELS[ds]) return DATASET_LABELS[ds];
  if (String(ds).startsWith('slush')) return 'Slush 2026';
  if (String(ds).startsWith('cala')) return 'Cala Graph';
  return String(ds).replace(/_/g, ' ');
}

function formatDomainLabel(rawUrl) {
  try {
    const host = new URL(rawUrl).hostname.toLowerCase().replace(/^www\./, '');
    if (host === 'platform.slush.org') return 'slush.org';
    if (host.endsWith('.linkedin.com')) return 'linkedin.com';
    return host;
  } catch {
    return '';
  }
}

export function shortId(id, maxLen = 18) {
  if (!id) return '';
  const str = String(id);
  if (str.length <= maxLen) return str;
  const colonIdx = str.indexOf(':');
  if (colonIdx > 0 && colonIdx < 16) {
    const prefix = str.slice(0, colonIdx + 1);
    const rest = str.slice(colonIdx + 1);
    return `${prefix}${rest.slice(0, 8)}…`;
  }
  return `${str.slice(0, maxLen - 1)}…`;
}

export function formatMs(ms) {
  if (ms === null || ms === undefined || Number.isNaN(Number(ms))) return '—';
  const n = Number(ms);
  if (n < 10) return `${n.toFixed(1)} ms`;
  if (n < 1000) return `${Math.round(n)} ms`;
  return `${(n / 1000).toFixed(2)} s`;
}

export function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return '—';
  const n = Number(bytes);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * Supports indexing response.evidence whether passed as EvidenceItem[] or {[id]: EvidenceItem}
 */
export function indexEvidence(evidencePayload) {
  const map = new Map();
  if (!evidencePayload) return map;
  if (Array.isArray(evidencePayload)) {
    for (const item of evidencePayload) {
      if (item && item.id) {
        map.set(item.id, item);
      }
    }
  } else if (typeof evidencePayload === 'object') {
    for (const [key, item] of Object.entries(evidencePayload)) {
      if (item && typeof item === 'object') {
        const id = item.id || key;
        map.set(id, { id, ...item });
      }
    }
  }
  return map;
}

/**
 * Determines canonical origin category ('both' | 'cala' | 'slush') for a node or edge
 */
export function detectOriginKind(entityOrEdge) {
  if (!entityOrEdge) return 'cala';

  if (Array.isArray(entityOrEdge.origins)) {
    const hasCala = entityOrEdge.origins.some((o) => String(o).includes('cala'));
    const hasSlush = entityOrEdge.origins.some((o) => String(o).includes('slush'));
    if (hasCala && hasSlush) return 'both';
    if (hasSlush) return 'slush';
    return 'cala';
  }

  if (Array.isArray(entityOrEdge.origin_badges)) {
    const hasCala = entityOrEdge.origin_badges.some((o) => String(o).includes('cala'));
    const hasSlush = entityOrEdge.origin_badges.some((o) => String(o).includes('slush'));
    if (hasCala && hasSlush) return 'both';
    if (hasSlush) return 'slush';
    if (hasCala) return 'cala';
  }

  const sids = entityOrEdge.source_ids;
  if (sids && typeof sids === 'object') {
    const hasCala = Array.isArray(sids.cala) && sids.cala.length > 0;
    const hasSlush = Array.isArray(sids.slush) && sids.slush.length > 0;
    if (hasCala && hasSlush) return 'both';
    if (hasSlush) return 'slush';
    if (hasCala) return 'cala';
  }

  const id = String(entityOrEdge.id || '');
  if (id.startsWith('slush-')) return 'slush';
  if (id.startsWith('cala:')) return 'cala';
  return 'cala';
}

export function renderOriginBadges(item) {
  const kind = detectOriginKind(item);
  if (kind === 'both') {
    return `<span class="badge badge-dual">Cala + Slush</span>`;
  }
  if (kind === 'slush') {
    const isRef = String(item?.id || '').startsWith('slush-organization:');
    return `<span class="badge badge-slush">${isRef ? 'Slush org' : 'Slush 2026'}</span>`;
  }
  return `<span class="badge badge-cala">Cala</span>`;
}

export function renderCompletenessBadge(completeness) {
  if (!completeness) return '';
  if (completeness === 'full') {
    return `<span class="badge badge-neutral">Full profile</span>`;
  }
  return '';
}

export function renderParticipationBadges(participationList = []) {
  if (!Array.isArray(participationList) || participationList.length === 0) return '';
  const labels = {
    announced_speaker: { text: 'Slush speaker', cls: 'badge-slush' },
    announced_attendee: { text: 'Slush attendee', cls: 'badge-slush' },
    platform_directory: { text: 'Slush directory', cls: 'badge-slush' },
    company_listed: { text: 'Listed at Slush', cls: 'badge-slush' },
    cala_event_link: { text: 'Slush participant', cls: 'badge-cala' },
  };
  return participationList
    .map((p) => {
      const meta = labels[p.status] || { text: p.status || 'Slush', cls: 'badge-neutral' };
      return `<span class="badge ${meta.cls}">${escapeHtml(meta.text)}</span>`;
    })
    .join(' ');
}

/**
 * Renders clean human-readable source provenance badges/links (no raw internal ev:... IDs)
 */
export function renderEvidenceChips(evidenceIds = [], evidenceMap = new Map(), maxVisible = 5) {
  if (!Array.isArray(evidenceIds) || evidenceIds.length === 0) return '';
  const uniqueIds = [...new Set(evidenceIds.filter(Boolean))];

  const resolvedItems = [];
  const seenKeys = new Set();

  for (const evId of uniqueIds) {
    const ev = evidenceMap.get(evId);
    const isSlush = Boolean(ev?.dataset && String(ev.dataset).startsWith('slush'));
    const docs = Array.isArray(ev?.source_documents) ? ev.source_documents : [];
    const doc = docs.find((d) => safeExternalUrl(d?.url || d?.document || d?.source_url)) || docs[0] || null;
    const rec = ev?.record || {};

    const url = safeExternalUrl(
      doc?.url ||
        doc?.document ||
        doc?.source_url ||
        rec.primary_source_url ||
        rec.profile_url ||
        rec.profile_link ||
        rec.company?.company_profile_url ||
        rec.website
    );

    const domainLabel = url ? formatDomainLabel(url) : '';
    const dsLabel = humanizeDatasetLabel(ev?.dataset);
    const label = domainLabel || doc?.publisher || doc?.name || dsLabel;

    const dedupKey = `${label.toLowerCase()}|${url ? formatDomainLabel(url) : 'nourl'}`;
    if (seenKeys.has(dedupKey)) continue;
    seenKeys.add(dedupKey);

    const titleDetail = doc?.title || doc?.publisher || dsLabel;
    const date = doc?.date || doc?.checked_at || doc?.published_at || '';
    const tipParts = [titleDetail];
    if (date) tipParts.push(`Verified ${date}`);
    if (url) tipParts.push('Open source');
    const tip = tipParts.filter(Boolean).join(' · ');

    resolvedItems.push({ evId, isSlush, url, label, tip });
  }

  const shown = resolvedItems.slice(0, maxVisible);
  const overflow = resolvedItems.length - shown.length;

  const chipsHtml = shown
    .map(({ evId, isSlush, url, label, tip }) => {
      if (url) {
        return `<a class="ev-chip ${isSlush ? 'slush-origin' : ''}" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" data-ev-id="${escapeHtml(evId)}" title="${escapeHtml(tip)}">
        <span>${escapeHtml(label)}</span><span aria-hidden="true" style="font-size:0.66rem;opacity:0.65;">↗</span>
      </a>`;
      }
      return `<span class="ev-chip ev-chip-static ${isSlush ? 'slush-origin' : ''}" data-ev-id="${escapeHtml(evId)}" title="${escapeHtml(tip)}">
        <span>${escapeHtml(label)}</span>
      </span>`;
    })
    .join('');

  const moreHtml =
    overflow > 0
      ? `<span class="badge badge-neutral" title="${overflow} additional verified sources">+${overflow}</span>`
      : '';

  return `<span class="ev-chip-group">${chipsHtml}${moreHtml}</span>`;
}

/**
 * Renders clickable external source provenance badge (Publisher + Title + URL + Date)
 */
export function renderSourceDocumentBadge(doc) {
  if (!doc) return '';
  const url = safeExternalUrl(doc.url || doc.document || doc.source_url);
  const publisher = doc.publisher || doc.name || doc.source_kind || doc.source_type || 'Source';

  let title = '';
  if (doc.title && doc.title !== publisher) {
    title = doc.title;
  } else if (doc.source_rank) {
    title = doc.source_rank;
  } else if (url) {
    try {
      const parsedUrl = new URL(url);
      const host = parsedUrl.hostname.replace(/^www\./, '');
      if (host.toLowerCase() !== String(publisher).replace(/^www\./, '').toLowerCase()) {
        title = host;
      } else {
        const cleanPath = (parsedUrl.pathname + parsedUrl.hash).replace(/^\/+/, '');
        title = cleanPath ? cleanPath.slice(0, 28) : 'Verified Source';
      }
    } catch {
      title = 'Verified Source';
    }
  } else {
    title = doc.source_type || doc.source_kind || 'Verified Source';
  }

  const date = doc.date || doc.checked_at || doc.published_at || '';

  const inner = `
    <span class="source-doc-pub">${escapeHtml(publisher)}</span>
    <span style="opacity:0.55;">·</span>
    <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:210px;">${escapeHtml(title)}</span>
    ${date ? `<span class="source-doc-date">${escapeHtml(date)}</span>` : ''}
    ${url ? `<span style="font-size:0.68rem;color:var(--cala-bright);">↗</span>` : ''}
  `;

  if (url) {
    return `<a class="source-doc-badge" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${inner}</a>`;
  }
  return `<span class="source-doc-badge">${inner}</span>`;
}

export function humanizePredicate(predicate) {
  if (!predicate) return 'LINKED_TO';
  return String(predicate).replace(/_/g, ' ');
}

export function formatQuestionLabel(qid) {
  const map = {
    person_to_company: 'Q1 · Person → Company',
    company_to_company: 'Q2 · Company ↔ Company',
    company_network: 'Q3 · Company Network',
    company_representatives: 'Q4 · Slush Representatives',
  };
  return map[qid] || qid;
}

export function renderStatusBadge(status) {
  const map = {
    complete: { label: 'Verified via Cala', cls: 'badge-dual' },
    partial: { label: 'Verified via Cala', cls: 'badge-cala' },
    needs_resolution: { label: 'Select exact entity', cls: 'badge-slush' },
    ambiguous: { label: 'Select exact entity', cls: 'badge-slush' },
    insufficient_data: { label: 'No verified path', cls: 'badge-warn' },
    not_found: { label: 'Entity not found', cls: 'badge-warn' },
  };
  const info = map[status] || { label: status || 'Ready', cls: 'badge-neutral' };
  return `<span class="badge ${info.cls}">${escapeHtml(info.label)}</span>`;
}

export function showToast(message, type = 'info', durationMs = 3600) {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const el = document.createElement('div');
  el.className = `toast ${type === 'error' ? 'error' : ''}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity 0.2s ease';
    setTimeout(() => el.remove(), 220);
  }, durationMs);
}

export async function copyTextToClipboard(text, label = 'Copied to clipboard') {
  try {
    await navigator.clipboard.writeText(text);
    showToast(label);
  } catch {
    showToast('Clipboard access unavailable in this context', 'error');
  }
}
