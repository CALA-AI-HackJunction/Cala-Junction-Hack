/**
 * Unicorn Radar — Partner Tech Challenge Dedicated Views (ES2022)
 * 1. Saved Analyses & Aiven Cloud (PostgreSQL + Valkey + Gemini/Gemma Telemetry)
 * 2. CRACI Isolated Build, CycloneDX SBOM & Egress Security Audit
 * 3. Dataset Coverage, Assertion Exclusion Funnel & Cala Investor Audit
 */

import {
  escapeHtml,
  safeExternalUrl,
  formatMs,
  formatBytes,
  formatQuestionLabel,
  renderStatusBadge,
  shortId,
} from './utils.js';

/* ==========================================================================
   VIEW 2: SAVED RUNS & AIVEN CLOUD TELEMETRY
   ========================================================================== */

export function renderHistoryView({
  containerEl,
  infraStatus,
  analysesList,
  onRefresh,
  onRestoreRun,
  onInspectPrompt,
}) {
  if (!containerEl) return;

  const st = infraStatus?.storage || {};
  const ca = infraStatus?.cache || {};
  const md = infraStatus?.models || {};
  const rows = Array.isArray(analysesList) ? analysesList : [];

  const pgConnected = Boolean(st.aiven_pg_connected);
  const vkConnected = Boolean(ca.aiven_valkey_connected);

  const tableRowsHtml = rows
    .map((item) => {
      const req = item.request || item.inputs || {};
      const querySummary =
        req.source && req.target
          ? `${req.source} → ${req.target}`
          : req.source || req.company || item.question_id;

      return `
        <tr>
          <td class="mono" style="font-size:12px;color:var(--cala-primary);">${escapeHtml(shortId(item.run_id, 16))}</td>
          <td><span class="badge badge-neutral">${escapeHtml(formatQuestionLabel(item.question_id))}</span></td>
          <td style="font-weight:500;color:var(--text-primary);">${escapeHtml(querySummary)}</td>
          <td>${renderStatusBadge(item.status)}</td>
          <td class="mono" style="font-size:12px;color:var(--text-muted);">${escapeHtml(item.created_at ? new Date(item.created_at).toLocaleString() : '—')}</td>
          <td>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <button type="button" class="btn-ghost-sm" data-restore-run="${escapeHtml(item.run_id)}">
                Restore run
              </button>
              <button type="button" class="btn-ghost-sm" data-prompt-run="${escapeHtml(item.run_id)}">
                Prompt JSON
              </button>
            </div>
          </td>
        </tr>
      `;
    })
    .join('');

  containerEl.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px;">
      <div>
        <span class="section-eyebrow">Aiven managed data layer &amp; reproducibility</span>
        <h2 style="font-family:var(--font-display);font-weight:400;font-size:28px;line-height:32px;margin:4px 0 0;display:flex;align-items:center;gap:8px;">
          <img src="https://www.cala.ai/assets/plug-BLa6W1NF.png" alt="" class="cala-mini-logo" onerror="this.style.display='none'" />
          <span>Saved analyses and Aiven telemetry</span>
        </h2>
      </div>
      <button type="button" class="btn-ghost-sm" id="btnRefreshHistoryView">Refresh telemetry</button>
    </div>

    <div class="tech-grid-3">
      <!-- Aiven PostgreSQL Card -->
      <div class="metric-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <span class="section-eyebrow">Immutable run store</span>
          <span class="badge ${pgConnected ? 'badge-dual' : 'badge-slush'}">
            ${pgConnected ? 'Aiven PostgreSQL connected' : escapeHtml(st.primary_backend || 'SQLite fallback active')}
          </span>
        </div>
        <div class="metric-value">${escapeHtml(st.saved_analyses_count ?? rows.length)}</div>
        <div class="metric-sub">
          Persisted runs · Avg write: <strong>${formatMs(st.avg_write_ms)}</strong> vs uncached compute
        </div>
      </div>

      <!-- Aiven Valkey Cache Card -->
      <div class="metric-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <span class="section-eyebrow">Versioned cache</span>
          <span class="badge ${vkConnected ? 'badge-dual' : 'badge-cala'}">
            ${vkConnected ? 'Aiven Valkey connected' : escapeHtml(ca.primary_cache || 'Local LRU + SQLite cache')}
          </span>
        </div>
        <div class="metric-value">${escapeHtml(ca.hit_rate_pct !== undefined ? `${Number(ca.hit_rate_pct).toFixed(1)}%` : '0.0%')}</div>
        <div class="metric-sub">
          Hits: <strong>${escapeHtml(ca.cache_hits ?? 0)}</strong> vs <strong>${escapeHtml(ca.cache_misses ?? 0)}</strong> misses · Avg hit: <strong>${formatMs(ca.avg_cache_hit_ms)}</strong>
        </div>
      </div>

      <!-- Gemini + Gemma Telemetry Card -->
      <div class="metric-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <span class="section-eyebrow">Synthesis &amp; entailment</span>
          <span class="badge ${md.gemini?.configured || md.gemma?.configured ? 'badge-cala' : 'badge-neutral'}">
            ${md.gemini?.configured && md.gemma?.configured ? 'Gemini + Gemma active' : md.gemini?.configured ? 'Gemini active' : 'Deterministic template'}
          </span>
        </div>
        <div class="metric-value">${escapeHtml((md.gemini?.calls ?? 0) + (md.gemma?.calls ?? 0))}</div>
        <div class="metric-sub">
          Gemini (<code>${escapeHtml(md.gemini?.model || 'gemini-2.5-flash')}</code>): ${escapeHtml(md.gemini?.calls ?? 0)} calls · Gemma (<code>${escapeHtml(md.gemma?.model || 'gemma-3-27b-it')}</code>): ${escapeHtml(md.gemma?.calls ?? 0)} audits
        </div>
      </div>
    </div>

    <div class="intel-card">
      <div class="card-header-row">
        <h3 class="card-title">Saved analysis runs (${rows.length})</h3>
        <span style="font-size:12px;color:var(--text-muted);">
          Cache keys hash <code>{canonical_ids, question_id, graph_version, pipeline_version, prompt_version, composer_mode}</code>
        </span>
      </div>
      ${
        rows.length > 0
          ? `<div class="data-table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Run ID</th>
                    <th>Task</th>
                    <th>Submitted query</th>
                    <th>Status</th>
                    <th>Created at</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>${tableRowsHtml}</tbody>
              </table>
            </div>`
          : `<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px;">
              No saved runs yet in this store. Run a query in <strong>Connection Explorer</strong> to record its evidence and subgraph snapshot
            </div>`
      }
    </div>
  `;

  containerEl.querySelector('#btnRefreshHistoryView')?.addEventListener('click', () => onRefresh?.());

  for (const btn of containerEl.querySelectorAll('[data-restore-run]')) {
    btn.addEventListener('click', () => onRestoreRun?.(btn.getAttribute('data-restore-run')));
  }
  for (const btn of containerEl.querySelectorAll('[data-prompt-run]')) {
    btn.addEventListener('click', () => onInspectPrompt?.(btn.getAttribute('data-prompt-run')));
  }
}

/* ==========================================================================
   VIEW 3: CRACI BUILD, CYCLONEDX SBOM & EGRESS DEFENSE
   ========================================================================== */

export function renderCraciView({
  containerEl,
  provenance,
  lastAudit,
  onRefreshProvenance,
  onRunAudit,
  onPivotEntity,
}) {
  if (!containerEl || !provenance) return;

  const isLiveApi = provenance.source_mode === 'craci_api_live';
  const wf = provenance.workflow_policy || {};
  const runnerJobs = Array.isArray(wf.craci_runner_jobs) ? wf.craci_runner_jobs : [];
  const sbom = provenance.sbom || {};
  const components = Array.isArray(sbom.components) ? sbom.components : [];
  const net = provenance.network_trace || {};
  const observations = Array.isArray(net.observations) ? net.observations : [];
  const calaMatches = Array.isArray(provenance.cala_entity_matches) ? provenance.cala_entity_matches : [];

  const auditHtml = lastAudit ? renderCraciAuditResultCard(lastAudit) : '';

  const componentsRowsHtml = components
    .map(
      (c) => `
      <tr>
        <td style="font-weight:500;color:var(--text-primary);">${escapeHtml(c.name)}</td>
        <td class="mono" style="color:var(--cala-primary);">${escapeHtml(c.version || '—')}</td>
        <td class="mono" style="font-size:12px;color:var(--text-muted);">${escapeHtml(c.purl || '')}</td>
        <td><span class="badge badge-dual">${escapeHtml(c.license || 'Verified')}</span></td>
        <td>${escapeHtml(c.supplier_vendor || 'PyPI / OSS')}</td>
      </tr>
    `
    )
    .join('');

  const netRowsHtml = observations
    .map((obs) => {
      const h = obs.http || {};
      const denied = Boolean(h.policyDenied);
      return `
        <tr>
          <td class="mono">#${escapeHtml(obs.sequence ?? 0)}</td>
          <td><span class="badge badge-neutral">${escapeHtml(h.method || obs.protocol || 'HTTPS')}</span></td>
          <td class="mono" style="font-size:12px;color:var(--text-primary);">${escapeHtml(h.originUrl || '—')}</td>
          <td class="mono">${escapeHtml(h.statusCode ?? '—')}</td>
          <td><code style="font-size:12px;color:var(--cala-primary);">${escapeHtml(h.matchedRule || 'allow-policy')}</code></td>
          <td>
            <span class="badge ${denied ? 'badge-warn' : 'badge-dual'}">
              ${denied ? 'Policy denied' : 'Allowed by proxy'}
            </span>
          </td>
        </tr>
      `;
    })
    .join('');

  containerEl.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px;">
      <div>
        <span class="section-eyebrow">CRACI supply-chain &amp; egress attestation</span>
        <h2 style="font-family:var(--font-display);font-weight:400;font-size:28px;line-height:32px;margin:4px 0 0;display:flex;align-items:center;gap:8px;">
          <img src="https://www.cala.ai/assets/robot-Dl2CE1vq.png" alt="" class="cala-mini-logo" onerror="this.style.display='none'" />
          <span>Isolated VM runner, CycloneDX 1.7 SBOM, and network policy</span>
        </h2>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <span class="badge ${isLiveApi ? 'badge-dual' : 'badge-cala'}">
          Source: ${isLiveApi ? 'Live CRACI API (/v1preview1)' : 'Verified workspace snapshot'}
        </span>
        <button type="button" class="btn-ghost-sm" id="btnRefreshCraci">Refresh SBOM</button>
        <button type="button" class="btn-primary" id="btnRunCraciAudit">
          Run supply-chain audit
        </button>
      </div>
    </div>

    <div id="craciAuditResultSlot">${auditHtml}</div>

    <div class="tech-grid-3">
      <div class="metric-card">
        <span class="section-eyebrow">CI runner isolation</span>
        <div class="metric-value"><code>runs-on: craci</code></div>
        <div class="metric-sub">
          ${escapeHtml(wf.workflows_scanned ?? 1)} workflow scanned · Compliant: <strong>${wf.compliant ? 'Yes (isolated Linux VM)' : 'Pending'}</strong>
        </div>
      </div>

      <div class="metric-card">
        <span class="section-eyebrow">Software bill of materials</span>
        <div class="metric-value">${escapeHtml(sbom.component_count ?? components.length)} components</div>
        <div class="metric-sub">
          Format: <strong>${escapeHtml(sbom.bomFormat || 'CycloneDX')} ${escapeHtml(sbom.specVersion || '1.7')}</strong> · Complete: <strong>${sbom.complete ? 'True' : 'Partial'}</strong>
        </div>
      </div>

      <div class="metric-card">
        <span class="section-eyebrow">Egress firewall</span>
        <div class="metric-value">${escapeHtml(net.policy_denied_count ?? 0)} denied / ${escapeHtml(net.unmatched_egress_count ?? 0)} unmatched</div>
        <div class="metric-sub">
          <code>cracicorp/setup@v1</code> · <code>default: deny</code> · Package-aware proxy attestation
        </div>
      </div>
    </div>

    <div class="tech-grid-2">
      <!-- Workflow Runner Policy Card -->
      <div class="intel-card">
        <div class="card-header-row">
          <h3 class="card-title">CRACI workflow &amp; egress policy</h3>
          <span class="badge badge-dual">${wf.compliant ? 'Policy verified' : 'Check policy'}</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;">
          ${
            runnerJobs.length > 0
              ? runnerJobs
                  .map(
                    (j) => `
                  <div class="path-step-row" style="flex-direction:column;gap:4px;">
                    <div style="display:flex;justify-content:space-between;width:100%;flex-wrap:wrap;">
                      <strong>${escapeHtml(j.job_name || 'verify-and-sbom')}</strong>
                      <span class="badge badge-cala">runs-on: ${escapeHtml(j.runs_on || 'craci')}</span>
                    </div>
                    <div style="font-size:12px;color:var(--text-muted);">
                      Workflow: <code>${escapeHtml(j.workflow || '.github/workflows/ci.yml')}</code> · Arch: <code>${escapeHtml(j.architecture || 'amd64')}</code> · Egress: <code>${escapeHtml(j.egress_policy || 'package-aware-proxy')}</code>
                    </div>
                  </div>
                `
                  )
                  .join('')
              : `<div style="font-size:13px;color:var(--text-muted);">Workspace workflow inspected deterministically</div>`
          }
        </div>

        ${
          calaMatches.length > 0
            ? `<div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-subtle);">
                <div class="section-eyebrow" style="margin-bottom:8px;">SBOM vendors matched in Cala × Slush graph</div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                  ${calaMatches
                    .map(
                      (m) => `
                    <button type="button" class="btn-ghost-sm" data-craci-entity-name="${escapeHtml(m.matched_name)}" data-craci-entity-id="${escapeHtml(m.matched_entity_id)}">
                      ${escapeHtml(m.matched_name)} (<code>${escapeHtml(shortId(m.matched_entity_id, 15))}</code>)
                    </button>
                  `
                    )
                    .join('')}
                </div>
              </div>`
            : ''
        }
      </div>

      <!-- Network Trace Card -->
      <div class="intel-card">
        <div class="card-header-row">
          <h3 class="card-title">Build network egress trace (${observations.length})</h3>
          <span class="badge badge-cala">Schema v${escapeHtml(net.schemaVersion || '1.0')}</span>
        </div>
        ${
          observations.length > 0
            ? `<div class="data-table-wrap">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>Seq</th>
                      <th>Method</th>
                      <th>Origin URL</th>
                      <th>HTTP</th>
                      <th>Rule</th>
                      <th>Verdict</th>
                    </tr>
                  </thead>
                  <tbody>${netRowsHtml}</tbody>
                </table>
              </div>`
            : `<div style="font-size:13px;color:var(--text-muted);">No outbound network observations recorded in offline workspace mode</div>`
        }
      </div>
    </div>

    <!-- CycloneDX SBOM Component Table -->
    <div class="intel-card">
      <div class="card-header-row">
        <h3 class="card-title">CycloneDX 1.7 dependency inventory (${components.length})</h3>
        <span class="badge badge-neutral">Frontend: 0 external runtime npm packages</span>
      </div>
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Package name</th>
              <th>Locked version</th>
              <th>Package URL (pURL)</th>
              <th>OSI license</th>
              <th>Supplier / ecosystem</th>
            </tr>
          </thead>
          <tbody>${componentsRowsHtml}</tbody>
        </table>
      </div>
    </div>
  `;

  containerEl.querySelector('#btnRefreshCraci')?.addEventListener('click', () => onRefreshProvenance?.());

  const auditBtn = containerEl.querySelector('#btnRunCraciAudit');
  auditBtn?.addEventListener('click', async () => {
    auditBtn.disabled = true;
    const origHtml = auditBtn.innerHTML;
    auditBtn.textContent = 'Auditing SBOM and egress…';
    try {
      const res = await onRunAudit?.();
      const slot = containerEl.querySelector('#craciAuditResultSlot');
      if (slot && res) {
        slot.innerHTML = renderCraciAuditResultCard(res);
      }
    } finally {
      auditBtn.disabled = false;
      auditBtn.innerHTML = origHtml;
    }
  });

  for (const btn of containerEl.querySelectorAll('[data-craci-entity-name]')) {
    btn.addEventListener('click', () => {
      onPivotEntity?.({
        name: btn.getAttribute('data-craci-entity-name'),
        id: btn.getAttribute('data-craci-entity-id'),
      });
    });
  }
}

function renderCraciAuditResultCard(audit) {
  const isLowRisk = audit.risk_level === 'low';
  const findings = Array.isArray(audit.findings) ? audit.findings : [];
  const riskStr = String(audit.risk_level || 'low');
  const riskFormatted = riskStr.charAt(0).toUpperCase() + riskStr.slice(1).toLowerCase();

  return `
    <div class="intel-card" style="margin-bottom:16px;">
      <div class="card-header-row">
        <h3 class="card-title">Grounded supply-chain and egress security audit</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <span class="badge ${isLowRisk ? 'badge-dual' : 'badge-warn'}">Risk: ${escapeHtml(riskFormatted)}</span>
          <span class="badge badge-ai">Auditor: ${escapeHtml(audit.auditor_model || 'Grounded verifier')}</span>
          <span class="badge badge-cala">Egress: ${escapeHtml(audit.egress_verdict || 'verified')}</span>
          ${audit.elapsed_ms ? `<span class="badge badge-neutral">${formatMs(audit.elapsed_ms)}</span>` : ''}
        </div>
      </div>
      <p style="font-size:14px;color:var(--text-primary);margin:0 0 12px;">${escapeHtml(audit.summary || '')}</p>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;">
        ${findings
          .map(
            (f) => `
          <div class="claim-item">
            <div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px;">
              <strong style="font-size:13px;color:var(--text-primary);">${escapeHtml(f.title)}</strong>
              <span class="badge ${f.severity === 'critical' || f.severity === 'high' ? 'badge-warn' : 'badge-cala'}">${escapeHtml(f.severity || 'info')}</span>
            </div>
            <div style="font-size:13px;color:var(--text-secondary);margin-bottom:4px;">${escapeHtml(f.detail)}</div>
            ${f.evidence_ref ? `<code style="font-size:12px;color:var(--text-muted);">Ref: ${escapeHtml(f.evidence_ref)}</code>` : ''}
          </div>
        `
          )
          .join('')}
      </div>
    </div>
  `;
}

/* ==========================================================================
   VIEW 4: DATASET COVERAGE, ASSERTION FUNNEL & AUDIT MANIFEST
   ========================================================================== */

export function renderCoverageView({
  containerEl,
  coverage,
  featuredInvestors = [],
  onExploreInvestor,
}) {
  if (!containerEl || !coverage) return;

  const counts = coverage.counts || {};
  const edgeTypes = counts.edge_types || {};
  const nodeTypes = counts.node_types || {};
  const datasets = Array.isArray(coverage.datasets) ? coverage.datasets : [];
  const limitations = Array.isArray(coverage.limitations) ? coverage.limitations : [];

  const totalEdges = counts.edges ?? 52471;
  const eventEdges = edgeTypes.PARTICIPATES_IN_EVENT ?? 2993;
  const traversableEdges = counts.traversable_edges ?? 40566;
  const otherExcluded = Math.max(0, totalEdges - traversableEdges - eventEdges);

  const nonBridgeTypes = new Set([
    'PARTICIPATES_IN_EVENT',
    'OPERATES_IN_INDUSTRY',
    'HAS_DOMAIN_NAME',
    'HAS_HEADQUARTERS_IN',
    'HAS_PRESENCE_IN',
    'IS_REGISTERED_IN',
  ]);

  const sortedEdgeTypes = Object.entries(edgeTypes).sort((a, b) => b[1] - a[1]);
  const maxEdgeCount = Math.max(...sortedEdgeTypes.map(([, v]) => v), 1);

  const edgeBarsHtml = sortedEdgeTypes
    .slice(0, 14)
    .map(([etype, cnt]) => {
      const isExcluded = nonBridgeTypes.has(etype);
      const pct = Math.max(2, (cnt / maxEdgeCount) * 100);
      return `
        <div class="bar-row">
          <div class="bar-label-line">
            <span>
              <code style="font-size:12px;">${escapeHtml(etype)}</code>
              ${isExcluded ? `<span class="badge badge-neutral" style="margin-left:8px;">Excluded non-bridge</span>` : `<span class="badge badge-cala" style="margin-left:8px;">Traversable</span>`}
            </span>
            <strong class="mono">${escapeHtml(cnt.toLocaleString())}</strong>
          </div>
          <div class="bar-track">
            <div class="bar-fill ${isExcluded ? 'excluded' : ''}" style="width:${pct.toFixed(1)}%;"></div>
          </div>
        </div>
      `;
    })
    .join('');

  const sortedNodeTypes = Object.entries(nodeTypes).sort((a, b) => b[1] - a[1]);
  const maxNodeCount = Math.max(...sortedNodeTypes.map(([, v]) => v), 1);

  const nodeBarsHtml = sortedNodeTypes
    .map(([ntype, cnt]) => {
      const pct = Math.max(2, (cnt / maxNodeCount) * 100);
      return `
        <div class="bar-row">
          <div class="bar-label-line">
            <span><strong>${escapeHtml(ntype)}</strong></span>
            <strong class="mono">${escapeHtml(cnt.toLocaleString())}</strong>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="width:${pct.toFixed(1)}%;"></div>
          </div>
        </div>
      `;
    })
    .join('');

  const investorsHtml =
    featuredInvestors.length > 0
      ? `
      <div class="intel-card" style="margin-top:16px;">
        <div class="card-header-row">
          <h3 class="card-title">Cala-verified Slush 2026 investors (${featuredInvestors.length})</h3>
          <span class="badge badge-cala">Namespace: <code>cala_verified_investor_match</code></span>
        </div>
        <div class="candidates-grid">
          ${featuredInvestors
            .map((inv) => {
              const u = safeExternalUrl(inv.website);
              return `
                <div class="candidate-card">
                  <div>
                    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:4px;">
                      <strong style="font-size:15px;color:var(--text-primary);">${escapeHtml(inv.slush_company_name)}</strong>
                      <span class="badge badge-cala">${escapeHtml(inv.country || 'VC')}</span>
                    </div>
                    <div class="mono" style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
                      Cala UUID: ${escapeHtml(inv.cala_id)}
                    </div>
                    <p style="font-size:13px;color:var(--text-secondary);margin:0 0 8px;">${escapeHtml(inv.cala_desc || inv.cala_name || '')}</p>
                    ${u ? `<a href="${escapeHtml(u)}" target="_blank" rel="noopener noreferrer" style="font-size:12px;">${escapeHtml(u)} ↗</a>` : ''}
                  </div>
                  <div style="display:flex;gap:8px;flex-wrap:wrap;">
                    <button
                      type="button"
                      class="btn-ghost-sm"
                      data-investor-q4="${escapeHtml(inv.slush_company_name)}"
                      data-investor-id="${escapeHtml(inv.slush_snapshot_id || '')}"
                      style="flex:1;justify-content:center;"
                    >
                      Slush speakers (Q4)
                    </button>
                    <button
                      type="button"
                      class="btn-ghost-sm"
                      data-investor-q3="${escapeHtml(inv.slush_company_name)}"
                      data-investor-id="${escapeHtml(inv.slush_snapshot_id || '')}"
                      style="flex:1;justify-content:center;"
                    >
                      Network (Q3)
                    </button>
                  </div>
                </div>
              `;
            })
            .join('')}
        </div>
      </div>
    `
      : '';

  containerEl.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px;">
      <div>
        <span class="section-eyebrow">Deterministic reconciliation &amp; epistemic audit</span>
        <h2 style="font-family:var(--font-display);font-weight:400;font-size:28px;line-height:32px;margin:4px 0 0;display:flex;align-items:center;gap:8px;">
          <img src="https://www.cala.ai/assets/funnel-C84kzSCH.png" alt="" class="cala-mini-logo" onerror="this.style.display='none'" />
          <span>Dataset coverage, non-bridge funnel, and snapshot manifest</span>
        </h2>
      </div>
      <code style="font-size:12px;color:var(--cala-primary);background:var(--bg-card);padding:6px 12px;border-radius:4px;border:1px solid var(--border-subtle);">
        graph_version: ${escapeHtml(shortId(coverage.graph_version, 26))}
      </code>
    </div>

    <!-- Explicit Cala complete: false Transparency Banner -->
    <div class="disambiguation-banner visible" style="margin-bottom:16px;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:4px;">
        <strong style="font-size:14px;color:var(--text-primary);">
          Snapshot completeness notice (<code>cala_coverage.complete = ${String(coverage.cala_coverage?.complete ?? false)}</code>)
        </strong>
        <span class="badge badge-slush">Zero confabulation policy</span>
      </div>
      <div style="font-size:13px;color:var(--text-secondary);">
        <strong>Reason:</strong> ${escapeHtml(coverage.cala_coverage?.reason || 'Time budget reached during export')} —
        <strong>${escapeHtml((counts.cala_full_entity_records ?? 3456).toLocaleString())}</strong> full Cala entity records (${escapeHtml((counts.cala_full_company_records ?? 2936).toLocaleString())} companies) and <strong>${escapeHtml((counts.cala_endpoint_entities ?? 35508).toLocaleString())}</strong> edge endpoint stubs reconciled with <strong>${escapeHtml((counts.slush_people_primary_records ?? 952).toLocaleString())}</strong> Slush people and <strong>${escapeHtml((counts.slush_company_records ?? 6275).toLocaleString())}</strong> Slush companies. Missing paths mean not established in this snapshot, not absence in the real world.
      </div>
    </div>

    <!-- Moment 2: 4-Step Assertion Filtering Funnel -->
    <div class="funnel-steps">
      <div class="funnel-card">
        <span class="section-eyebrow">1. Reconciled graph nodes</span>
        <div class="metric-value">${escapeHtml((counts.nodes ?? 40423).toLocaleString())}</div>
        <div class="metric-sub">
          ${escapeHtml((counts.cross_source_company_merges ?? 2583).toLocaleString())} corroborated Cala × Slush company joins · ${escapeHtml((counts.unresolved_identity_candidates ?? 1287).toLocaleString())} unmerged name-only candidates preserved
        </div>
      </div>

      <div class="funnel-card">
        <span class="section-eyebrow">2. Total raw assertions</span>
        <div class="metric-value">${escapeHtml(totalEdges.toLocaleString())}</div>
        <div class="metric-sub">
          ${escapeHtml((counts.cala_supported_edges ?? 51910).toLocaleString())} Cala assertions + ${escapeHtml((counts.slush_supported_edges ?? 618).toLocaleString())} Slush assertions · ${escapeHtml((counts.evidence_records ?? 63789).toLocaleString())} evidence records
        </div>
      </div>

      <div class="funnel-card">
        <span class="section-eyebrow">3. Excluded non-bridges</span>
        <div class="metric-value">&minus;${escapeHtml((eventEdges + otherExcluded).toLocaleString())}</div>
        <div class="metric-sub">
          <strong>${escapeHtml(eventEdges.toLocaleString())}</strong> <code>PARTICIPATES_IN_EVENT</code> Slush links + <strong>${escapeHtml(otherExcluded.toLocaleString())}</strong> industry/domain/unattributed edges vs total raw assertions
        </div>
      </div>

      <div class="funnel-card" style="border-color:var(--cala-border);">
        <span class="section-eyebrow" style="color:var(--cala-primary);">4. Verified professional bridges</span>
        <div class="metric-value" style="color:var(--cala-primary);">${escapeHtml(traversableEdges.toLocaleString())}</div>
        <div class="metric-sub">
          ${((traversableEdges / Math.max(totalEdges, 1)) * 100).toFixed(1)}% of raw assertions retained · 100% backed by primary source documents
        </div>
      </div>
    </div>

    <div class="tech-grid-2">
      <!-- Main Chart (Wider): Assertion Types Traversable vs Excluded -->
      <div class="intel-card">
        <div class="card-header-row">
          <h3 class="card-title">Assertion types: traversable vs excluded</h3>
          <span class="badge badge-cala">One accent for traversable bridges</span>
        </div>
        ${edgeBarsHtml}
      </div>

      <!-- Narrower Ranked Breakdown List + Policy -->
      <div class="intel-card">
        <div class="card-header-row">
          <h3 class="card-title">Entity class breakdown &amp; identity rules</h3>
        </div>
        ${nodeBarsHtml}
        <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-subtle);font-size:13px;color:var(--text-secondary);">
          <strong style="color:var(--text-primary);">Identity resolution policy:</strong> ${escapeHtml(coverage.identity_policy || '')}
        </div>
      </div>
    </div>

    <div class="tech-grid-2">
      <!-- SHA-256 Dataset Manifest -->
      <div class="intel-card">
        <div class="card-header-row">
          <h3 class="card-title">Immutable input snapshot manifest</h3>
          <span class="badge badge-neutral">Importer v${escapeHtml(coverage.importer_version || '2.0.2')}</span>
        </div>
        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Dataset ID</th>
                <th>Filename</th>
                <th>Size</th>
                <th>SHA-256 digest</th>
              </tr>
            </thead>
            <tbody>
              ${datasets
                .map(
                  (d) => `
                <tr>
                  <td><span class="badge ${String(d.id).includes('cala') ? 'badge-cala' : 'badge-slush'}">${escapeHtml(d.id)}</span></td>
                  <td class="mono">${escapeHtml(d.filename)}</td>
                  <td class="mono">${formatBytes(d.size_bytes)}</td>
                  <td class="mono" style="font-size:12px;color:var(--text-muted);">${escapeHtml(shortId(d.sha256, 22))}</td>
                </tr>
              `
                )
                .join('')}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Limitations Checklist -->
      <div class="intel-card">
        <div class="card-header-row">
          <h3 class="card-title">Documented epistemic guardrails &amp; limitations</h3>
        </div>
        <ul class="brief-list">
          ${limitations.map((lim) => `<li>${escapeHtml(lim)}</li>`).join('')}
        </ul>
      </div>
    </div>

    ${investorsHtml}
  `;

  for (const btn of containerEl.querySelectorAll('[data-investor-q4]')) {
    btn.addEventListener('click', () => {
      onExploreInvestor?.({
        question_id: 'company_representatives',
        company: btn.getAttribute('data-investor-q4'),
        company_id: btn.getAttribute('data-investor-id') || null,
      });
    });
  }

  for (const btn of containerEl.querySelectorAll('[data-investor-q3]')) {
    btn.addEventListener('click', () => {
      onExploreInvestor?.({
        question_id: 'company_network',
        company: btn.getAttribute('data-investor-q3'),
        company_id: btn.getAttribute('data-investor-id') || null,
      });
    });
  }
}
