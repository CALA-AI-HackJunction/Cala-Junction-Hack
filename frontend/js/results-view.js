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
} from './utils.js';

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
        source: 'Starting entity (source)',
        target: 'Target entity (target)',
        company: 'Target company (company)',
      };
      const candidates = Array.isArray(slotData.candidates) ? slotData.candidates : [];

      if (candidates.length === 0) {
        return `
          <div class="disambig-slot-block">
            <div class="disambig-slot-title">${escapeHtml(slotLabelMap[slotName] || slotName)} — Query: “${escapeHtml(slotData.query || '')}”</div>
            <div class="honest-empty-banner">
              <div class="honest-empty-title">No matching entity in loaded snapshot</div>
              <div style="font-size:13px;color:var(--text-secondary);">
                ${escapeHtml(slotData.reason || 'This name was not found in the reconciled Cala and Slush 2026 snapshot. Try typing in the search input above for suggestions.')}
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
                <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
                  <strong style="font-size:15px;color:var(--text-primary);">${escapeHtml(cand.name)}</strong>
                  <div style="display:flex;gap:4px;flex-wrap:wrap;">
                    ${renderOriginBadges(cand)}
                    ${renderCompletenessBadge(cand.record_completeness)}
                  </div>
                </div>
                <div class="candidate-id" style="margin-bottom:8px;">ID: ${escapeHtml(cand.id)}</div>
                <div class="candidate-meta">
                  ${renderParticipationBadges(cand.participation) ? `<div>${renderParticipationBadges(cand.participation)}</div>` : ''}
                  ${ctx.job_title ? `<div><strong>Role:</strong> ${escapeHtml(ctx.job_title)}</div>` : ''}
                  ${ctx.location_raw ? `<div><strong>Location:</strong> ${escapeHtml(ctx.location_raw)}</div>` : ''}
                  ${websiteUrl ? `<div><strong>Website:</strong> <a href="${escapeHtml(websiteUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(websiteUrl)}</a></div>` : ''}
                  ${affiliations.length > 0 ? `<div><strong>Affiliations:</strong> ${escapeHtml(affiliations.join(', '))}</div>` : ''}
                  ${degree !== undefined ? `<div><strong>Verified bridges:</strong> ${escapeHtml(degree)} edge${degree === 1 ? '' : 's'}</div>` : ''}
                  ${Array.isArray(cand.evidence_ids) && cand.evidence_ids.length > 0 ? `<div style="margin-top:4px;">${renderEvidenceChips(cand.evidence_ids, evidenceMap, 4)}</div>` : ''}
                </div>
              </div>
              <button
                type="button"
                class="btn-select-candidate"
                data-select-slot="${escapeHtml(slotName)}"
                data-select-id="${escapeHtml(cand.id)}"
                data-select-name="${escapeHtml(cand.name)}"
              >
                Use this record
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
        <h3 class="disambig-title">Multiple records match this name</h3>
        <p class="disambig-sub">
          ${escapeHtml(analysis.summary || 'Distinct records share this name across the Cala and Slush snapshots. Select the canonical entity ID below to run a verified search.')}
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
    ok: { text: 'Live Cala /v1 verified', cls: 'badge-cala' },
    payment_required: { text: 'HTTP 402 · Insufficient balance', cls: 'badge-warn' },
    unconfigured: { text: 'CALA_API_KEY unconfigured · Snapshot only', cls: 'badge-neutral' },
    not_mapped: { text: 'Unmapped in Cala /v1', cls: 'badge-neutral' },
    rate_limited: { text: 'HTTP 429 · Rate limited', cls: 'badge-warn' },
    timeout: { text: 'Timeout · Clean halt', cls: 'badge-warn' },
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
          ${sourcesHtml ? `<div style="display:flex;gap:4px;flex-wrap:wrap;">${sourcesHtml}</div>` : ''}
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
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
            <span class="badge badge-cala">${escapeHtml(humanizePredicate(r.predicate))}</span>
            <span style="font-size:12px;color:var(--text-muted);">(${escapeHtml(r.direction || 'linked')})</span>
            <strong>${escapeHtml(r.peer_name || r.peer_cala_id || 'Entity')}</strong>
          </div>
          ${sourcesHtml ? `<div style="display:flex;gap:4px;flex-wrap:wrap;">${sourcesHtml}</div>` : ''}
        </div>
      `;
    })
    .join('');

  const investorMatchHtml = investorMatch
    ? `
      <div style="margin-top:8px;padding:8px 12px;border-radius:4px;background:var(--cala-bg);border:1px solid var(--cala-border);font-size:12px;">
        <div style="font-weight:500;color:var(--cala-primary);margin-bottom:4px;">Cala audit registry match (<code>${escapeHtml(investorMatch.namespace || 'cala_verified_investor_match')}</code>)</div>
        <div><strong>${escapeHtml(investorMatch.cala_name || '')}</strong> · Cala UUID: <code>${escapeHtml(investorMatch.cala_id || '')}</code> ${investorMatch.country ? `· ${escapeHtml(investorMatch.country)}` : ''}</div>
      </div>
    `
    : '';

  return `
    <div class="cala-live-box ${isWarnHalt && !isOk ? 'warn-halt' : ''}">
      <div class="cala-live-header">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span class="badge ${badgeMeta.cls}">${escapeHtml(badgeMeta.text)}</span>
          <code style="font-size:12px;color:var(--text-muted);">namespace: ${escapeHtml(enrichPayload.namespace || 'cala_live_enrichment')}</code>
        </div>
        ${enrichPayload.elapsed_ms !== undefined ? `<span class="mono" style="font-size:12px;color:var(--text-muted);">${formatMs(enrichPayload.elapsed_ms)}${enrichPayload.cached ? ' · cached' : ''}</span>` : ''}
      </div>
      ${enrichPayload.cala_uuid ? `<div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">Cala entity UUID: <code>${escapeHtml(enrichPayload.cala_uuid)}</code></div>` : ''}
      <div style="font-size:13px;color:var(--text-secondary);margin-bottom:4px;">
        ${escapeHtml(enrichPayload.message || 'Isolated from snapshot hop counts to preserve deterministic reproducibility.')}
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
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
          <span class="badge badge-neutral">${escapeHtml(node.entity_type || 'Entity')}</span>
          ${renderOriginBadges(node)}
          ${renderCompletenessBadge(node.record_completeness)}
        </div>
        <h4 class="inspector-title">${escapeHtml(node.name || node.id)}</h4>
        <div class="mono" style="font-size:12px;color:var(--text-muted);margin-top:4px;">${escapeHtml(node.id)}</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <button type="button" class="btn-ghost-sm" id="btnLiveCalaEnrichNode">
          Query Cala /v1
        </button>
        ${
          node.entity_type !== 'Person'
            ? `<button type="button" class="btn-ghost-sm" id="btnPivotQ4Node" title="Check Slush 2026 representatives">Slush dossier (Q4)</button>`
            : ''
        }
        <button type="button" class="btn-ghost-sm" id="btnCloseInspector">Close</button>
      </div>
    </div>

    ${
      Array.isArray(node.participation) && node.participation.length > 0
        ? `<div style="margin-bottom:8px;">${renderParticipationBadges(node.participation)}</div>`
        : ''
    }

    ${p.job_title ? `<div style="font-size:13px;color:var(--text-primary);font-weight:500;margin-bottom:4px;">${escapeHtml(p.job_title)}</div>` : ''}
    ${p.biography || p.description ? `<p style="font-size:13px;color:var(--text-secondary);margin:0 0 12px;line-height:20px;">${escapeHtml(p.biography || p.description)}</p>` : ''}

    <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:13px;margin-bottom:8px;">
      ${websiteUrl ? `<a href="${escapeHtml(websiteUrl)}" target="_blank" rel="noopener noreferrer">Website ↗</a>` : ''}
      ${linkedinUrl ? `<a href="${escapeHtml(linkedinUrl)}" target="_blank" rel="noopener noreferrer">LinkedIn ↗</a>` : ''}
      ${p.location_raw ? `<span style="color:var(--text-muted);">${escapeHtml(p.location_raw)}</span>` : ''}
    </div>

    ${
      topics.length > 0
        ? `<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:12px;">
            ${topics.map((t) => `<span class="badge badge-ai">${escapeHtml(t)}</span>`).join('')}
          </div>`
        : ''
    }

    ${
      workEntries.length > 0
        ? `<div style="margin-bottom:12px;">
            <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">Sourced work history</div>
            ${workEntries
              .map((w) => {
                const provBadges = (w.provenance || []).map((pr) => renderSourceDocumentBadge(pr)).join(' ');
                return `
                  <div style="padding:8px 12px;background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:4px;margin-bottom:4px;font-size:13px;">
                    <div><strong>${escapeHtml(w.role || w.title || 'Role')}</strong> · ${escapeHtml(w.organization || 'Organization')}</div>
                    ${provBadges ? `<div style="margin-top:4px;">${provBadges}</div>` : ''}
                  </div>
                `;
              })
              .join('')}
          </div>`
        : ''
    }

    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;padding-top:8px;border-top:1px solid var(--border-subtle);font-size:12px;color:var(--text-muted);">
      <div>
        ${calaIds.length > 0 ? `<span>Cala UUID: <code>${escapeHtml(calaIds[0])}</code></span>` : ''}
        ${slushIds.length > 0 ? `<span style="margin-left:8px;">Slush ID: <code>${escapeHtml(slushIds[0])}</code></span>` : ''}
      </div>
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
      enrichBtn.textContent = 'Query Cala /v1';
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
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
          <span class="badge badge-cala">${escapeHtml(humanizePredicate(edge.type))}</span>
          ${renderOriginBadges(edge)}
          <span class="badge badge-neutral">Temporal: ${escapeHtml(edge.temporal_status || 'undated')}</span>
        </div>
        <h4 class="inspector-title">
          ${escapeHtml(srcNode?.name || edge.source)} <span style="color:var(--text-muted);">→</span> ${escapeHtml(tgtNode?.name || edge.target)}
        </h4>
        <div class="mono" style="font-size:12px;color:var(--text-muted);margin-top:4px;">${escapeHtml(edge.id)} · Strength: ${escapeHtml(edge.evidence_strength || 'documented')}</div>
      </div>
      <button type="button" class="btn-ghost-sm" id="btnCloseEdgeInspector">Close</button>
    </div>

    ${
      propsEntries.length > 0
        ? `<div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">
            ${propsEntries.map(([k, v]) => `<span class="badge badge-neutral" style="margin-right:4px;">${escapeHtml(k)}: ${escapeHtml(String(v))}</span>`).join('')}
          </div>`
        : ''
    }

    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;padding-top:8px;border-top:1px solid var(--border-subtle);">
      <span style="font-size:12px;color:var(--text-muted);">Factual assertion direction preserved regardless of search traversal</span>
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
        <span class="section-eyebrow">Snapshot synthesis</span>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          ${renderStatusBadge(analysis.status)}
          ${cov.max_hops ? `<span class="badge badge-neutral">Max ${escapeHtml(cov.max_hops)} hops</span>` : ''}
          ${cov.visited_nodes !== undefined ? `<span class="badge badge-neutral">${escapeHtml(cov.visited_nodes)} visited nodes</span>` : ''}
        </div>
      </div>
      <h2 class="summary-headline">${escapeHtml(analysis.summary || 'Analysis ready')}</h2>
      ${
        analysis.interpretation
          ? `<div class="epistemic-note">${escapeHtml(analysis.interpretation)}</div>`
          : ''
      }
      ${inlineEnrichHtml}
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
          ${pass ? 'Gemma 3 entailment pass' : 'Gemma audit flagged'} · ${escapeHtml(gemmaSum.supported_claims ?? claims.length)}/${escapeHtml(gemmaSum.audited_claims ?? claims.length)} (${escapeHtml(gemmaSum.model || 'gemma-3')})
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
              ${isSup ? 'Gemma verified' : escapeHtml(audit.verdict)}
            </span>
          `;
        }
        return `
          <div class="claim-item">
            <div class="claim-text">${escapeHtml(c.text)}</div>
            <div class="claim-footer">
              ${renderEvidenceChips(c.evidence_ids, evidenceMap, 6)}
              ${auditPill}
            </div>
            ${audit?.note ? `<div class="gemma-note"><strong>Gemma 3 audit:</strong> ${escapeHtml(audit.note)}</div>` : ''}
          </div>
        `;
      })
      .join('');

    claimsCardHtml = `
      <div class="intel-card ai-accent">
        <div class="card-header-row">
          <h3 class="card-title">Grounded claims &amp; Gemma 3 entailment audit</h3>
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
          <div style="margin-bottom:4px;">${escapeHtml(tp.text)}</div>
          ${renderEvidenceChips(tp.evidence_ids, evidenceMap, 5)}
        </li>
      `
      )
      .join('');

    const sqHtml = (brief.smart_questions || [])
      .map(
        (sq) => `
        <li>
          <div style="margin-bottom:4px;">${escapeHtml(sq.text)}</div>
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
            <span class="badge badge-cala" style="margin-right:8px;">${escapeHtml(wp.hop_count)} hop${wp.hop_count === 1 ? '' : 's'}</span>
            <span>${escapeHtml(wp.summary)}</span>
          </div>
          ${renderEvidenceChips(wp.evidence_ids, evidenceMap, 3)}
        </div>
      `
      )
      .join('');

    const att = brief.attendance_verification;

    briefCardHtml = `
      <div class="intel-card slush-brief-accent">
        <div class="card-header-row">
          <h3 class="card-title">Slush 2026 Executive Meeting Brief</h3>
          <span class="badge badge-slush">Composer: ${escapeHtml(brief.model || brief.composer || 'Grounded')}</span>
        </div>

        ${brief.executive_summary ? `<div class="brief-exec-summary">${escapeHtml(brief.executive_summary)}</div>` : ''}

        <div class="brief-grid">
          ${
            tpHtml
              ? `<div>
                  <h4 class="brief-subhead">Verified talking points</h4>
                  <ul class="brief-list">${tpHtml}</ul>
                </div>`
              : ''
          }
          ${
            sqHtml
              ? `<div>
                  <h4 class="brief-subhead">Questions to ask at Slush</h4>
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

        ${
          att
            ? `<div class="attendance-callout">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
                  <strong style="color:var(--text-primary);">Attendance verification (${escapeHtml(att.status || 'partial_snapshot')})</strong>
                  ${renderEvidenceChips(att.evidence_ids, evidenceMap, 4)}
                </div>
                <div>${escapeHtml(att.note || 'Physical event check-in and meeting availability are not assumed from directory listings.')}</div>
              </div>`
            : ''
        }
      </div>
    `;
  }

  // 4) Question-Specific Results Card
  const resultsCardHtml = renderQuestionResultsCard({
    analysis,
    qid,
    pathsMap,
    nodesMap,
    evidenceMap,
    isolatedPathId,
  });

  // 5) Evidence & Provenance Explorer Card
  const evidenceCardHtml = renderEvidenceExplorerCard(evidenceMap);

  containerEl.innerHTML = `
    ${summaryCardHtml}
    ${claimsCardHtml}
    ${briefCardHtml}
    ${resultsCardHtml}
    ${evidenceCardHtml}
  `;

  // Wire interactive events inside Intel Column
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

  for (const btn of containerEl.querySelectorAll('[data-inspect-node]')) {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      onInspectNodeById?.(btn.getAttribute('data-inspect-node'));
    });
  }

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

  if (analysis.status === 'needs_resolution' || analysis.status === 'not_found') {
    return '';
  }

  // Q1 & Q2: Multi-Hop Ranked Path Cards
  if (qid === 'person_to_company' || qid === 'company_to_company') {
    if (results.length === 0 || analysis.status === 'insufficient_data') {
      return `
        <div class="intel-card">
          <div class="card-header-row">
            <h3 class="card-title">Ranked professional paths</h3>
            <span class="badge badge-warn">0 supported bridges</span>
          </div>
          <div class="honest-empty-banner">
            <div class="honest-empty-title">No supported path within 4 hops</div>
            <p style="font-size:13px;color:var(--text-secondary);margin:0 0 8px;">
              ${escapeHtml(analysis.summary || 'No supported professional path was found in the loaded snapshot within 4 steps.')}
            </p>
            <div style="font-size:12px;color:var(--text-muted);">
              <strong>Methodology:</strong> Unicorn Radar excludes 2,990 generic Slush event co-attendance links (<code>PARTICIPATES_IN_EVENT</code>), shared industry tags (<code>OPERATES_IN_INDUSTRY</code>), and unattributed edges so two companies attending Slush 2026 are not linked without a professional bridge.
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
            const fromName = nodesMap.get(rel.from_id)?.name || rel.from_id;
            const toName = nodesMap.get(rel.to_id)?.name || rel.to_id;
            const isRev = rel.traversal === 'reverse';
            return `
              <div class="path-step-row">
                <div>
                  <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px;">
                    <span class="badge badge-cala">${escapeHtml(humanizePredicate(rel.predicate))}</span>
                    <span class="badge badge-neutral" title="Traversal direction vs assertion direction">${isRev ? 'Reverse traversal' : 'Forward'}</span>
                    <span class="badge badge-neutral">${escapeHtml(rel.temporal_status || 'undated')}</span>
                  </div>
                  <div style="color:var(--text-primary);">
                    ${escapeHtml(rel.statement || `${fromName} → ${toName}`)}
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
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                <span class="rank-pill">Rank #${escapeHtml(res.rank)}</span>
                <span class="badge badge-dual">${escapeHtml(hops)} hop${hops === 1 ? '' : 's'}</span>
                <span style="font-size:12px;color:var(--text-muted);">${isIsolated ? 'Isolated on graph' : 'Select card to isolate path'}</span>
              </div>
              <span class="mono" style="font-size:12px;color:var(--text-muted);">${escapeHtml(res.path_id || '')}</span>
            </div>
            <div style="font-size:14px;font-weight:500;color:var(--text-primary);">${escapeHtml(res.explanation || '')}</div>
            ${stepsHtml ? `<div class="path-steps-list">${stepsHtml}</div>` : ''}
            ${reasonsHtml ? `<div class="rank-reasons-row">${reasonsHtml}</div>` : ''}
          </div>
        `;
      })
      .join('');

    return `
      <div class="intel-card">
        <div class="card-header-row">
          <h3 class="card-title">Ranked multi-hop paths (${results.length})</h3>
          <span style="font-size:12px;color:var(--text-muted);">Select a path card to isolate on graph</span>
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
      direct_people: 'Direct people',
      investors: 'Investors',
      direct_companies: 'Direct companies',
      indirect_connections: '2-hop indirect',
    };

    const itemsHtml = results
      .map((res) => {
        const ent = res.entity || {};
        const fullNode = nodesMap.get(ent.id) || ent;
        const firstPathId = res.path_ids?.[0] || '';
        const isIsolated = firstPathId && isolatedPathId === firstPathId;
        return `
          <div class="result-card ${isIsolated ? 'isolated' : ''}" data-q3-group-item="${escapeHtml(res.group || 'other')}" data-isolate-path="${escapeHtml(firstPathId)}">
            <div class="result-top-row">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                <span class="rank-pill">#${escapeHtml(res.rank)}</span>
                <strong style="font-size:14px;color:var(--text-primary);">${escapeHtml(ent.name || ent.id)}</strong>
                <span class="badge badge-ai">${escapeHtml(groupLabels[res.group] || res.group || 'Network')}</span>
                ${renderOriginBadges(fullNode)}
              </div>
              <div style="display:flex;gap:8px;">
                <button type="button" class="btn-ghost-sm" data-inspect-node="${escapeHtml(ent.id)}">Inspect</button>
                ${
                  ent.entity_type !== 'Person'
                    ? `<button type="button" class="btn-ghost-sm" data-pivot-qid="company_representatives" data-pivot-company="${escapeHtml(ent.name)}" data-pivot-company-id="${escapeHtml(ent.id)}">Slush dossier</button>`
                    : ''
                }
              </div>
            </div>
            <div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">${escapeHtml(res.explanation || '')}</div>
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">
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
          <h3 class="card-title">2-hop professional ecosystem (${results.length})</h3>
          <div class="preset-filters">
            <button type="button" class="filter-chip active" data-q3-group-tab="all">All (${groupCounts.all})</button>
            <button type="button" class="filter-chip" data-q3-group-tab="direct_people">People (${groupCounts.direct_people})</button>
            <button type="button" class="filter-chip" data-q3-group-tab="investors">Investors (${groupCounts.investors})</button>
            <button type="button" class="filter-chip" data-q3-group-tab="direct_companies">Companies (${groupCounts.direct_companies})</button>
            <button type="button" class="filter-chip" data-q3-group-tab="indirect_connections">2-hop indirect (${groupCounts.indirect_connections})</button>
          </div>
        </div>
        <div class="results-stack">
          ${itemsHtml || `<div style="color:var(--text-muted);font-size:13px;">No surrounding professional connections documented in snapshot</div>`}
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
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
              <span class="rank-pill">Rep #${escapeHtml(res.rank)}</span>
              <strong style="font-size:15px;color:var(--text-primary);">${escapeHtml(person.name || person.id)}</strong>
              ${renderParticipationBadges(res.attendance || person.participation)}
              ${renderOriginBadges(person)}
            </div>
            <button type="button" class="btn-ghost-sm" data-inspect-node="${escapeHtml(person.id)}">Inspect profile</button>
          </div>

          ${p.job_title ? `<div style="font-size:13px;font-weight:500;color:var(--cala-primary);margin-bottom:4px;">${escapeHtml(p.job_title)}</div>` : ''}
          <div style="font-size:13px;color:var(--text-primary);margin-bottom:8px;">${escapeHtml(res.explanation || '')}</div>
          ${p.biography ? `<p style="font-size:13px;color:var(--text-secondary);margin:0 0 8px;line-height:20px;">${escapeHtml(p.biography)}</p>` : ''}

          ${
            topics.length > 0
              ? `<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px;">
                  ${topics.map((t) => `<span class="badge badge-ai">${escapeHtml(t)}</span>`).join('')}
                </div>`
              : ''
          }

          ${
            workEntries.length > 0
              ? `<div style="margin-bottom:8px;display:flex;flex-direction:column;gap:4px;">
                  ${workEntries
                    .slice(0, 3)
                    .map((w) => {
                      const u = safeExternalUrl(w.source_url);
                      return `<div style="font-size:12px;color:var(--text-secondary);"><strong>${escapeHtml(w.role || 'Role')}</strong> at ${escapeHtml(w.organization || '')} ${u ? `<a href="${escapeHtml(u)}" target="_blank" rel="noopener noreferrer">Source ↗</a>` : ''}</div>`;
                    })
                    .join('')}
                </div>`
              : ''
          }

          ${
            res.contact_interpretation
              ? `<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">${escapeHtml(res.contact_interpretation)}</div>`
              : ''
          }

          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">
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
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
            <strong style="font-size:14px;color:var(--text-primary);">
              Affiliated people — individual Slush 2026 attendance unverified (${unverifiedList.length})
            </strong>
            <span class="badge badge-warn">Company listing ≠ person attendance</span>
          </div>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 8px;">
            These people have documented corporate, founder, or board ties to the company, but no named Slush 2026 speaker or attendee record in the snapshot.
          </p>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${unverifiedList
              .map(
                (u) => `
              <div class="path-step-row">
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                  <strong>${escapeHtml(u.name || u.id)}</strong>
                  ${renderOriginBadges(u)}
                  ${renderCompletenessBadge(u.record_completeness)}
                </div>
                <div style="display:flex;align-items:center;gap:8px;">
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
        <h3 class="card-title">Named Slush 2026 representatives (${results.length})</h3>
        <span class="badge badge-slush">Physical check-in unverified</span>
      </div>
      <div class="results-stack">
        ${
          verifiedCardsHtml ||
          `<div class="honest-empty-banner">
            <div class="honest-empty-title">No named Slush 2026 representatives in snapshot</div>
            <div style="font-size:13px;color:var(--text-secondary);">Even when a company is listed in the Slush directory, Unicorn Radar does not assume which employees are attending without named participation records.</div>
          </div>`
        }
      </div>
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
          <div style="margin-top:8px;">
            ${renderSourceDocumentBadge(doc)}
            ${doc.evidence ? `<div style="font-size:12px;color:var(--text-secondary);margin-top:4px;padding-left:8px;border-left:2px solid var(--border-strong);">“${escapeHtml(doc.evidence)}”</div>` : ''}
          </div>
        `
        )
        .join('');

      return `
        <div class="evidence-card" id="evidence-card-${escapeHtml(ev.id)}" data-ev-dataset="${escapeHtml(ds)}">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
              <code style="font-size:12px;color:var(--cala-primary);font-weight:500;">${escapeHtml(ev.id)}</code>
              <span class="badge ${isSlush ? 'badge-slush' : 'badge-cala'}">${escapeHtml(ds)}</span>
            </div>
            ${ev.record_pointer ? `<code style="font-size:12px;color:var(--text-muted);">${escapeHtml(ev.record_pointer)}</code>` : ''}
          </div>
          ${docsHtml || `<div style="font-size:12px;color:var(--text-muted);margin-top:4px;">Primary dataset record assertion preserved in snapshot</div>`}
          ${
            ev.record
              ? `<details style="margin-top:8px;font-size:12px;color:var(--text-muted);">
                  <summary style="cursor:pointer;">Raw record snapshot</summary>
                  <pre class="code-block" style="margin-top:8px;max-height:180px;">${escapeHtml(JSON.stringify(ev.record, null, 2))}</pre>
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
        <h3 class="card-title">Provenance &amp; evidence ledger (${items.length})</h3>
        <span class="badge badge-cala">100% referential integrity</span>
      </div>
      <div class="evidence-search-row">
        <input
          type="text"
          id="evidenceSearchInput"
          class="smart-input"
          style="flex:1 1 200px;height:36px;"
          placeholder="Filter by evidence ID, publisher, or URL"
        />
        <select id="evidenceDatasetFilter" class="styled-select">
          <option value="all">All datasets (${items.length})</option>
          <option value="cala">Cala Graph</option>
          <option value="slush_people">Slush People</option>
          <option value="slush_companies">Slush Companies</option>
        </select>
      </div>
      <div class="evidence-list">
        ${itemsHtml || `<div style="font-size:13px;color:var(--text-muted);">No evidence records attached to this state</div>`}
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
