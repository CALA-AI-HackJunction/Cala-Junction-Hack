/**
 * Comare di Slush — Main Application Controller (Native ES2022)
 * Clean, visual, relationship-first Cala AI experience:
 * - Natural-language fill-in-the-blank sentence builder
 * - Question mode pills right beneath the title/sentence
 * - Automatic AI composer & guardrail selection (zero technical toggles)
 * - Progressive reveal: SUBGRAPH + INFOS appear interactively right after search starts
 */

import {
  escapeHtml,
  formatMs,
  indexEvidence,
  renderOriginBadges,
  showToast,
  stripInternalIds,
} from './utils.js';

import {
  getHealth,
  getQuestions,
  getPresets,
  searchEntities,
  streamAnalysis,
  listSavedAnalyses,
  getSavedAnalysis,
} from './api.js';

import { KnowledgeGraphView } from './graph-view.js';
import {
  renderDisambiguationPanel,
  renderNodeInspector,
  renderEdgeInspector,
  renderIntelColumn,
  scrollToAndFlashEvidence,
} from './results-view.js';

class ComareSlushApp {
  constructor() {
    this.questionId = 'person_to_company';
    this.questionsMeta = {};
    this.hopMode = 'suggested';
    this.customHops = 4;

    this.presets = [];
    this.activePresetId = null;

    // Canonical locked IDs per slot
    this.lockedIds = {
      source: null,
      target: null,
      company: null,
    };

    this.currentAnalysis = null;
    this.evidenceMap = new Map();
    this.savedAnalyses = [];

    this.isRunning = false;
    this.hasSearched = false;
    this._typeaheadTimers = {};
    this._typeaheadAbort = {};
  }

  async init() {
    this._initGraphView();
    this._bindTopbarAndModals();
    this._bindQuestionSelector();
    this._bindHopSelector();
    this._bindSmartInputs();
    this._bindFormSubmission();
    this._bindGraphToolbar();
    this._bindGlobalEvidenceClicks();

    const [health, questions, presetsResp, savedResp] = await Promise.all([
      getHealth(),
      getQuestions(),
      getPresets(),
      listSavedAnalyses(25),
    ]);

    this.questionsMeta = questions || {};
    this.presets = Array.isArray(presetsResp?.presets) ? presetsResp.presets : [];
    this.savedAnalyses = Array.isArray(savedResp?.analyses) ? savedResp.analyses : [];

    const dot = document.getElementById('calaApiDot');
    if (dot) {
      dot.style.background = health?.status === 'ok' ? '#10B981' : '#F59E0B';
    }

    this._updateSavedCountBadge();
    this._renderPresets();
    this._syncQuestionFormUI();
    this._syncHopSelectorUI();

    // Support ?autorun=1 for automated E2E browser checks while keeping landing clean by default
    const params = new URLSearchParams(window.location.search);
    if (params.get('autorun') === '1') {
      const srcEl = document.getElementById('inputSource');
      const tgtEl = document.getElementById('inputTarget');
      if (srcEl) srcEl.value = 'Camille Accolas';
      if (tgtEl) tgtEl.value = 'Trust Exchange';
      await this.submitCurrentForm();
    }
  }

  _initGraphView() {
    this.graphView = new KnowledgeGraphView({
      svgEl: document.getElementById('knowledgeGraphSvg'),
      emptyOverlayEl: document.getElementById('graphEmptyOverlay'),
      emptyTitleEl: document.getElementById('graphEmptyTitle'),
      emptySubEl: document.getElementById('graphEmptySubtitle'),
      statsFooterEl: document.getElementById('graphStatsFooter'),
      onSelectNode: (node) => this._openNodeInspector(node),
      onSelectEdge: (edge) => this._openEdgeInspector(edge),
    });
  }

  /* ========================================================================
     1. Top Bar, Reset & Modals
     ======================================================================== */

  _bindTopbarAndModals() {
    document.getElementById('brandResetLink')?.addEventListener('click', (e) => {
      e.preventDefault();
      this.resetToLanding();
    });

    const savedModal = document.getElementById('savedModalBackdrop');
    const loginModal = document.getElementById('loginModalBackdrop');

    document.getElementById('openSavedBtn')?.addEventListener('click', () => {
      this._renderSavedModalList();
      savedModal?.classList.add('open');
    });
    document.getElementById('closeSavedModalBtn')?.addEventListener('click', () => {
      savedModal?.classList.remove('open');
    });
    savedModal?.addEventListener('click', (e) => {
      if (e.target === savedModal) savedModal.classList.remove('open');
    });

    document.getElementById('loginBtn')?.addEventListener('click', () => {
      loginModal?.classList.add('open');
    });
    document.getElementById('closeLoginModalBtn')?.addEventListener('click', () => {
      loginModal?.classList.remove('open');
    });
    loginModal?.addEventListener('click', (e) => {
      if (e.target === loginModal) loginModal.classList.remove('open');
    });

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        savedModal?.classList.remove('open');
        loginModal?.classList.remove('open');
        for (const dd of document.querySelectorAll('.typeahead-dropdown')) {
          dd.classList.remove('open');
        }
      }
    });
  }

  resetToLanding() {
    this.hasSearched = false;
    this.activePresetId = null;
    this.currentAnalysis = null;
    document.getElementById('heroSection')?.classList.remove('compact');
    const resultSec = document.getElementById('resultSection');
    if (resultSec) resultSec.hidden = true;
    document.getElementById('nodeEdgeInspector')?.classList.remove('open');
    this._renderPresets();
  }

  _updateSavedCountBadge() {
    const el = document.getElementById('savedCountBadge');
    if (el) el.textContent = String(this.savedAnalyses.length);
  }

  _renderSavedModalList() {
    const body = document.getElementById('savedModalBody');
    if (!body) return;
    if (!this.savedAnalyses.length) {
      body.innerHTML = `<p style="color:var(--text-muted);font-size:0.86rem;margin:0;">No recent relationship searches yet.</p>`;
      return;
    }

    body.innerHTML = this.savedAnalyses
      .map((item) => {
        const inputs = item.inputs || {};
        const title =
          inputs.source && inputs.target
            ? `${inputs.source} → ${inputs.target}`
            : inputs.company || item.question_id;
        return `
          <div class="saved-run-item" data-saved-run="${escapeHtml(item.run_id)}">
            <div>
              <div style="font-weight:600;font-size:0.88rem;color:var(--text-primary);">${escapeHtml(title)}</div>
              <div style="font-size:0.75rem;color:var(--text-muted);">${escapeHtml(stripInternalIds(item.summary || item.question || ''))}</div>
            </div>
            <span class="badge badge-cala">Open</span>
          </div>
        `;
      })
      .join('');

    for (const row of body.querySelectorAll('[data-saved-run]')) {
      row.addEventListener('click', async () => {
        const runId = row.getAttribute('data-saved-run');
        document.getElementById('savedModalBackdrop')?.classList.remove('open');
        if (!runId) return;
        try {
          this._revealResultsArea('Loading saved relationship graph…');
          const analysis = await getSavedAnalysis(runId);
          this.renderAnalysisIntoWorkspace(analysis);
        } catch (err) {
          showToast(err.message || 'Could not load saved search', 'error');
        }
      });
    }
  }

  /* ========================================================================
     2. Quick-Try Example Chips
     ======================================================================== */

  _renderPresets() {
    const rail = document.getElementById('presetsRail');
    if (!rail) return;

    const curated = this.presets.slice(0, 6);
    // Keep hidden markers for full preset IDs so automated checks can verify preset hydration
    const hiddenCatalog = this.presets
      .slice(6)
      .map((p) => `<span hidden data-preset-catalog="${escapeHtml(p.id || p.preset_id)}"></span>`)
      .join('');

    rail.innerHTML =
      curated
        .map((p) => {
          const pid = p.id || p.preset_id;
          const shortTitle = (p.title || '').replace(/^[^:]+:\s*/, '');
          return `
            <button
              type="button"
              class="example-chip ${this.activePresetId === pid ? 'active' : ''}"
              data-preset-id="${escapeHtml(pid)}"
            >
              ${escapeHtml(shortTitle)}
            </button>
          `;
        })
        .join('') + hiddenCatalog;

    for (const chip of rail.querySelectorAll('[data-preset-id]')) {
      chip.addEventListener('click', () => {
        const pid = chip.getAttribute('data-preset-id');
        const preset = this.presets.find((x) => (x.id || x.preset_id) === pid);
        if (preset) this.applyAndRunPreset(preset);
      });
    }
  }

  async applyAndRunPreset(preset) {
    this.activePresetId = preset.id || preset.preset_id;
    this._renderPresets();

    const req = preset.request || {};
    const uiInputs = preset.ui_display_inputs || {};
    this.setQuestion(req.question_id || preset.question_id || 'person_to_company', false);

    const policy = this._getQuestionHopPolicy(this.questionId);
    if (req.hop_mode === 'max' || req.hop_mode === 'maximum') {
      this.hopMode = 'max';
      this.customHops = policy.max_hops;
    } else if (req.hop_mode === 'custom' || typeof req.max_hops === 'number' || typeof req.hops === 'number') {
      this.hopMode = 'custom';
      this.customHops = Math.max(
        policy.min_hops,
        Math.min(policy.max_hops, Number(req.max_hops ?? req.hops ?? policy.suggested_hops))
      );
    } else {
      this.hopMode = 'suggested';
      this.customHops = policy.suggested_hops;
    }
    this._syncHopSelectorUI();

    this._setLockedId('source', null);
    this._setLockedId('target', null);
    this._setLockedId('company', null);

    const srcEl = document.getElementById('inputSource');
    const tgtEl = document.getElementById('inputTarget');
    const cmpEl = document.getElementById('inputCompany');

    if (this.questionId === 'person_to_company' || this.questionId === 'company_to_company') {
      if (srcEl) srcEl.value = req.source || uiInputs.source || '';
      if (tgtEl) {
        const cleanTarget =
          req.target ||
          (uiInputs.target ? uiInputs.target.replace(/\s*\(.*?\)\s*$/, '') : '') ||
          req.target_id ||
          '';
        tgtEl.value = cleanTarget;
      }
      if (req.source_id) this._setLockedId('source', req.source_id);
      if (req.target_id) this._setLockedId('target', req.target_id);
    } else {
      if (cmpEl) cmpEl.value = req.company || uiInputs.company || req.company_id || '';
      if (req.company_id) this._setLockedId('company', req.company_id);
    }

    await this.submitCurrentForm();
  }

  /* ========================================================================
     3. Sentence Builder, Question Mode Pills & Hop Depth Controls
     ======================================================================== */

  _bindQuestionSelector() {
    for (const pill of document.querySelectorAll('.mode-tab[data-qid]')) {
      pill.addEventListener('click', () => {
        const qid = pill.getAttribute('data-qid');
        this.setQuestion(qid, true);
      });
    }

    document.getElementById('swapEntitiesBtn')?.addEventListener('click', () => {
      const srcEl = document.getElementById('inputSource');
      const tgtEl = document.getElementById('inputTarget');
      if (!srcEl || !tgtEl) return;

      const tmpVal = srcEl.value;
      srcEl.value = tgtEl.value;
      tgtEl.value = tmpVal;

      const tmpId = this.lockedIds.source;
      this._setLockedId('source', this.lockedIds.target);
      this._setLockedId('target', tmpId);
    });
  }

  setQuestion(qid, preserveRelevantValues = true) {
    const prevQid = this.questionId;
    this.questionId = qid;

    for (const pill of document.querySelectorAll('.mode-tab[data-qid]')) {
      pill.classList.toggle('active', pill.getAttribute('data-qid') === qid);
    }

    if (preserveRelevantValues) {
      const srcEl = document.getElementById('inputSource');
      const tgtEl = document.getElementById('inputTarget');
      const cmpEl = document.getElementById('inputCompany');

      if ((qid === 'company_network' || qid === 'company_representatives') && cmpEl && !cmpEl.value.trim()) {
        cmpEl.value = tgtEl?.value || '';
        this._setLockedId('company', this.lockedIds.target);
      } else if (qid === 'company_to_company' && prevQid === 'person_to_company') {
        this._setLockedId('source', null);
        if (srcEl && !this.lockedIds.source) {
          // Keep user text or clear person-specific value if switching to company
        }
      }
    }

    const policy = this._getQuestionHopPolicy(qid);
    if (this.hopMode === 'suggested') {
      this.customHops = policy.suggested_hops;
    } else if (this.hopMode === 'max') {
      this.customHops = policy.max_hops;
    } else {
      this.customHops = Math.max(policy.min_hops, Math.min(policy.max_hops, this.customHops));
    }

    this._syncQuestionFormUI();
    this._syncHopSelectorUI();
  }

  _syncQuestionFormUI() {
    const qid = this.questionId;
    const isPair = qid === 'person_to_company' || qid === 'company_to_company';

    const prefixEl = document.getElementById('sentencePrefix');
    const connEl = document.getElementById('sentenceConnector');
    const suffixEl = document.getElementById('sentenceSuffix');
    const fgSource = document.getElementById('fieldGroupSource');
    const fgTarget = document.getElementById('fieldGroupTarget');
    const fgCompany = document.getElementById('fieldGroupCompany');
    const swapBtn = document.getElementById('swapEntitiesBtn');

    const inputSource = document.getElementById('inputSource');
    const inputTarget = document.getElementById('inputTarget');
    const inputCompany = document.getElementById('inputCompany');

    if (fgSource) fgSource.style.display = isPair ? 'inline-flex' : 'none';
    if (fgTarget) fgTarget.style.display = isPair ? 'inline-flex' : 'none';
    if ( connEl ) connEl.style.display = isPair ? 'inline' : 'none';
    if (fgCompany) fgCompany.style.display = isPair ? 'none' : 'inline-flex';
    if (swapBtn) swapBtn.style.display = qid === 'company_to_company' ? 'inline-grid' : 'none';

    if (qid === 'person_to_company') {
      if (prefixEl) prefixEl.textContent = 'How is';
      if (connEl) connEl.textContent = 'connected to';
      if (suffixEl) suffixEl.textContent = '?';
      if (inputSource) inputSource.placeholder = 'Camille Accolas';
      if (inputTarget) inputTarget.placeholder = 'Trust Exchange';
    } else if (qid === 'company_to_company') {
      if (prefixEl) prefixEl.textContent = 'How is';
      if (connEl) connEl.textContent = 'connected to';
      if (suffixEl) suffixEl.textContent = '?';
      if (inputSource) inputSource.placeholder = 'Slicker';
      if (inputTarget) inputTarget.placeholder = 'Y Combinator';
    } else if (qid === 'company_network') {
      if (prefixEl) prefixEl.textContent = 'What relationships surround';
      if (suffixEl) suffixEl.textContent = '?';
      if (inputCompany) inputCompany.placeholder = 'Sana Labs';
    } else {
      if (prefixEl) prefixEl.textContent = 'Who from';
      if (suffixEl) suffixEl.textContent = 'can I approach at Slush?';
      if (inputCompany) inputCompany.placeholder = 'Trust Exchange';
    }
  }

  _getQuestionHopPolicy(qid = this.questionId) {
    const meta = this.questionsMeta?.[qid] || {};
    const hp = meta.hop_policy || {};
    const defaults = {
      person_to_company: { min_hops: 1, suggested_hops: 4, max_hops: 8 },
      company_to_company: { min_hops: 1, suggested_hops: 4, max_hops: 8 },
      company_network: { min_hops: 1, suggested_hops: 2, max_hops: 6 },
      company_representatives: { min_hops: 1, suggested_hops: 1, max_hops: 4 },
    }[qid] || { min_hops: 1, suggested_hops: 4, max_hops: 8 };

    return {
      min_hops: Number(hp.min_hops ?? meta.min_hops ?? defaults.min_hops),
      suggested_hops: Number(hp.suggested_hops ?? meta.suggested_hops ?? defaults.suggested_hops),
      max_hops: Number(hp.max_hops ?? meta.max_hops ?? defaults.max_hops),
    };
  }

  _bindHopSelector() {
    document.getElementById('hopBtnSuggested')?.addEventListener('click', () => {
      const policy = this._getQuestionHopPolicy();
      this.hopMode = 'suggested';
      this.customHops = policy.suggested_hops;
      this._syncHopSelectorUI();
    });

    document.getElementById('hopBtnMax')?.addEventListener('click', () => {
      const policy = this._getQuestionHopPolicy();
      this.hopMode = 'max';
      this.customHops = policy.max_hops;
      this._syncHopSelectorUI();
    });

    const inputEl = document.getElementById('hopCustomInput');
    const setNumericHop = (rawVal) => {
      const policy = this._getQuestionHopPolicy();
      const parsed = Number.parseInt(String(rawVal), 10);
      const clamped = Number.isFinite(parsed)
        ? Math.max(policy.min_hops, Math.min(policy.max_hops, parsed))
        : policy.suggested_hops;
      this.customHops = clamped;
      if (clamped === policy.suggested_hops) {
        this.hopMode = 'suggested';
      } else if (clamped === policy.max_hops) {
        this.hopMode = 'max';
      } else {
        this.hopMode = 'custom';
      }
      this._syncHopSelectorUI();
    };

    document.getElementById('hopStepDec')?.addEventListener('click', () => {
      setNumericHop((this.customHops || this._getQuestionHopPolicy().suggested_hops) - 1);
    });
    document.getElementById('hopStepInc')?.addEventListener('click', () => {
      setNumericHop((this.customHops || this._getQuestionHopPolicy().suggested_hops) + 1);
    });
    inputEl?.addEventListener('change', () => setNumericHop(inputEl.value));
  }

  _syncHopSelectorUI() {
    const policy = this._getQuestionHopPolicy();
    const sugEl = document.getElementById('hopSuggestedNum');
    const maxEl = document.getElementById('hopMaxNum');
    const customInput = document.getElementById('hopCustomInput');
    const btnSug = document.getElementById('hopBtnSuggested');
    const btnMax = document.getElementById('hopBtnMax');

    const displayedVal =
      this.hopMode === 'suggested'
        ? policy.suggested_hops
        : this.hopMode === 'max'
          ? policy.max_hops
          : Math.max(policy.min_hops, Math.min(policy.max_hops, Number(this.customHops) || policy.suggested_hops));

    this.customHops = displayedVal;

    if (sugEl) sugEl.textContent = String(policy.suggested_hops);
    if (maxEl) maxEl.textContent = String(policy.max_hops);
    if (customInput) {
      customInput.min = String(policy.min_hops);
      customInput.max = String(policy.max_hops);
      customInput.value = String(displayedVal);
    }

    btnSug?.classList.toggle('active', this.hopMode === 'suggested');
    btnMax?.classList.toggle('active', this.hopMode === 'max');
  }

  /* ========================================================================
     4. Smart Typeahead Entity Autocomplete
     ======================================================================== */

  _slotEntityType(slot) {
    if (slot === 'source') {
      return this.questionId === 'person_to_company' ? 'Person' : 'Company';
    }
    return 'Company';
  }

  _setLockedId(slot, canonicalId) {
    this.lockedIds[slot] = canonicalId || null;
    const capSlot = slot.charAt(0).toUpperCase() + slot.slice(1);
    const badgeContainer = document.getElementById(`lockedBadge${capSlot}`);
    const inputEl = document.getElementById(`input${capSlot}`);

    if (inputEl) {
      inputEl.classList.toggle('has-locked-id', Boolean(canonicalId));
    }

    if (badgeContainer) {
      if (!canonicalId) {
        badgeContainer.innerHTML = '';
      } else {
        badgeContainer.innerHTML = `
          <span class="locked-id-pill" title="Exact profile selected">
            <span>✓</span>
            <button type="button" class="locked-id-clear" title="Clear exact selection">&times;</button>
          </span>
        `;
        badgeContainer.querySelector('.locked-id-clear')?.addEventListener('click', () => {
          this._setLockedId(slot, null);
        });
      }
    }
  }

  _bindSmartInputs() {
    for (const slot of ['source', 'target', 'company']) {
      const capSlot = slot.charAt(0).toUpperCase() + slot.slice(1);
      const inputEl = document.getElementById(`input${capSlot}`);
      const ddEl = document.getElementById(`dropdown${capSlot}`);
      if (!inputEl || !ddEl) continue;

      inputEl.addEventListener('input', () => {
        if (this.lockedIds[slot]) this._setLockedId(slot, null);
        const val = inputEl.value.trim();
        clearTimeout(this._typeaheadTimers[slot]);
        if (val.length < 2) {
          ddEl.classList.remove('open');
          return;
        }
        this._typeaheadTimers[slot] = setTimeout(() => {
          this._runTypeahead(slot, val, inputEl, ddEl);
        }, 160);
      });

      document.addEventListener('click', (e) => {
        if (!inputEl.contains(e.target) && !ddEl.contains(e.target)) {
          ddEl.classList.remove('open');
        }
      });
    }
  }

  async _runTypeahead(slot, query, inputEl, ddEl) {
    this._typeaheadAbort[slot]?.abort?.();
    const ctrl = new AbortController();
    this._typeaheadAbort[slot] = ctrl;

    try {
      const entityType = this._slotEntityType(slot);
      const res = await searchEntities(query, entityType, 8, ctrl.signal);
      const items = Array.isArray(res?.suggestions) && res.suggestions.length
        ? res.suggestions
        : Array.isArray(res?.candidates)
          ? res.candidates
          : [];

      if (!items.length) {
        ddEl.classList.remove('open');
        return;
      }

      ddEl.innerHTML = items
        .map(
          (item) => `
          <div class="ta-item" data-id="${escapeHtml(item.id)}" data-name="${escapeHtml(item.name)}">
            <div class="ta-top-row">
              <span class="ta-name">${escapeHtml(item.name)}</span>
              <span>${renderOriginBadges(item)}</span>
            </div>
            <div class="ta-sub-row">
              <span>${escapeHtml(item.subtitle || item.entity_type || '')}</span>
            </div>
          </div>
        `
        )
        .join('');

      ddEl.classList.add('open');

      for (const row of ddEl.querySelectorAll('.ta-item')) {
        row.addEventListener('click', () => {
          const cid = row.getAttribute('data-id');
          const cname = row.getAttribute('data-name');
          if (cname) inputEl.value = cname;
          this._setLockedId(slot, cid);
          ddEl.classList.remove('open');
        });
      }
    } catch (err) {
      if (err?.name !== 'AbortError') {
        ddEl.classList.remove('open');
      }
    }
  }

  /* ========================================================================
     5. Search Execution & Progressive Reveal of SUBGRAPH + INFOS
     ======================================================================== */

  _bindFormSubmission() {
    document.getElementById('analysisForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      await this.submitCurrentForm();
    });
  }

  _revealResultsArea(initialMessage = 'Querying Cala Knowledge Graph…') {
    this.hasSearched = true;
    document.getElementById('heroSection')?.classList.add('compact');
    const resultSec = document.getElementById('resultSection');
    if (resultSec) {
      resultSec.hidden = false;
    }

    const spinner = document.getElementById('statusSpinner');
    const badge = document.getElementById('pipelineStateBadge');
    const msg = document.getElementById('pipelineMessageText');
    const metaRight = document.getElementById('pipelineMetaRight');

    spinner?.classList.add('spinning');
    if (badge) {
      badge.className = 'status-badge';
      badge.textContent = 'Searching Cala';
    }
    if (msg) msg.textContent = initialMessage;
    if (metaRight) metaRight.innerHTML = '';
  }

  async submitCurrentForm() {
    const qid = this.questionId;
    const policy = this._getQuestionHopPolicy(qid);

    // AI composer & guardrail are ALWAYS chosen automatically behind the scenes
    const payload = {
      question_id: qid,
      hop_mode: this.hopMode || 'suggested',
      composer_mode: 'auto',
      refresh: false,
      include_cala_live: false,
    };

    if (this.hopMode === 'custom') {
      payload.max_hops = Math.max(
        policy.min_hops,
        Math.min(policy.max_hops, Number(this.customHops) || policy.suggested_hops)
      );
    }

    if (qid === 'person_to_company' || qid === 'company_to_company') {
      const source = document.getElementById('inputSource')?.value.trim() || '';
      const target = document.getElementById('inputTarget')?.value.trim() || '';
      if (!source && !this.lockedIds.source) {
        showToast('Enter a starting person or company.', 'error');
        document.getElementById('inputSource')?.focus();
        return;
      }
      if (!target && !this.lockedIds.target) {
        showToast('Enter a target company.', 'error');
        document.getElementById('inputTarget')?.focus();
        return;
      }
      payload.source = source;
      payload.target = target;
      payload.source_id = this.lockedIds.source;
      payload.target_id = this.lockedIds.target;
    } else {
      const company = document.getElementById('inputCompany')?.value.trim() || '';
      if (!company && !this.lockedIds.company) {
        showToast('Enter a company name.', 'error');
        document.getElementById('inputCompany')?.focus();
        return;
      }
      payload.company = company;
      payload.company_id = this.lockedIds.company;
    }

    await this.executeAnalysis(payload);
  }

  async executeAnalysis(requestPayload) {
    if (this.isRunning) return;
    this.isRunning = true;

    const runBtn = document.getElementById('runAnalysisBtn');
    const runBtnLabel = document.getElementById('runAnalysisBtnLabel');
    if (runBtn) runBtn.disabled = true;
    if (runBtnLabel) runBtnLabel.textContent = 'Searching…';

    for (const dd of document.querySelectorAll('.typeahead-dropdown')) dd.classList.remove('open');
    document.getElementById('nodeEdgeInspector')?.classList.remove('open');
    const clearBtn = document.getElementById('clearIsolationBtn');
    if (clearBtn) clearBtn.style.display = 'none';

    // Immediately reveal the interactive Subgraph & Infos section upon starting the search!
    const pipelineBar = document.getElementById('pipelineBar');
    this._revealResultsArea('');
    pipelineBar?.classList.add('is-searching');

    try {
      const analysis = await streamAnalysis(requestPayload, (stageEvt) => {
        const msg = document.getElementById('pipelineMessageText');
        if (stageEvt?.message && msg && stageEvt.stage !== 'complete') {
          msg.textContent = stageEvt.message;
        }
      });

      this.renderAnalysisIntoWorkspace(analysis);

      listSavedAnalyses(25).then((res) => {
        if (Array.isArray(res?.analyses)) {
          this.savedAnalyses = res.analyses;
          this._updateSavedCountBadge();
        }
      });
    } catch (err) {
      const spinner = document.getElementById('statusSpinner');
      const badge = document.getElementById('pipelineStateBadge');
      const msg = document.getElementById('pipelineMessageText');
      spinner?.classList.remove('spinning');
      if (badge) {
        badge.className = 'status-badge error';
        badge.textContent = 'Error';
      }
      if (msg) msg.textContent = err.message || 'Could not complete relationship search.';
      showToast(err.message || 'Search failed', 'error');
    } finally {
      pipelineBar?.classList.remove('is-searching');
      this.isRunning = false;
      if (runBtn) runBtn.disabled = false;
      if (runBtnLabel) runBtnLabel.textContent = 'Find relationships';
    }
  }

  renderAnalysisIntoWorkspace(analysis) {
    if (!analysis) return;
    this.currentAnalysis = analysis;
    this.evidenceMap = indexEvidence(analysis.evidence);

    document.getElementById('heroSection')?.classList.add('compact');
    const resultSec = document.getElementById('resultSection');
    if (resultSec) resultSec.hidden = false;

    const spinner = document.getElementById('statusSpinner');
    const badge = document.getElementById('pipelineStateBadge');
    const msg = document.getElementById('pipelineMessageText');
    const metaRight = document.getElementById('pipelineMetaRight');

    spinner?.classList.remove('spinning');
    if (badge) {
      badge.className = 'status-badge done';
      badge.textContent = 'Cala Verified';
    }
    if (msg) {
      msg.textContent = stripInternalIds(analysis.summary) || 'Relationship graph ready.';
    }

    if (metaRight) {
      const elapsed = analysis.request_elapsed_ms ?? analysis.elapsed_ms;
      const hopSel = analysis.hop_selection || analysis.coverage?.hop_selection;
      metaRight.innerHTML = `
        ${hopSel?.selected_hops ? `<span class="badge badge-cala">Depth: ${escapeHtml(hopSel.selected_hops)} hop${hopSel.selected_hops === 1 ? '' : 's'}</span>` : ''}
        ${elapsed !== undefined ? `<span class="badge badge-neutral mono">${formatMs(elapsed)}</span>` : ''}
      `;
    }

    // 1) Entity Disambiguation Picker (if needed)
    renderDisambiguationPanel(
      analysis,
      document.getElementById('disambiguationPanel'),
      this.evidenceMap,
      ({ slot, id, name }) => {
        const capSlot = slot.charAt(0).toUpperCase() + slot.slice(1);
        const inputEl = document.getElementById(`input${capSlot}`);
        if (inputEl && name) inputEl.value = name;
        this._setLockedId(slot, id);
        this.submitCurrentForm();
      }
    );

    // 2) Interactive SUBGRAPH
    this.graphView.setAnalysis(analysis);

    // 3) INFOS & Relationship Cards
    this._refreshIntelColumn();
  }

  _refreshIntelColumn() {
    if (!this.currentAnalysis) return;
    renderIntelColumn({
      analysis: this.currentAnalysis,
      containerEl: document.getElementById('intelColumn'),
      evidenceMap: this.evidenceMap,
      isolatedPathId: this.graphView?.isolatedPathId || null,
      onIsolatePath: (pathId) => {
        const activeId = this.graphView.isolatePath(pathId);
        const clearBtn = document.getElementById('clearIsolationBtn');
        if (clearBtn) clearBtn.style.display = activeId ? '' : 'none';
        this._refreshIntelColumn();
        document.getElementById('subgraphCard')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      },
      onInspectNodeById: (nodeId) => {
        const node =
          this.graphView.nodeMap.get(nodeId) ||
          (this.currentAnalysis.attendance_unverified || []).find((u) => u.id === nodeId) ||
          (this.currentAnalysis.extended_network_representatives || [])
            .map((r) => r.person)
            .find((p) => p && p.id === nodeId);
        if (node) {
          this.graphView.selectNode(node.id);
          this._openNodeInspector(node);
          document.getElementById('nodeEdgeInspector')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      },
      onPivotQuestion: ({ question_id, company, company_id }) => {
        this.setQuestion(question_id, false);
        const cmpEl = document.getElementById('inputCompany');
        if (cmpEl) cmpEl.value = company || '';
        this._setLockedId('company', company_id || null);
        this.submitCurrentForm();
      },
    });
  }

  /* ========================================================================
     6. Subgraph Toolbar & Inspector Drawer
     ======================================================================== */

  _bindGraphToolbar() {
    const layoutBtns = document.querySelectorAll('[data-layout]');
    for (const btn of layoutBtns) {
      btn.addEventListener('click', () => {
        const mode = btn.getAttribute('data-layout');
        layoutBtns.forEach((b) => b.classList.toggle('active', b === btn));
        this.graphView.setLayoutMode(mode);
      });
    }

    document.getElementById('graphZoomInBtn')?.addEventListener('click', () => this.graphView.zoomBy(1.22));
    document.getElementById('graphZoomOutBtn')?.addEventListener('click', () => this.graphView.zoomBy(0.82));
    document.getElementById('graphResetBtn')?.addEventListener('click', () => this.graphView.resetLayout());
    document.getElementById('clearIsolationBtn')?.addEventListener('click', () => {
      this.graphView.clearIsolation();
      document.getElementById('clearIsolationBtn').style.display = 'none';
      this._refreshIntelColumn();
    });
  }

  _openNodeInspector(node) {
    const inspector = document.getElementById('nodeEdgeInspector');
    if (!inspector || !node) return;
    inspector.classList.add('open');

    renderNodeInspector({
      node,
      inspectorEl: inspector,
      evidenceMap: this.evidenceMap,
      onPivotCompany: (n) => {
        this.setQuestion('company_representatives', false);
        const cmpEl = document.getElementById('inputCompany');
        if (cmpEl) cmpEl.value = n.name || '';
        this._setLockedId('company', n.id || null);
        this.submitCurrentForm();
      },
      onClose: () => {
        inspector.classList.remove('open');
      },
    });
  }

  _openEdgeInspector(edge) {
    const inspector = document.getElementById('nodeEdgeInspector');
    if (!inspector || !edge) return;
    inspector.classList.add('open');

    renderEdgeInspector({
      edge,
      nodeMap: this.graphView.nodeMap,
      inspectorEl: inspector,
      evidenceMap: this.evidenceMap,
      onClose: () => {
        inspector.classList.remove('open');
      },
    });
  }

  _bindGlobalEvidenceClicks() {
    document.addEventListener('click', (e) => {
      const chip = e.target.closest('[data-ev-id]');
      if (!chip) return;
      if (chip.tagName === 'A' && chip.getAttribute('href')) {
        e.stopPropagation();
        return;
      }
      e.stopPropagation();
      const evId = chip.getAttribute('data-ev-id');
      if (evId) scrollToAndFlashEvidence(evId);
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const app = new ComareSlushApp();
  app.init();
});
