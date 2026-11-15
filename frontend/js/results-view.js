/**
 * Unicorn Radar — Grounded Intelligence, Disambiguation, Inspector & Provenance Renderer (ES2022)
 */

import {
  escapeHtml,
  safeExternalUrl,
  formatMs,
  renderOriginBadges,
  renderCompletenessBadge,
  renderParticipationBadges,
  renderEvidenceChips,
  renderSourceDocumentBadge,
  renderStatusBadge,
  humanizePredicate,
  humanizeDatasetLabel,
  stripInternalIds,
} from './utils.js?v=20261115c';

/* ==========================================================================
   1. Interactive Identity Disambiguation Panel
   ========================================================================== */

export function renderDisambiguationPanel(analysis, panelEl, evidenceMap, onSelectCandidate) {
  if (!panelEl) return;
  const status = analysis?.status;
  const resolution = analysis?.resolution;

  if ((status !== 'needs_resolution' && status !== 'ambiguous' && status !== 'not_found') || !resolution) {
    panelEl.classList.remove('visible');
    panelEl.innerHTML = '';
    return;
  }

  const slotEntries = Object.entries(resolution).filter(
    ([, slotObj]) => slotObj && (slotObj.status === 'needs_resolution' || slotObj.status === 'not_found' || (slotObj.candidates && slotObj.candidates.length > 0))
  );

  if (slotEntries.length === 0) {
    panelEl.classList.remove('visible');
    panelEl.innerHTML = '';
    return;
  }

  const slotBlocksHtml = slotEntries
    .map(([slotName, slotData]) => {
      const slotLabelMap = {
        source: 'Starting Entity',
        target: 'Target Entity',
        company: 'Target Company',
      };
      const candidates = Array.isArray(slotData.candidates) ? slotData.candidates : [];

      if (candidates.length === 0) {
        return `
          <div class="disambig-slot-block">
            <div class="disambig-slot-title">${escapeHtml(slotLabelMap[slotName] || slotName)} — Query: “${escapeHtml(slotData.query || '')}”</div>
            <div class="honest-empty-banner">
              <div class="honest-empty-title">No Matching Entity in Loaded Snapshot</div>
              <div style="font-size:0.8rem;color:var(--text-secondary);">
                ${escapeHtml(slotData.reason || 'This name was not found in the reconciled Cala + Slush 2026 snapshot. Try typing in the search input above for fuzzy suggestions.')}
              </div>
            </div>
          </div>
        `;
      }

      const cardsHtml = candidates
        .map((cand) => {
          const ctx = cand.context || cand.profile || {};
          const affiliations = Array.isArray(cand.affiliations) ? cand.affiliations : [];
          const degree = cand.traversable_degree;
          const websiteUrl = safeExternalUrl(ctx.website);

          return `
            <div class="candidate-card">
              <div>
                <div style="display:flex;align-items:center;justify-content:space-between;gap:0.4rem;flex-wrap:wrap;margin-bottom:0.45rem;">
                  <strong style="font-family:var(--font-display);font-size:0.95rem;">${escapeHtml(cand.name)}</strong>
                  <div style="display:flex;gap:0.28rem;flex-wrap:wrap;">
                    ${renderOriginBadges(cand)}
                    ${renderCompletenessBadge(cand.record_completeness)}
                  </div>
                </div>
                <div class="candidate-meta">
                  ${renderParticipationBadges(cand.participation) ? `<div>${renderParticipationBadges(cand.participation)}</div>` : ''}
                  ${ctx.job_title ? `<div><strong>Role:</strong> ${escapeHtml(ctx.job_title)}</div>` : ''}
                  ${ctx.location_raw ? `<div><strong>Location:</strong> ${escapeHtml(ctx.location_raw)}</div>` : ''}
                  ${websiteUrl ? `<div><strong>Website:</strong> <a href="${escapeHtml(websiteUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(websiteUrl)}</a></div>` : ''}
                  ${affiliations.length > 0 ? `<div><strong>Documented Affiliations:</strong> ${escapeHtml(affiliations.join(', '))}</div>` : ''}
                  ${degree !== undefined ? `<div><strong>Traversable Connections:</strong> ${escapeHtml(degree)} verified edge${degree === 1 ? '' : 's'}</div>` : ''}
                  ${Array.isArray(cand.evidence_ids) && cand.evidence_ids.length > 0 ? `<div style="margin-top:0.25rem;">${renderEvidenceChips(cand.evidence_ids, evidenceMap, 4)}</div>` : ''}
                </div>
              </div>
              <button
                type="button"
                class="btn-select-candidate"
                data-select-slot="${escapeHtml(slotName)}"
                data-select-id="${escapeHtml(cand.id)}"
                data-select-name="${escapeHtml(cand.name)}"
              >
                Select Canonical Identity &amp; Run Search →
              </button>
            </div>
          `;
        })
        .join('');

      return `
        <div class="disambig-slot-block">
          <div class="disambig-slot-title">
            ${escapeHtml(slotLabelMap[slotName] || slotName)} · “${escapeHtml(slotData.query || '')}” (${candidates.length} distinct records)
          </div>
          <div class="candidates-grid">${cardsHtml}</div>
        </div>
      `;
    })
    .join('');

  panelEl.innerHTML = `
    <div class="disambig-header">
      <div>
        <h3 class="disambig-title">
          <span>🛡️ Identity Integrity Guardrail — Zero Silent Merging</span>
        </h3>
        <p class="disambig-sub">
          ${escapeHtml(stripInternalIds(analysis.summary) || 'Multiple distinct records share this name across Cala and Slush snapshots. Select the exact profile below to run a verified search.')}
        </p>
      </div>
      ${renderStatusBadge(status)}
    </div>
    ${slotBlocksHtml}
  `;

  panelEl.classList.add('visible');

  for (const btn of panelEl.querySelectorAll('.btn-select-candidate')) {
    btn.addEventListener('click', () => {
      const slot = btn.getAttribute('data-select-slot');
      const id = btn.getAttribute('data-select-id');
      const name = btn.getAttribute('data-select-name');
      onSelectCandidate?.({ slot, id, name });
    });
  }
}

/* ==========================================================================
   2. Live Cala /v1 Enrichment Box Renderer (Strict Namespace Separation)
   ========================================================================== */

export function renderCalaLiveEnrichmentBox(enrichPayload) {
  if (!enrichPayload) return '';

  const st = enrichPayload.status || 'unavailable';
  const isOk = st === 'ok';
  const isWarnHalt = st === 'payment_required' || st === 'rate_limited' || st === 'timeout' || st === 'unconfigured' || st === 'not_mapped';

  const statusBadgeMap = {
    ok: { text: '✓ Live Cala /v1 Verified', cls: 'badge-cala' },
    payment_required: { text: 'HTTP 402 · Insufficient Balance — Clean Halt', cls: 'badge-warn' },
    unconfigured: { text: 'CALA_API_KEY Unconfigured — Snapshot Only', cls: 'badge-neutral' },
    not_mapped: { text: 'Unmapped in Cala /v1 — Zero Guessing', cls: 'badge-neutral' },
    rate_limited: { text: 'HTTP 429 · Rate Limited — Clean Halt', cls: 'badge-warn' },
    timeout: { text: 'Timeout — Clean Halt', cls: 'badge-warn' },
  };
  const badgeMeta = statusBadgeMap[st] || { text: `Status: ${st}`, cls: 'badge-neutral' };

  const facts = Array.isArray(enrichPayload.verified_facts) ? enrichPayload.verified_facts : [];
  const rels = Array.isArray(enrichPayload.verified_relationships) ? enrichPayload.verified_relationships : [];
  const investorMatch = enrichPayload.cala_verified_investor_match;

  const factsHtml = facts
    .map((f) => {
      const valStr = typeof f.value === 'object' ? JSON.stringify(f.value) : String(f.value ?? '');
      const urlVal = safeExternalUrl(valStr);
      const sourcesHtml = (f.sources || []).map((s) => renderSourceDocumentBadge(s)).join(' ');
      return `
        <div class="fact-row">
          <div class="fact-label">${escapeHtml(f.label || f.field)}</div>
          <div class="fact-value">
            ${urlVal ? `<a href="${escapeHtml(urlVal)}" target="_blank" rel="noopener noreferrer">${escapeHtml(urlVal)}</a>` : escapeHtml(valStr)}
          </div>
          ${sourcesHtml ? `<div style="display:flex;gap:0.35rem;flex-wrap:wrap;">${sourcesHtml}</div>` : ''}
        </div>
      `;
    })
    .join('');

  const relsHtml = rels
    .slice(0, 8)
    .map((r) => {
      const sourcesHtml = (r.sources || []).map((s) => renderSourceDocumentBadge(s)).join(' ');
      return `
        <div class="fact-row">
          <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;margin-bottom:0.22rem;">
            <span class="badge badge-cala">${escapeHtml(humanizePredicate(r.predicate))}</span>
            <span style="font-size:0.72rem;color:var(--text-dim);">(${escapeHtml(r.direction || 'linked')})</span>
            <strong>${escapeHtml(r.peer_name || r.peer_cala_id || 'Entity')}</strong>
          </div>
          ${sourcesHtml ? `<div style="display:flex;gap:0.35rem;flex-wrap:wrap;">${sourcesHtml}</div>` : ''}
        </div>
      `;
    })
    .join('');

  const investorMatchHtml = investorMatch
    ? `
      <div style="margin-top:0.5rem;padding:0.5rem 0.65rem;border-radius:6px;background:rgba(6,182,212,0.09);border:1px solid var(--cala-border);font-size:0.76rem;">
        <div style="font-weight:600;color:var(--cala-bright);margin-bottom:2px;">Preserved Cala Audit Registry Match</div>
        <div><strong>${escapeHtml(investorMatch.cala_name || '')}</strong>${investorMatch.country ? ` · ${escapeHtml(investorMatch.country)}` : ''}</div>
      </div>
    `
    : '';

  return `
    <div class="cala-live-box ${isWarnHalt && !isOk ? 'warn-halt' : ''}">
      <div class="cala-live-header">
        <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
          <span class="badge ${badgeMeta.cls}">${escapeHtml(badgeMeta.text)}</span>
        </div>
        ${enrichPayload.elapsed_ms !== undefined ? `<span class="mono" style="font-size:0.68rem;color:var(--text-dim);">${formatMs(enrichPayload.elapsed_ms)}${enrichPayload.cached ? ' · cached' : ''}</span>` : ''}
      </div>
      <div style="font-size:0.77rem;color:var(--text-secondary);margin-bottom:0.35rem;">
        ${escapeHtml(stripInternalIds(enrichPayload.message) || 'Isolated from snapshot hop counts to preserve deterministic reproducibility.')}
      </div>
      ${investorMatchHtml}
      ${factsHtml}
      ${relsHtml}
    </div>
  `;
}

/* ==========================================================================
   3. Node & Edge Docked Inspector Drawer
   ========================================================================== */

export function renderNodeInspector({
  node,
  inspectorEl,
  evidenceMap,
  enrichmentCacheMap,
  onTriggerCalaEnrich,
  onPivotCompany,
  onClose,
}) {
  if (!inspectorEl || !node) return;
  const p = node.profile || {};
  const websiteUrl = safeExternalUrl(p.website || p.personal_website || p.profile_url);
  const linkedinUrl = safeExternalUrl(p.linkedin_url);
  const topics = Array.isArray(p.professional_topics) ? p.professional_topics : [];
  const workEntries = Array.isArray(p.work_experience?.entries) ? p.work_experience.entries : [];
  const calaIds = node.source_ids?.cala || [];
  const slushIds = node.source_ids?.slush || [];
  const cachedEnrich = enrichmentCacheMap?.get(node.id) || null;

  inspectorEl.innerHTML = `
    <div class="inspector-header">
      <div>
        <div style="display:flex;align-items:center;gap:0.38rem;flex-wrap:wrap;margin-bottom:0.25rem;">
          <span class="badge badge-neutral">${escapeHtml(node.entity_type || 'Entity')}</span>
          ${renderOriginBadges(node)}
          ${renderCompletenessBadge(node.record_completeness)}
        </div>
        <h4 class="inspector-title">${escapeHtml(node.name || 'Entity')}</h4>
      </div>
      <div style="display:flex;gap:0.4rem;align-items:center;flex-wrap:wrap;">
        ${
          node.entity_type !== 'Person'
            ? `<button type="button" class="btn-ghost-sm" id="btnPivotQ4Node">People at Slush</button>`
            : ''
        }
        <button type="button" class="btn-ghost-sm" id="btnCloseInspector">&times;</button>
      </div>
    </div>

    ${
      Array.isArray(node.participation) && node.participation.length > 0
        ? `<div style="margin-bottom:0.55rem;">${renderParticipationBadges(node.participation)}</div>`
        : ''
    }

    ${p.job_title ? `<div style="font-size:0.84rem;color:var(--text-primary);font-weight:500;margin-bottom:0.35rem;">${escapeHtml(p.job_title)}</div>` : ''}
    ${p.biography || p.description ? `<p style="font-size:0.82rem;color:var(--text-secondary);margin:0 0 0.6rem;line-height:1.55;">${escapeHtml(p.biography || p.description)}</p>` : ''}

    <div style="display:flex;gap:0.75rem;flex-wrap:wrap;font-size:0.78rem;margin-bottom:0.55rem;">
      ${websiteUrl ? `<a href="${escapeHtml(websiteUrl)}" target="_blank" rel="noopener noreferrer">Website ↗</a>` : ''}
      ${linkedinUrl ? `<a href="${escapeHtml(linkedinUrl)}" target="_blank" rel="noopener noreferrer">LinkedIn ↗</a>` : ''}
      ${p.headquarters || p.location_raw ? `<span style="color:var(--text-muted);">${escapeHtml(p.headquarters || p.location_raw)}</span>` : ''}
    </div>

    ${
      p.funding_stage || p.total_funding || p.employees || p.founded || p.at_slush_2026 || p.slush_branches_connected
        ? `<div style="display:flex;gap:0.35rem;flex-wrap:wrap;margin-bottom:0.6rem;">
            ${p.funding_stage ? `<span class="badge badge-cala">Stage: ${escapeHtml(p.funding_stage)}</span>` : ''}
            ${p.total_funding ? `<span class="badge badge-dual">Funding: ${escapeHtml(p.total_funding)}</span>` : ''}
            ${p.employees ? `<span class="badge badge-neutral">Employees: ${escapeHtml(p.employees)}</span>` : ''}
            ${p.founded ? `<span class="badge badge-neutral">Founded: ${escapeHtml(p.founded)}</span>` : ''}
            ${p.at_slush_2026 && p.at_slush_2026 !== 'NO' ? `<span class="badge badge-slush">Slush 2026: ${escapeHtml(p.at_slush_2026)}</span>` : ''}
            ${p.slush_branches_connected ? `<span class="badge badge-cala">${escapeHtml(p.slush_branches_connected)} Slush branches</span>` : ''}
          </div>`
        : ''
    }

    ${
      topics.length > 0
        ? `<div style="display:flex;gap:0.3rem;flex-wrap:wrap;margin-bottom:0.6rem;">
            ${topics.map((t) => `<span class="badge badge-ai">${escapeHtml(t)}</span>`).join('')}
          </div>`
        : ''
    }

    ${
      workEntries.length > 0
        ? `<div style="margin-bottom:0.65rem;">
            <div style="font-size:0.75rem;font-weight:500;color:var(--text-muted);margin-bottom:0.35rem;">Work history</div>
            ${workEntries
              .map((w) => {
                const provBadges = (w.provenance || []).map((pr) => renderSourceDocumentBadge(pr)).join(' ');
                return `
                  <div style="padding:0.45rem 0.65rem;background:var(--bg-surface);border:1px solid var(--hairline);border-radius:6px;margin-bottom:0.35rem;font-size:0.78rem;">
                    <div><strong>${escapeHtml(w.role || w.title || 'Role')}</strong> · ${escapeHtml(w.organization || 'Organization')}</div>
                    ${provBadges ? `<div style="margin-top:0.25rem;">${provBadges}</div>` : ''}
                  </div>
                `;
              })
              .join('')}
          </div>`
        : ''
    }

    <div style="display:flex;align-items:center;justify-content:space-between;gap:0.5rem;flex-wrap:wrap;padding-top:0.45rem;border-top:1px solid var(--border-subtle);font-size:0.72rem;color:var(--text-muted);">
      <span>Verified sources</span>
      <div>${renderEvidenceChips(node.evidence_ids, evidenceMap, 6)}</div>
    </div>

    <div id="inspectorCalaLiveSlot">
      ${cachedEnrich ? renderCalaLiveEnrichmentBox(cachedEnrich) : ''}
    </div>
  `;

  inspectorEl.classList.add('open');

  inspectorEl.querySelector('#btnCloseInspector')?.addEventListener('click', () => {
    inspectorEl.classList.remove('open');
    onClose?.();
  });

  inspectorEl.querySelector('#btnPivotQ4Node')?.addEventListener('click', () => {
    onPivotCompany?.(node);
  });

  const enrichBtn = inspectorEl.querySelector('#btnLiveCalaEnrichNode');
  enrichBtn?.addEventListener('click', async () => {
    enrichBtn.disabled = true;
    enrichBtn.textContent = 'Querying Cala /v1…';
    try {
      const payload = await onTriggerCalaEnrich?.(node.id);
      const slot = inspectorEl.querySelector('#inspectorCalaLiveSlot');
      if (slot && payload) {
        slot.innerHTML = renderCalaLiveEnrichmentBox(payload);
      }
    } finally {
      enrichBtn.disabled = false;
      enrichBtn.textContent = '⚡ Live Cala /v1 Enrich';
    }
  });
}

export function renderEdgeInspector({ edge, nodeMap, inspectorEl, evidenceMap, onClose }) {
  if (!inspectorEl || !edge) return;
  const srcNode = nodeMap.get(edge.source);
  const tgtNode = nodeMap.get(edge.target);
  const propsEntries = Object.entries(edge.properties || {}).filter(([, v]) => v !== null && v !== undefined && v !== '');

  inspectorEl.innerHTML = `
    <div class="inspector-header">
      <div>
        <div style="display:flex;align-items:center;gap:0.38rem;flex-wrap:wrap;margin-bottom:0.25rem;">
          <span class="badge badge-cala">${escapeHtml(humanizePredicate(edge.type))}</span>
          ${renderOriginBadges(edge)}
          <span class="badge badge-neutral">Temporal: ${escapeHtml(edge.temporal_status || 'undated')}</span>
        </div>
        <h4 class="inspector-title">
          ${escapeHtml(srcNode?.name || 'Source')} <span style="color:var(--cala-bright);">→</span> ${escapeHtml(tgtNode?.name || 'Target')}
        </h4>
        <div style="font-size:0.72rem;color:var(--text-dim);margin-top:2px;">Strength: ${escapeHtml(humanizePredicate(edge.evidence_strength || 'documented').toLowerCase())}</div>
      </div>
      <button type="button" class="btn-ghost-sm" id="btnCloseEdgeInspector">&times;</button>
    </div>

    ${
      propsEntries.length > 0
        ? `<div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:0.55rem;">
            ${propsEntries.map(([k, v]) => `<span class="badge badge-neutral" style="margin-right:0.3rem;">${escapeHtml(k)}: ${escapeHtml(String(v))}</span>`).join('')}
          </div>`
        : ''
    }

    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;padding-top:0.45rem;border-top:1px solid var(--border-subtle);">
      <span style="font-size:0.74rem;color:var(--text-muted);">Factual assertion direction preserved regardless of search traversal.</span>
      ${renderEvidenceChips(edge.evidence_ids, evidenceMap, 8)}
    </div>
  `;

  inspectorEl.classList.add('open');
  inspectorEl.querySelector('#btnCloseEdgeInspector')?.addEventListener('click', () => {
    inspectorEl.classList.remove('open');
    onClose?.();
  });
}

/* ==========================================================================
   4. Right Column — Full Intelligence Feed Renderer
   ========================================================================== */

export function renderIntelColumn({
  analysis,
  containerEl,
  evidenceMap,
  isolatedPathId,
  onIsolatePath,
  onInspectNodeById,
  onPivotQuestion,
}) {
  if (!containerEl || !analysis) return;

  const qid = analysis.question_id;
  const pathsMap = new Map((analysis.graph?.paths || []).map((p) => [p.id, p]));
  const nodesMap = new Map((analysis.graph?.nodes || []).map((n) => [n.id, n]));

  // 1) Summary & Epistemic Status Card
  const cov = analysis.coverage || {};
  const hopSel = analysis.hop_selection || cov.hop_selection || null;
  const hopModeLabel = hopSel?.hop_mode
    ? `${hopSel.hop_mode.charAt(0).toUpperCase()}${hopSel.hop_mode.slice(1)} · ${hopSel.selected_hops ?? cov.max_hops ?? ''} Hops`
    : cov.max_hops
      ? `Max ${cov.max_hops} Hops`
      : '';
  const liveEnrichInline = analysis.cala_live_enrichment;
  let inlineEnrichHtml = '';
  if (liveEnrichInline) {
    if (liveEnrichInline.status) {
      inlineEnrichHtml = renderCalaLiveEnrichmentBox(liveEnrichInline);
    } else if (typeof liveEnrichInline === 'object') {
      inlineEnrichHtml = Object.values(liveEnrichInline)
        .filter((v) => v && typeof v === 'object')
        .map((v) => renderCalaLiveEnrichmentBox(v))
        .join('');
    }
  }

  const summaryCardHtml = `
    <div class="intel-card">
      <div class="card-header-row">
        <span class="section-eyebrow">Relationship summary</span>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${renderStatusBadge(analysis.status)}
          ${hopModeLabel ? `<span class="badge badge-cala">${escapeHtml(hopModeLabel)}</span>` : ''}
        </div>
      </div>
      <h3 class="summary-headline">${escapeHtml(stripInternalIds(analysis.summary) || 'Analysis ready')}</h3>
      ${
        analysis.interpretation
          ? `<div class="epistemic-note">${escapeHtml(stripInternalIds(analysis.interpretation))}</div>`
          : ''
      }
      ${
        cov.hop_depth_note
          ? `<div class="epistemic-note" style="margin-top:8px;">${escapeHtml(cov.hop_depth_note)}</div>`
          : ''
      }
    </div>
  `;

  // 2) Grounded AI Claims & Gemma 3 Entailment Shield Card
  const claims = Array.isArray(analysis.generated_claims) ? analysis.generated_claims : [];
  const gemmaSum = analysis.gemma_audit_summary;
  let claimsCardHtml = '';

  if (claims.length > 0) {
    let gemmaHeaderBadge = `<span class="badge badge-neutral">${escapeHtml(analysis.generation_mode || 'template')}</span>`;
    if (gemmaSum && gemmaSum.enabled) {
      const pass = gemmaSum.overall_verdict === 'pass' && (!gemmaSum.flagged_claims || gemmaSum.flagged_claims === 0);
      gemmaHeaderBadge = `
        <span class="badge ${pass ? 'badge-dual' : 'badge-warn'}" title="Audited by ${escapeHtml(gemmaSum.model || 'Gemma 3')}">
          ${pass ? '✓ Gemma 3 Entailment Pass' : '⚠ Gemma Audit Flagged'} · ${escapeHtml(gemmaSum.supported_claims ?? claims.length)}/${escapeHtml(gemmaSum.audited_claims ?? claims.length)} (${escapeHtml(gemmaSum.model || 'gemma-3')})
        </span>
      `;
    }

    const claimItemsHtml = claims
      .map((c) => {
        const audit = c.gemma_audit;
        let auditPill = '';
        if (audit && audit.verdict) {
          const isSup = audit.verdict === 'supported' || audit.verdict === 'pass';
          auditPill = `
            <span class="gemma-verdict-pill ${isSup ? 'supported' : 'flagged'}" title="${escapeHtml(audit.note || '')}">
              ${isSup ? '✓ Gemma Verified' : `⚠ ${escapeHtml(audit.verdict)}`}
            </span>
          `;
        }
        return `
          <div class="claim-item">
            <div class="claim-text">${escapeHtml(stripInternalIds(c.text))}</div>
            <div class="claim-footer">
              ${renderEvidenceChips(c.evidence_ids, evidenceMap, 6)}
              ${auditPill}
            </div>
            ${audit?.note ? `<div class="gemma-note"><strong>Gemma 3 Audit:</strong> ${escapeHtml(stripInternalIds(audit.note))}</div>` : ''}
          </div>
        `;
      })
      .join('');

    claimsCardHtml = `
      <div class="intel-card ai-accent">
        <div class="card-header-row">
          <h3 class="card-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#A78BFA" stroke-width="2.2">
              <path d="M12 2L15 9l7 3-7 3-3 7-3-7-7-3 7-3 3-7z"/>
            </svg>
            <span>Grounded Claims &amp; Gemma 3 Entailment Shield</span>
          </h3>
          ${gemmaHeaderBadge}
        </div>
        <div class="claims-list">${claimItemsHtml}</div>
      </div>
    `;
  }

  // 3) Slush 2026 Executive Meeting Brief Card
  const brief = analysis.meeting_brief;
  let briefCardHtml = '';
  if (brief && (brief.executive_summary || (brief.talking_points && brief.talking_points.length > 0))) {
    const tpHtml = (brief.talking_points || [])
      .map(
        (tp) => `
        <li>
          <div style="margin-bottom:0.28rem;">${escapeHtml(stripInternalIds(tp.text))}</div>
          ${renderEvidenceChips(tp.evidence_ids, evidenceMap, 5)}
        </li>
      `
      )
      .join('');

    const sqHtml = (brief.smart_questions || [])
      .map(
        (sq) => `
        <li>
          <div style="margin-bottom:0.28rem;">${escapeHtml(stripInternalIds(sq.text))}</div>
          ${renderEvidenceChips(sq.evidence_ids, evidenceMap, 5)}
        </li>
      `
      )
      .join('');

    const warmHtml = (brief.warm_intro_paths || [])
      .map(
        (wp) => `
        <div class="path-step-row" style="cursor:pointer;" data-brief-path-id="${escapeHtml(wp.path_id || '')}">
          <div>
            <span class="badge badge-cala" style="margin-right:0.35rem;">${escapeHtml(wp.hop_count)} Hop${wp.hop_count === 1 ? '' : 's'}</span>
            <span>${escapeHtml(stripInternalIds(wp.summary))}</span>
          </div>
          ${renderEvidenceChips(wp.evidence_ids, evidenceMap, 5)}
        </div>
      `
      )
      .join('');

    const att = brief.attendance_verification;

    briefCardHtml = `
      <div class="intel-card">
        <div class="card-header-row">
          <h3 class="card-title">Slush 2026 Executive Meeting Brief</h3>
          <span class="badge badge-slush">Slush 2026</span>
        </div>

        ${brief.executive_summary ? `<div class="brief-exec-summary">${escapeHtml(stripInternalIds(brief.executive_summary))}</div>` : ''}

        <div class="brief-grid">
          ${
            tpHtml
              ? `<div>
                  <h4 class="brief-subhead">Talking points</h4>
                  <ul class="brief-list">${tpHtml}</ul>
                </div>`
              : ''
          }
          ${
            sqHtml
              ? `<div>
                  <h4 class="brief-subhead">Questions to ask</h4>
                  <ul class="brief-list">${sqHtml}</ul>
                </div>`
              : ''
          }
          ${
            warmHtml
              ? `<div>
                  <h4 class="brief-subhead">Warm introduction routes</h4>
                  <div class="path-steps-list">${warmHtml}</div>
                </div>`
              : ''
          }
        </div>
      </div>
    `;
  }

  // 4) Question-Specific Results Card (Placed first right under summary so relationships lead)
  const resultsCardHtml = renderQuestionResultsCard({
    analysis,
    qid,
    pathsMap,
    nodesMap,
    evidenceMap,
    isolatedPathId,
  });

  containerEl.innerHTML = `
    ${summaryCardHtml}
    ${resultsCardHtml}
    ${briefCardHtml}
  `;

  // Wire interactive events inside Intel Column
  // Path isolation cards (Q1/Q2/Q3/Q4 & warm_intro_paths)
  for (const card of containerEl.querySelectorAll('[data-isolate-path]')) {
    card.addEventListener('click', (e) => {
      if (e.target.closest('button, a')) return;
      const pid = card.getAttribute('data-isolate-path');
      if (pid) onIsolatePath?.(pid);
    });
  }

  for (const row of containerEl.querySelectorAll('[data-brief-path-id]')) {
    row.addEventListener('click', (e) => {
      if (e.target.closest('button, a')) return;
      const pid = row.getAttribute('data-brief-path-id');
      if (pid) onIsolatePath?.(pid);
    });
  }

  // Node inspect buttons
  for (const btn of containerEl.querySelectorAll('[data-inspect-node]')) {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      onInspectNodeById?.(btn.getAttribute('data-inspect-node'));
    });
  }

  // Quick question pivot buttons
  for (const btn of containerEl.querySelectorAll('[data-pivot-qid]')) {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      onPivotQuestion?.({
        question_id: btn.getAttribute('data-pivot-qid'),
        company: btn.getAttribute('data-pivot-company'),
        company_id: btn.getAttribute('data-pivot-company-id'),
      });
    });
  }

  // Q3 Network Category Filter Tabs
  const q3Tabs = containerEl.querySelectorAll('[data-q3-group-tab]');
  if (q3Tabs.length > 0) {
    q3Tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const grp = tab.getAttribute('data-q3-group-tab');
        q3Tabs.forEach((t) => t.classList.toggle('active', t === tab));
        for (const item of containerEl.querySelectorAll('[data-q3-group-item]')) {
          const itemGrp = item.getAttribute('data-q3-group-item');
          item.style.display = grp === 'all' || itemGrp === grp ? '' : 'none';
        }
      });
    });
  }

  // Evidence search & dataset filter
  const evSearchInput = containerEl.querySelector('#evidenceSearchInput');
  const evDatasetFilter = containerEl.querySelector('#evidenceDatasetFilter');
  const applyEvFilter = () => {
    const q = (evSearchInput?.value || '').trim().toLowerCase();
    const ds = evDatasetFilter?.value || 'all';
    for (const card of containerEl.querySelectorAll('.evidence-card')) {
      const cardDs = card.getAttribute('data-ev-dataset') || '';
      const text = card.textContent.toLowerCase();
      const matchDs = ds === 'all' || cardDs === ds;
      const matchText = !q || text.includes(q);
      card.style.display = matchDs && matchText ? '' : 'none';
    }
  };
  evSearchInput?.addEventListener('input', applyEvFilter);
  evDatasetFilter?.addEventListener('change', applyEvFilter);
}

function renderQuestionResultsCard({ analysis, qid, pathsMap, nodesMap, evidenceMap, isolatedPathId }) {
  const results = Array.isArray(analysis.results) ? analysis.results : [];
  const cov = analysis.coverage || {};
  const hopSel = analysis.hop_selection || cov.hop_selection || {};
  const selectedHops = hopSel.selected_hops ?? cov.max_hops ?? 4;
  const maxAllowedHops = hopSel.max_allowed_hops ?? 8;

  if (analysis.status === 'needs_resolution' || analysis.status === 'not_found') {
    return '';
  }

  // Q1 & Q2: Multi-Hop Ranked Path Cards
  if (qid === 'person_to_company' || qid === 'company_to_company') {
    if (results.length === 0 || analysis.status === 'insufficient_data') {
      const canExpandHops = Number(selectedHops) < Number(maxAllowedHops);
      return `
        <div class="intel-card">
          <div class="card-header-row">
            <h3 class="card-title">Relationship paths</h3>
            <span class="badge badge-warn">0 paths</span>
          </div>
          <div class="honest-empty-banner">
            <div class="honest-empty-title">No verified relationship path within ${escapeHtml(selectedHops)} hop${Number(selectedHops) === 1 ? '' : 's'}</div>
            <p style="font-size:0.84rem;color:var(--text-secondary);margin:0 0 0.45rem;">
              ${escapeHtml(analysis.summary || `No verified professional path was found within ${selectedHops} steps.`)}
            </p>
            ${
              canExpandHops
                ? `<div style="font-size:0.8rem;color:var(--accent);margin-bottom:0.4rem;">Search depth is set to ${escapeHtml(selectedHops)} hop${Number(selectedHops) === 1 ? '' : 's'}. Increase Search depth to Suggested or Max (${escapeHtml(maxAllowedHops)}) above to check deeper connections.</div>`
                : ''
            }
            <div style="font-size:0.78rem;color:var(--text-muted);">
              Generic event co-attendance and shared industry categories are excluded so two companies merely attending Slush are never falsely linked
            </div>
          </div>
        </div>
      `;
    }

    const cardsHtml = results
      .map((res) => {
        const pathObj = pathsMap.get(res.path_id);
        const relations = Array.isArray(pathObj?.relations) ? pathObj.relations : [];
        const hops = pathObj?.hop_count ?? relations.length ?? 1;
        const isIsolated = isolatedPathId === res.path_id;

        const stepsHtml = relations
          .map((rel) => {
            const fromName = nodesMap.get(rel.from_id)?.name || 'Source';
            const toName = nodesMap.get(rel.to_id)?.name || 'Target';
            const isRev = rel.traversal === 'reverse';
            return `
              <div class="path-step-row">
                <div>
                  <div style="display:flex;align-items:center;gap:0.35rem;flex-wrap:wrap;margin-bottom:2px;">
                    <span class="badge badge-cala">${escapeHtml(humanizePredicate(rel.predicate))}</span>
                    <span class="badge badge-neutral" title="Traversal direction vs assertion direction">${isRev ? '↶ Reverse Traversal' : '↷ Forward'}</span>
                    <span class="badge badge-neutral">${escapeHtml(rel.temporal_status || 'undated')}</span>
                  </div>
                  <div style="color:var(--text-primary);margin-top:2px;">
                    ${escapeHtml(stripInternalIds(rel.statement) || `${fromName} → ${toName}`)}
                  </div>
                </div>
                ${renderEvidenceChips(rel.evidence_ids, evidenceMap, 4)}
              </div>
            `;
          })
          .join('');

        const reasonsHtml = (res.rank_reasons || [])
          .map((r) => `<span class="reason-tag">${escapeHtml(r)}</span>`)
          .join('');

        return `
          <div class="result-card ${isIsolated ? 'isolated' : ''}" data-isolate-path="${escapeHtml(res.path_id || '')}">
            <div class="result-top-row">
              <div style="display:flex;align-items:center;gap:0.45rem;flex-wrap:wrap;">
                <span class="rank-pill">Rank #${escapeHtml(res.rank)}</span>
                <span class="badge badge-dual">${escapeHtml(hops)} Hop${hops === 1 ? '' : 's'}</span>
                <span style="font-size:0.74rem;color:var(--text-muted);">${isIsolated ? '● Path Isolated on Graph' : 'Click card to isolate path'}</span>
              </div>
            </div>
            <div style="font-size:0.86rem;font-weight:600;color:var(--text-primary);">${escapeHtml(stripInternalIds(res.explanation) || '')}</div>
            ${stepsHtml ? `<div class="path-steps-list">${stepsHtml}</div>` : ''}
            ${reasonsHtml ? `<div class="rank-reasons-row">${reasonsHtml}</div>` : ''}
          </div>
        `;
      })
      .join('');

    return `
      <div class="intel-card">
        <div class="card-header-row">
          <h3 class="card-title">Ranked Multi-Hop Paths (${results.length})</h3>
          <span style="font-size:0.73rem;color:var(--text-muted);">Click any path card to isolate on graph</span>
        </div>
        <div class="results-stack">${cardsHtml}</div>
      </div>
    `;
  }

  // Q3: Surrounded Company Network (Grouped Tabs)
  if (qid === 'company_network') {
    const groupCounts = {
      all: results.length,
      direct_people: results.filter((r) => r.group === 'direct_people').length,
      investors: results.filter((r) => r.group === 'investors').length,
      direct_companies: results.filter((r) => r.group === 'direct_companies').length,
      indirect_connections: results.filter((r) => r.group === 'indirect_connections').length,
    };

    const groupLabels = {
      direct_people: 'Direct People',
      investors: 'Investors',
      direct_companies: 'Direct Companies',
      indirect_connections: 'Indirect ≥2-Hop',
    };

    const itemsHtml = results
      .map((res) => {
        const ent = res.entity || {};
        const fullNode = nodesMap.get(ent.id) || ent;
        const firstPathId = res.path_ids?.[0] || '';
        const isIsolated = firstPathId && isolatedPathId === firstPathId;
        const hopDist = res.min_hop_distance;
        return `
          <div class="result-card ${isIsolated ? 'isolated' : ''}" data-q3-group-item="${escapeHtml(res.group || 'other')}" data-isolate-path="${escapeHtml(firstPathId)}">
            <div class="result-top-row">
              <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                <span class="rank-pill">#${escapeHtml(res.rank)}</span>
                <strong style="font-family:var(--font-display);font-size:0.92rem;">${escapeHtml(ent.name || 'Entity')}</strong>
                <span class="badge badge-ai">${escapeHtml(groupLabels[res.group] || res.group || 'Network')}</span>
                ${hopDist ? `<span class="badge badge-dual">${escapeHtml(hopDist)} Hop${Number(hopDist) === 1 ? '' : 's'}</span>` : ''}
                ${renderOriginBadges(fullNode)}
              </div>
              <div style="display:flex;gap:0.35rem;">
                <button type="button" class="btn-ghost-sm" data-inspect-node="${escapeHtml(ent.id)}">Inspect</button>
                ${
                  ent.entity_type !== 'Person'
                    ? `<button type="button" class="btn-ghost-sm" data-pivot-qid="company_representatives" data-pivot-company="${escapeHtml(ent.name)}" data-pivot-company-id="${escapeHtml(ent.id)}">Slush Brief</button>`
                    : ''
                }
              </div>
            </div>
            <div style="font-size:0.83rem;color:var(--text-secondary);margin-bottom:0.4rem;">${escapeHtml(stripInternalIds(res.explanation) || '')}</div>
            <div style="display:flex;align-items:center;justify-content:space-between;gap:0.4rem;flex-wrap:wrap;">
              <div class="rank-reasons-row" style="margin-top:0;">
                ${(res.rank_reasons || []).map((r) => `<span class="reason-tag">${escapeHtml(r)}</span>`).join('')}
              </div>
              ${renderEvidenceChips(ent.evidence_ids, evidenceMap, 4)}
            </div>
          </div>
        `;
      })
      .join('');

    return `
      <div class="intel-card">
        <div class="card-header-row">
          <h3 class="card-title">${escapeHtml(selectedHops)}-Hop Professional Ecosystem (${results.length})</h3>
          <div class="preset-filters">
            <button type="button" class="filter-chip active" data-q3-group-tab="all">All (${groupCounts.all})</button>
            <button type="button" class="filter-chip" data-q3-group-tab="direct_people">People (${groupCounts.direct_people})</button>
            <button type="button" class="filter-chip" data-q3-group-tab="investors">Investors (${groupCounts.investors})</button>
            <button type="button" class="filter-chip" data-q3-group-tab="direct_companies">Companies (${groupCounts.direct_companies})</button>
            <button type="button" class="filter-chip" data-q3-group-tab="indirect_connections">Indirect ≥2-Hop (${groupCounts.indirect_connections})</button>
          </div>
        </div>
        <div class="results-stack">
          ${itemsHtml || `<div style="color:var(--text-muted);font-size:0.82rem;">No surrounding professional connections documented in snapshot.</div>`}
        </div>
      </div>
    `;
  }

  // Q4: Slush Representatives (Named Participation Verified vs Affiliated Attendance Unverified)
  const unverifiedList = Array.isArray(analysis.attendance_unverified)
    ? analysis.attendance_unverified
    : Array.isArray(analysis.other_affiliated_people)
      ? analysis.other_affiliated_people
      : [];

  const verifiedCardsHtml = results
    .map((res) => {
      const person = res.person || {};
      const p = person.profile || {};
      const topics = Array.isArray(p.professional_topics) ? p.professional_topics : [];
      const workEntries = Array.isArray(p.work_experience?.entries) ? p.work_experience.entries : [];
      const firstPathId = res.path_ids?.[0] || '';
      const isIsolated = firstPathId && isolatedPathId === firstPathId;

      return `
        <div class="result-card ${isIsolated ? 'isolated' : ''}" data-isolate-path="${escapeHtml(firstPathId)}">
          <div class="result-top-row">
            <div style="display:flex;align-items:center;gap:0.42rem;flex-wrap:wrap;">
              <span class="rank-pill">Rep #${escapeHtml(res.rank)}</span>
              <strong style="font-family:var(--font-display);font-size:0.98rem;">${escapeHtml(person.name || 'Representative')}</strong>
              ${renderParticipationBadges(res.attendance || person.participation)}
              ${renderOriginBadges(person)}
            </div>
            <button type="button" class="btn-ghost-sm" data-inspect-node="${escapeHtml(person.id)}">Profile &amp; Live Cala</button>
          </div>

          ${p.job_title ? `<div style="font-size:0.8rem;font-weight:600;color:var(--cala-bright);margin-bottom:0.3rem;">${escapeHtml(p.job_title)}</div>` : ''}
          <div style="font-size:0.83rem;color:var(--text-primary);margin-bottom:0.4rem;">${escapeHtml(stripInternalIds(res.explanation) || '')}</div>
          ${p.biography ? `<p style="font-size:0.79rem;color:var(--text-secondary);margin:0 0 0.5rem;line-height:1.48;">${escapeHtml(p.biography)}</p>` : ''}

          ${
            topics.length > 0
              ? `<div style="display:flex;gap:0.28rem;flex-wrap:wrap;margin-bottom:0.45rem;">
                  ${topics.map((t) => `<span class="badge badge-ai">${escapeHtml(t)}</span>`).join('')}
                </div>`
              : ''
          }

          ${
            workEntries.length > 0
              ? `<div style="margin-bottom:0.45rem;display:flex;flex-direction:column;gap:0.25rem;">
                  ${workEntries
                    .slice(0, 3)
                    .map((w) => {
                      const u = safeExternalUrl(w.source_url);
                      return `<div style="font-size:0.74rem;color:var(--text-muted);">• <strong>${escapeHtml(w.role || 'Role')}</strong> at ${escapeHtml(w.organization || '')} ${u ? `<a href="${escapeHtml(u)}" target="_blank" rel="noopener noreferrer">[Source ↗]</a>` : ''}</div>`;
                    })
                    .join('')}
                </div>`
              : ''
          }

          ${
            res.contact_interpretation
              ? `<div style="font-size:0.76rem;color:var(--text-secondary);margin-bottom:0.45rem;">${escapeHtml(res.contact_interpretation)}</div>`
              : ''
          }

          <div style="display:flex;align-items:center;justify-content:space-between;gap:0.4rem;flex-wrap:wrap;">
            <div class="rank-reasons-row" style="margin-top:0;">
              ${(res.rank_reasons || []).map((r) => `<span class="reason-tag">${escapeHtml(r)}</span>`).join('')}
            </div>
            ${renderEvidenceChips(person.evidence_ids, evidenceMap, 5)}
          </div>
        </div>
      `;
    })
    .join('');

  const unverifiedHtml =
    unverifiedList.length > 0
      ? `
        <div class="unverified-affiliates-box">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.4rem;">
            <strong style="font-family:var(--font-display);font-size:0.86rem;color:var(--warn-bright);">
              Affiliated People — Individual Slush 2026 Attendance Unverified (${unverifiedList.length})
            </strong>
            <span class="badge badge-warn">Company Listing ≠ Person Attendance</span>
          </div>
          <p style="font-size:0.75rem;color:var(--text-muted);margin:0 0 0.55rem;">
            These people have documented corporate/founder/board ties to the company, but no named Slush 2026 speaker/attendee record in the snapshot.
          </p>
          <div style="display:flex;flex-direction:column;gap:0.4rem;">
            ${unverifiedList
              .map(
                (u) => `
              <div class="path-step-row">
                <div style="display:flex;align-items:center;gap:0.45rem;flex-wrap:wrap;">
                  <strong>${escapeHtml(u.name || 'Person')}</strong>
                  ${renderOriginBadges(u)}
                  ${renderCompletenessBadge(u.record_completeness)}
                </div>
                <div style="display:flex;align-items:center;gap:0.35rem;">
                  ${renderEvidenceChips(u.evidence_ids, evidenceMap, 3)}
                  <button type="button" class="btn-ghost-sm" data-inspect-node="${escapeHtml(u.id)}">Inspect</button>
                </div>
              </div>
            `
              )
              .join('')}
          </div>
        </div>
      `
      : '';

  return `
    <div class="intel-card">
      <div class="card-header-row">
        <h3 class="card-title">Approaching at Slush — Named Participation Verified (${results.length})</h3>
        <span class="badge badge-slush">Physical Check-In Unverified</span>
      </div>
      <div class="results-stack">
        ${
          verifiedCardsHtml ||
          `<div class="honest-empty-banner">
            <div class="honest-empty-title">No named Slush 2026 representatives found</div>
            <div style="font-size:0.82rem;color:var(--text-secondary);">Even when a company is listed at Slush, Comare di Slush only surfaces people with individual participation evidence.</div>
          </div>`
        }
      </div>
      ${
        Array.isArray(analysis.extended_network_representatives) && analysis.extended_network_representatives.length > 0
          ? `
            <div class="unverified-affiliates-box" style="border-color:var(--cala-border);background:rgba(6,182,212,0.05);">
              <div style="display:flex;align-items:center;justify-content:space-between;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.4rem;">
                <strong style="font-family:var(--font-display);font-size:0.86rem;color:var(--cala-bright);">
                  Extended Multi-Hop Slush 2026 Bridges (${analysis.extended_network_representatives.length}) — Up to ${escapeHtml(selectedHops)} Hops
                </strong>
                <span class="badge badge-cala">Indirect Warm-Bridge Participants</span>
              </div>
              <p style="font-size:0.75rem;color:var(--text-muted);margin:0 0 0.55rem;">
                These Slush 2026 participants are connected via 2–${escapeHtml(selectedHops)} documented professional steps (not direct employees/affiliates of the target company).
              </p>
              <div style="display:flex;flex-direction:column;gap:0.45rem;">
                ${analysis.extended_network_representatives
                  .map((ext) => {
                    const ep = ext.person || {};
                    const ePathId = ext.path_ids?.[0] || '';
                    const eIsolated = ePathId && isolatedPathId === ePathId;
                    return `
                      <div class="result-card ${eIsolated ? 'isolated' : ''}" style="padding:0.65rem 0.8rem;" data-isolate-path="${escapeHtml(ePathId)}">
                        <div class="result-top-row">
                          <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                            <span class="badge badge-dual">${escapeHtml(ext.hop_distance || 2)} Hops</span>
                            <strong>${escapeHtml(ep.name || 'Representative')}</strong>
                            ${renderParticipationBadges(ext.attendance || ep.participation)}
                            ${renderOriginBadges(ep)}
                          </div>
                          <button type="button" class="btn-ghost-sm" data-inspect-node="${escapeHtml(ep.id)}">Profile &amp; Live Cala</button>
                        </div>
                        <div style="font-size:0.8rem;color:var(--text-primary);margin-bottom:0.25rem;">${escapeHtml(stripInternalIds(ext.explanation) || '')}</div>
                        ${
                          ext.contact_interpretation
                            ? `<div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:0.25rem;">${escapeHtml(ext.contact_interpretation)}</div>`
                            : ''
                        }
                        <div style="display:flex;align-items:center;justify-content:space-between;gap:0.4rem;flex-wrap:wrap;">
                          <div class="rank-reasons-row" style="margin-top:0;">
                            ${(ext.rank_reasons || []).map((r) => `<span class="reason-tag">${escapeHtml(r)}</span>`).join('')}
                          </div>
                          ${renderEvidenceChips(ep.evidence_ids, evidenceMap, 4)}
                        </div>
                      </div>
                    `;
                  })
                  .join('')}
              </div>
            </div>
          `
          : ''
      }
      ${unverifiedHtml}
    </div>
  `;
}

/* ==========================================================================
   5. Evidence & Provenance Explorer Card + Scroll Highlighter
   ========================================================================== */

function renderEvidenceExplorerCard(evidenceMap) {
  const items = [...evidenceMap.values()];

  const itemsHtml = items
    .map((ev) => {
      const ds = ev.dataset || 'snapshot';
      const isSlush = ds.startsWith('slush');
      const docs = Array.isArray(ev.source_documents) ? ev.source_documents : [];

      const docsHtml = docs
        .map(
          (doc) => `
          <div style="margin-top:0.35rem;">
            ${renderSourceDocumentBadge(doc)}
            ${doc.evidence ? `<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.22rem;padding-left:0.5rem;border-left:2px solid rgba(34,211,238,0.35);">“${escapeHtml(doc.evidence)}”</div>` : ''}
          </div>
        `
        )
        .join('');

      return `
        <div class="evidence-card" data-ev-dataset="${escapeHtml(ds)}">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:0.5rem;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
              <span class="badge ${isSlush ? 'badge-slush' : 'badge-cala'}">${escapeHtml(humanizeDatasetLabel(ds))}</span>
            </div>
          </div>
          ${docsHtml || `<div style="font-size:0.73rem;color:var(--text-muted);margin-top:0.25rem;">Primary dataset record assertion preserved in snapshot.</div>`}
          ${
            ev.record
              ? `<details style="margin-top:0.4rem;font-size:0.72rem;color:var(--text-muted);">
                  <summary style="cursor:pointer;">Raw Record Snapshot</summary>
                  <pre class="code-block" style="margin-top:0.35rem;max-height:180px;">${escapeHtml(JSON.stringify(ev.record, null, 2))}</pre>
                </details>`
              : ''
          }
        </div>
      `;
    })
    .join('');

  return `
    <div class="intel-card" id="evidenceExplorerSection">
      <div class="card-header-row">
        <h3 class="card-title">
          <span>📚 Verified Provenance &amp; Evidence Ledger (${items.length})</span>
        </h3>
        <span class="badge badge-cala">100% Referential Integrity</span>
      </div>
      <div class="evidence-search-row">
        <input
          type="text"
          id="evidenceSearchInput"
          class="smart-input"
          style="flex:1 1 200px;padding:0.42rem 0.7rem;font-size:0.78rem;"
          placeholder="Filter by publisher, domain, URL, or quote..."
        />
        <select id="evidenceDatasetFilter" class="styled-select">
          <option value="all">All Datasets (${items.length})</option>
          <option value="cala">Cala Edges</option>
          <option value="cala_company_dossier">Cala Company Dossier</option>
          <option value="cala_people_connectors">Cala Speakers &amp; Connectors</option>
          <option value="cala_roster">Cala Slush Roster</option>
          <option value="cala_shared_bridges">Cala Shared Bridges</option>
          <option value="slush_people">Slush People</option>
          <option value="slush_companies">Slush Companies</option>
        </select>
      </div>
      <div class="evidence-list">
        ${itemsHtml || `<div style="font-size:0.78rem;color:var(--text-muted);">No evidence records attached to this state.</div>`}
      </div>
    </div>
  `;
}

export function scrollToAndFlashEvidence(evId) {
  if (!evId) return;
  const el = document.getElementById(`evidence-card-${evId}`);
  if (!el) return;
  el.style.display = '';
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.remove('flash-highlight');
  void el.offsetWidth;
  el.classList.add('flash-highlight');
  setTimeout(() => el.classList.remove('flash-highlight'), 2400);
}
