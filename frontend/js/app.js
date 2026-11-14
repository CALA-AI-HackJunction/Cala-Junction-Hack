/**
 * Unicorn Radar — Main Application Controller (Zero-Build Native ES2022)
 * Coordinates Connection Explorer, Interactive Knowledge Graph, SSE Pipeline,
 * Smart Typeahead Resolution, Provenance Deep-Linking, and Partner Tech Views.
 */

import {
  escapeHtml,
  shortId,
  formatMs,
  indexEvidence,
  renderOriginBadges,
  renderCompletenessBadge,
  showToast,
  copyTextToClipboard,
} from './utils.js';

import {
  getHealth,
  getInfrastructureStatus,
  getQuestions,
  getPresets,
  getCoverage,
  searchEntities,
  streamAnalysis,
  listSavedAnalyses,
  getSavedAnalysis,
  getAnalysisPrompt,
  enrichCalaEntity,
  getCraciProvenance,
  runCraciAudit,
} from './api.js';

import { KnowledgeGraphView } from './graph-view.js';
import {
  renderDisambiguationPanel,
  renderNodeInspector,
  renderEdgeInspector,
  renderIntelColumn,
  scrollToAndFlashEvidence,
} from './results-view.js';
import {
  renderHistoryView,
  renderCraciView,
  renderCoverageView,
} from './tech-views.js';

const ORDERED_STAGES = [
  'resolving',
  'cache_check',
  'traversing',
  'ranking',
  'composing_gemini',
  'auditing_gemma',
  'persisting_aiven',
];

class UnicornRadarApp {
  constructor() {
    this.activeView = 'explorer';
    this.questionId = 'person_to_company';
    this.questionsMeta = {};
    this.presets = [];
    this.featuredInvestors = [];
    this.presetFilter = 'all';
    this.presetsExpanded = false;
    this.activePresetId = 'bench_01_camille_trust_exchange';

    // Canonical locked IDs per slot
    this.lockedIds = {
      source: null,
      target: null,
      company: null,
    };

    // Current loaded analysis state
    this.currentAnalysis = null;
    this.evidenceMap = new Map();
    this.calaEnrichmentCache = new Map();

    // Cached partner view payloads
    this.infraStatus = null;
    this.savedAnalyses = [];
    this.coverageData = null;
    this.craciProvenance = null;
    this.lastCraciAudit = null;
    this.lastPromptPayload = null;

    this.isRunning = false;
    this._typeaheadTimers = {};
    this._typeaheadAbort = {};
  }

  async init() {
    this._initGraphView();
    this._bindGlobalNavigation();
    this._bindQuestionSelector();
    this._bindSmartInputs();
    this._bindFormSubmission();
    this._bindGraphToolbar();
    this._bindModalAndGlobalShortcuts();

    // Parallel boot hydration of health, infrastructure, questions, presets, saved runs
    const [health, infra, questions, presetsResp, savedResp] = await Promise.all([
      getHealth(),
      getInfrastructureStatus(),
      getQuestions(),
      getPresets(),
      listSavedAnalyses(30),
    ]);

    this.infraStatus = infra;
    this.questionsMeta = questions || {};
    this.presets = Array.isArray(presetsResp?.presets) ? presetsResp.presets : [];
    this.featuredInvestors = Array.isArray(presetsResp?.featured_cala_verified_slush_investors)
      ? presetsResp.featured_cala_verified_slush_investors
      : [];
    this.savedAnalyses = Array.isArray(savedResp?.analyses) ? savedResp.analyses : [];

    this._updateCapabilityStrip(health, infra);
    this._updateSavedCountBadge();
    this._renderPresets();
    this._syncQuestionFormUI();

    // Run flagship default verified query on boot so workspace is immediately rich & interactive
    await this.executeAnalysis({
      question_id: 'person_to_company',
      source: 'Camille Accolas',
      target: 'Trust Exchange',
      composer_mode: document.getElementById('composerModeSelect')?.value || 'auto',
      refresh: false,
      include_cala_live: false,
    });
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
     1. Navigation & Partner Capability Pills
     ======================================================================== */

  _bindGlobalNavigation() {
    for (const btn of document.querySelectorAll('.nav-tab[data-view]')) {
      btn.addEventListener('click', () => {
        const view = btn.getAttribute('data-view');
        this.switchView(view);
      });
    }

    for (const pill of document.querySelectorAll('.cap-pill[data-goto-view]')) {
      pill.addEventListener('click', () => {
        const target = pill.getAttribute('data-goto-view');
        if (target) this.switchView(target);
      });
    }
  }

  async switchView(viewName) {
    this.activeView = viewName;
    for (const btn of document.querySelectorAll('.nav-tab[data-view]')) {
      const isAct = btn.getAttribute('data-view') === viewName;
      btn.classList.toggle('active', isAct);
      btn.setAttribute('aria-selected', String(isAct));
    }
    for (const sec of document.querySelectorAll('.view-section')) {
      sec.classList.toggle('active', sec.id === `view-${viewName}`);
    }

    if (viewName === 'explorer') {
      requestAnimationFrame(() => this.graphView?.fitToView());
    } else if (viewName === 'history') {
      await this._loadAndRenderHistoryView();
    } else if (viewName === 'craci') {
      await this._loadAndRenderCraciView();
    } else if (viewName === 'coverage') {
      await this._loadAndRenderCoverageView();
    }
  }

  _updateCapabilityStrip(health, infra) {
    const caps = health?.capabilities || {};
    const isOffline = health?.status === 'offline_fixture';

    // Cala Pill
    const capCala = document.getElementById('capCala');
    const capCalaLabel = document.getElementById('capCalaLabel');
    if (capCala && capCalaLabel) {
      capCala.className = `cap-pill cala ${isOffline ? 'fallback' : 'online'}`;
      capCalaLabel.textContent = caps.cala_live ? 'Cala Graph + /v1 Live' : 'Cala Graph · 933 Bridges';
    }

    // Gemini Pill
    const capGemini = document.getElementById('capGemini');
    const capGeminiLabel = document.getElementById('capGeminiLabel');
    if (capGemini && capGeminiLabel) {
      const on = Boolean(caps.gemini || infra?.models?.gemini?.configured);
      capGemini.className = `cap-pill ai ${on ? 'online' : 'fallback'}`;
      capGeminiLabel.textContent = on
        ? `Gemini · ${infra?.models?.gemini?.model || '2.5'}`
        : 'Gemini · Template Fallback';
    }

    // Gemma Pill
    const capGemma = document.getElementById('capGemma');
    const capGemmaLabel = document.getElementById('capGemmaLabel');
    if (capGemma && capGemmaLabel) {
      const on = Boolean(caps.gemma || infra?.models?.gemma?.configured);
      capGemma.className = `cap-pill ai ${on ? 'online' : 'fallback'}`;
      capGemmaLabel.textContent = on ? 'Gemma 3 Shield · Active' : 'Gemma 3 · Rule Guardrail';
    }

    // Aiven Pill
    const capAiven = document.getElementById('capAiven');
    const capAivenLabel = document.getElementById('capAivenLabel');
    if (capAiven && capAivenLabel) {
      const pgOn = Boolean(caps.aiven_pg || infra?.storage?.aiven_pg_connected);
      const vkOn = Boolean(caps.aiven_valkey || infra?.cache?.aiven_valkey_connected);
      capAiven.className = `cap-pill ${pgOn || vkOn ? 'online' : 'fallback'}`;
      if (pgOn && vkOn) {
        capAivenLabel.textContent = 'Aiven PG + Valkey Live';
      } else if (pgOn) {
        capAivenLabel.textContent = 'Aiven PG Live';
      } else if (vkOn) {
        capAivenLabel.textContent = 'Aiven Valkey Live';
      } else {
        capAivenLabel.textContent = 'Store · SQLite + LRU';
      }
    }

    // CRACI Pill
    const capCraci = document.getElementById('capCraci');
    const capCraciLabel = document.getElementById('capCraciLabel');
    if (capCraci && capCraciLabel) {
      capCraci.className = `cap-pill ${isOffline ? 'fallback' : 'online'}`;
      capCraciLabel.textContent = infra?.craci?.api_configured ? 'CRACI Live SBOM' : 'CRACI · CycloneDX 1.7';
    }
  }

  _updateSavedCountBadge() {
    const badge = document.getElementById('savedRunsCountBadge');
    if (badge) {
      const count = this.infraStatus?.storage?.saved_analyses_count ?? this.savedAnalyses.length;
      badge.textContent = String(count);
    }
  }

  /* ========================================================================
     2. Curated Demo Presets Strip & Filter Tabs
     ======================================================================== */

  _renderPresets() {
    const rail = document.getElementById('presetsRail');
    const filterBar = document.getElementById('presetFilterBar');
    const expandBtn = document.getElementById('togglePresetsExpandBtn');
    const expandLabel = document.getElementById('togglePresetsExpandLabel');
    if (!rail) return;

    if (filterBar && !filterBar.dataset.bound) {
      filterBar.dataset.bound = '1';
      for (const chip of filterBar.querySelectorAll('[data-filter]')) {
        chip.addEventListener('click', () => {
          this.presetFilter = chip.getAttribute('data-filter');
          for (const c of filterBar.querySelectorAll('[data-filter]')) {
            c.classList.toggle('active', c === chip);
          }
          this._renderPresets();
        });
      }
    }

    if (expandBtn && !expandBtn.dataset.bound) {
      expandBtn.dataset.bound = '1';
      expandBtn.addEventListener('click', () => {
        this.presetsExpanded = !this.presetsExpanded;
        rail.classList.toggle('expanded', this.presetsExpanded);
        if (expandLabel) {
          expandLabel.textContent = this.presetsExpanded
            ? 'Collapse Preset Grid'
            : `Expand All (${this.presets.length})`;
        }
      });
    }

    if (expandLabel && !this.presetsExpanded) {
      expandLabel.textContent = `Expand All (${this.presets.length})`;
    }

    const filtered = this.presets.filter((p) => {
      if (this.presetFilter === 'all') return true;
      const hops = p.verified_outcome?.top_path_hops;
      const status = p.expected_status;
      const qid = p.request?.question_id || p.question_id;
      const badge = (p.badge || '').toLowerCase();

      if (this.presetFilter === '1_2_hop') {
        return status === 'partial' && (hops === 1 || hops === 2 || badge.includes('1-hop') || badge.includes('2-hop'));
      }
      if (this.presetFilter === '3_4_hop') {
        return hops >= 3 || p.group === 'multi_hop_showcase' || badge.includes('3-hop') || badge.includes('4-hop');
      }
      if (this.presetFilter === 'slush_speakers') {
        return qid === 'company_representatives' || p.group === 'slush_speakers_showcase';
      }
      if (this.presetFilter === 'edge_cases') {
        return status === 'needs_resolution' || status === 'insufficient_data';
      }
      return true;
    });

    const qShort = {
      person_to_company: 'Q1',
      company_to_company: 'Q2',
      company_network: 'Q3',
      company_representatives: 'Q4',
    };

    rail.innerHTML = filtered
      .map((p) => {
        const pid = p.id || p.preset_id;
        const qid = p.request?.question_id || p.question_id;
        const badgeCls =
          p.expected_status === 'needs_resolution'
            ? 'warn'
            : p.expected_status === 'insufficient_data'
              ? 'negative'
              : '';
        return `
          <button type="button" class="preset-card ${this.activePresetId === pid ? 'active' : ''}" data-preset-id="${escapeHtml(pid)}">
            <div>
              <div class="preset-card-top">
                <span class="preset-badge ${badgeCls}">${escapeHtml(p.badge || p.group || 'Verified')}</span>
                <span class="preset-qtag">${escapeHtml(qShort[qid] || 'Q')}</span>
              </div>
              <div class="preset-title" style="margin-top:0.35rem;">${escapeHtml(p.title)}</div>
            </div>
            <div class="preset-desc">${escapeHtml(p.description || p.subtitle || '')}</div>
          </button>
        `;
      })
      .join('');

    for (const card of rail.querySelectorAll('[data-preset-id]')) {
      card.addEventListener('click', () => {
        const pid = card.getAttribute('data-preset-id');
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

    // Reset all locked IDs cleanly before populating preset
    this._setLockedId('source', null);
    this._setLockedId('target', null);
    this._setLockedId('company', null);

    const srcEl = document.getElementById('inputSource');
    const tgtEl = document.getElementById('inputTarget');
    const cmpEl = document.getElementById('inputCompany');

    if (this.questionId === 'person_to_company' || this.questionId === 'company_to_company') {
      if (srcEl) srcEl.value = req.source || uiInputs.source || '';
      if (tgtEl) {
        // Infer clean display name when preset supplies target_id without target text
        const cleanTargetText =
          req.target ||
          (uiInputs.target ? uiInputs.target.replace(/\s*\(.*?\)\s*$/, '') : '') ||
          req.target_id ||
          '';
        tgtEl.value = cleanTargetText;
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
     3. Question Selector & Smart Debounced Typeahead Inputs
     ======================================================================== */

  _bindQuestionSelector() {
    for (const card of document.querySelectorAll('.question-card[data-qid]')) {
      card.addEventListener('click', () => {
        const qid = card.getAttribute('data-qid');
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

    for (const card of document.querySelectorAll('.question-card[data-qid]')) {
      card.classList.toggle('active', card.getAttribute('data-qid') === qid);
    }

    if (preserveRelevantValues) {
      // Carry company name smoothly when switching between Q1/Q2 and Q3/Q4
      const srcEl = document.getElementById('inputSource');
      const tgtEl = document.getElementById('inputTarget');
      const cmpEl = document.getElementById('inputCompany');

      if ((qid === 'company_network' || qid === 'company_representatives') && cmpEl && !cmpEl.value.trim()) {
        cmpEl.value = tgtEl?.value || 'Trust Exchange';
        this._setLockedId('company', this.lockedIds.target);
      } else if (qid === 'company_to_company' && prevQid === 'person_to_company') {
        // Clear person source ID lock if switching source from Person -> Company
        this._setLockedId('source', null);
        if (srcEl && srcEl.value === 'Camille Accolas') {
          srcEl.value = 'Slicker';
        }
      }
    }

    this._syncQuestionFormUI();
  }

  _syncQuestionFormUI() {
    const qid = this.questionId;
    const isPair = qid === 'person_to_company' || qid === 'company_to_company';

    const fgSource = document.getElementById('fieldGroupSource');
    const fgTarget = document.getElementById('fieldGroupTarget');
    const fgCompany = document.getElementById('fieldGroupCompany');
    const swapBtn = document.getElementById('swapEntitiesBtn');

    if (fgSource) fgSource.style.display = isPair ? '' : 'none';
    if (fgTarget) fgTarget.style.display = isPair ? '' : 'none';
    if (fgCompany) fgCompany.style.display = isPair ? 'none' : '';
    if (swapBtn) swapBtn.style.display = qid === 'company_to_company' ? 'grid' : 'none';

    const labelSourceText = document.getElementById('labelSourceText');
    const tagSourceType = document.getElementById('tagSourceType');
    const inputSource = document.getElementById('inputSource');
    const inputTarget = document.getElementById('inputTarget');
    const inputCompany = document.getElementById('inputCompany');

    const meta = this.questionsMeta?.[qid] || {};
    if (qid === 'person_to_company') {
      if (labelSourceText) labelSourceText.textContent = 'Person';
      if (tagSourceType) tagSourceType.textContent = 'Person';
      if (inputSource) inputSource.placeholder = meta.placeholders?.source || 'e.g. Camille Accolas or Dani Penev';
      if (inputTarget) inputTarget.placeholder = meta.placeholders?.target || 'e.g. Trust Exchange or Y Combinator';
    } else if (qid === 'company_to_company') {
      if (labelSourceText) labelSourceText.textContent = 'Starting Company';
      if (tagSourceType) tagSourceType.textContent = 'Company';
      if (inputSource) inputSource.placeholder = meta.placeholders?.source || 'e.g. Slicker or Sana Labs';
      if (inputTarget) inputTarget.placeholder = meta.placeholders?.target || 'e.g. Y Combinator or Amplitude';
    } else if (inputCompany) {
      inputCompany.placeholder = meta.placeholders?.company || 'e.g. Trust Exchange, Planhat, General Catalyst...';
    }
  }

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
          <span class="locked-id-pill" title="Canonical ID locked: ${escapeHtml(canonicalId)}">
            <span>🔒 ${escapeHtml(shortId(canonicalId, 20))}</span>
            <button type="button" class="locked-id-clear" title="Unlock canonical ID">&times;</button>
          </span>
        `;
        badgeContainer.querySelector('.locked-id-clear')?.addEventListener('click', () => {
          this._setLockedId(slot, null);
        });
      }
    }
  }

  _bindSmartInputs() {
    const slots = ['source', 'target', 'company'];
    for (const slot of slots) {
      const capSlot = slot.charAt(0).toUpperCase() + slot.slice(1);
      const inputEl = document.getElementById(`input${capSlot}`);
      const dropdownEl = document.getElementById(`dropdown${capSlot}`);
      if (!inputEl || !dropdownEl) continue;

      inputEl.addEventListener('input', () => {
        // Typing manually unlocks previous canonical ID so plain-name queries work naturally
        if (this.lockedIds[slot]) {
          this._setLockedId(slot, null);
        }
        this.activePresetId = null;

        clearTimeout(this._typeaheadTimers[slot]);
        const val = inputEl.value.trim();
        if (val.length < 1) {
          dropdownEl.classList.remove('open');
          dropdownEl.innerHTML = '';
          return;
        }

        this._typeaheadTimers[slot] = setTimeout(() => {
          this._runTypeaheadLookup(slot, val, inputEl, dropdownEl);
        }, 180);
      });

      inputEl.addEventListener('keydown', (e) => {
        if (!dropdownEl.classList.contains('open')) return;
        const items = [...dropdownEl.querySelectorAll('.typeahead-item')];
        if (items.length === 0) return;
        const curIdx = items.findIndex((el) => el.classList.contains('highlighted'));

        if (e.key === 'ArrowDown') {
          e.preventDefault();
          const next = (curIdx + 1) % items.length;
          items.forEach((el, idx) => el.classList.toggle('highlighted', idx === next));
          items[next]?.scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          const prev = (curIdx - 1 + items.length) % items.length;
          items.forEach((el, idx) => el.classList.toggle('highlighted', idx === prev));
          items[prev]?.scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'Enter' && curIdx >= 0) {
          e.preventDefault();
          items[curIdx].click();
        } else if (e.key === 'Escape') {
          dropdownEl.classList.remove('open');
        }
      });
    }

    // Clear input buttons
    for (const btn of document.querySelectorAll('[data-clear-slot]')) {
      btn.addEventListener('click', () => {
        const slot = btn.getAttribute('data-clear-slot');
        const capSlot = slot.charAt(0).toUpperCase() + slot.slice(1);
        const inputEl = document.getElementById(`input${capSlot}`);
        const dropdownEl = document.getElementById(`dropdown${capSlot}`);
        if (inputEl) {
          inputEl.value = '';
          inputEl.focus();
        }
        if (dropdownEl) dropdownEl.classList.remove('open');
        this._setLockedId(slot, null);
      });
    }

    // Close typeahead dropdowns when clicking outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.field-group')) {
        for (const dd of document.querySelectorAll('.typeahead-dropdown')) {
          dd.classList.remove('open');
        }
      }
    });
  }

  async _runTypeaheadLookup(slot, queryText, inputEl, dropdownEl) {
    this._typeaheadAbort[slot]?.abort();
    const controller = new AbortController();
    this._typeaheadAbort[slot] = controller;

    try {
      const entityType = this._slotEntityType(slot);
      const data = await searchEntities(queryText, entityType, 12, controller.signal);

      // Merge suggestions[] or fallback to candidates[] / entity
      let list = Array.isArray(data?.suggestions) && data.suggestions.length > 0
        ? data.suggestions
        : Array.isArray(data?.candidates) && data.candidates.length > 0
          ? data.candidates
          : data?.entity
            ? [data.entity]
            : [];

      if (list.length === 0) {
        dropdownEl.classList.remove('open');
        dropdownEl.innerHTML = '';
        return;
      }

      dropdownEl.innerHTML = list
        .map((item) => {
          const degreeTxt =
            item.traversable_degree !== undefined
              ? `${item.traversable_degree} verified link${item.traversable_degree === 1 ? '' : 's'}`
              : '';
          const sub = item.subtitle || degreeTxt || item.entity_type || '';
          return `
            <button
              type="button"
              class="typeahead-item"
              data-ta-id="${escapeHtml(item.id)}"
              data-ta-name="${escapeHtml(item.name)}"
            >
              <div class="ta-top-row">
                <span class="ta-name">${escapeHtml(item.name)}</span>
                <span class="ta-badges">
                  <span class="badge badge-neutral">${escapeHtml(item.entity_type || entityType)}</span>
                  ${renderOriginBadges(item)}
                  ${renderCompletenessBadge(item.record_completeness)}
                </span>
              </div>
              <div class="ta-sub-row">
                <span>${escapeHtml(sub)}</span>
                <span class="ta-id">${escapeHtml(shortId(item.id, 22))}</span>
              </div>
            </button>
          `;
        })
        .join('');

      dropdownEl.classList.add('open');

      for (const opt of dropdownEl.querySelectorAll('.typeahead-item')) {
        opt.addEventListener('click', () => {
          const chosenId = opt.getAttribute('data-ta-id');
          const chosenName = opt.getAttribute('data-ta-name');
          inputEl.value = chosenName || '';
          this._setLockedId(slot, chosenId);
          dropdownEl.classList.remove('open');
        });
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        dropdownEl.classList.remove('open');
      }
    }
  }

  /* ========================================================================
     4. Form Submission & Live Multi-Stage SSE Execution
     ======================================================================== */

  _bindFormSubmission() {
    const form = document.getElementById('analysisForm');
    form?.addEventListener('submit', async (e) => {
      e.preventDefault();
      await this.submitCurrentForm();
    });
  }

  async submitCurrentForm() {
    const qid = this.questionId;
    const composerMode = document.getElementById('composerModeSelect')?.value || 'auto';
    const refresh = Boolean(document.getElementById('forceRefreshCheck')?.checked);
    const includeCalaLive = Boolean(document.getElementById('includeCalaLiveCheck')?.checked);

    const payload = {
      question_id: qid,
      composer_mode: composerMode,
      refresh,
      include_cala_live: includeCalaLive,
    };

    if (qid === 'person_to_company' || qid === 'company_to_company') {
      const source = document.getElementById('inputSource')?.value.trim() || '';
      const target = document.getElementById('inputTarget')?.value.trim() || '';
      if (!source && !this.lockedIds.source) {
        showToast('Please enter a starting person or company.', 'error');
        return;
      }
      if (!target && !this.lockedIds.target) {
        showToast('Please enter a target company.', 'error');
        return;
      }
      payload.source = source;
      payload.target = target;
      payload.source_id = this.lockedIds.source;
      payload.target_id = this.lockedIds.target;
    } else {
      const company = document.getElementById('inputCompany')?.value.trim() || '';
      if (!company && !this.lockedIds.company) {
        showToast('Please enter a company name.', 'error');
        return;
      }
      payload.company = company;
      payload.company_id = this.lockedIds.company;
    }

    await this.executeAnalysis(payload);
  }

  _resetPipelineUI() {
    const bar = document.getElementById('pipelineBar');
    const stateBadge = document.getElementById('pipelineStateBadge');
    const msgText = document.getElementById('pipelineMessageText');
    const metaRight = document.getElementById('pipelineMetaRight');

    bar?.classList.add('visible');
    if (stateBadge) {
      stateBadge.className = 'badge badge-cala';
      stateBadge.textContent = 'STREAMING';
    }
    if (msgText) msgText.textContent = 'Initializing zero-confabulation query pipeline…';
    if (metaRight) metaRight.innerHTML = '';

    for (const pill of document.querySelectorAll('#pipelineStagesGrid .stage-pill')) {
      pill.classList.remove('running', 'done', 'hit', 'skipped');
    }
  }

  _handlePipelineStageEvent(ev) {
    const stage = ev.stage;
    const msgText = document.getElementById('pipelineMessageText');
    const stateBadge = document.getElementById('pipelineStateBadge');

    if (ev.message && msgText) {
      msgText.textContent = ev.message;
    }

    if (stage === 'complete') {
      for (const pill of document.querySelectorAll('#pipelineStagesGrid .stage-pill')) {
        if (!pill.classList.contains('hit') && !pill.classList.contains('skipped')) {
          pill.classList.remove('running');
          pill.classList.add('done');
        }
      }
      if (stateBadge) {
        const isCached = Boolean(ev.analysis?.cached || ev.analysis?.storage_meta?.cached);
        stateBadge.className = `badge ${isCached ? 'badge-dual' : 'badge-cala'}`;
        stateBadge.textContent = isCached ? '⚡ CACHE HIT' : '✓ VERIFIED';
      }
      return;
    }

    const idx = ORDERED_STAGES.indexOf(stage);
    if (idx === -1) return;

    ORDERED_STAGES.forEach((stKey, i) => {
      const pill = document.querySelector(`#pipelineStagesGrid .stage-pill[data-stage="${stKey}"]`);
      if (!pill) return;
      if (i < idx) {
        if (!pill.classList.contains('hit') && !pill.classList.contains('skipped')) {
          pill.classList.remove('running');
          pill.classList.add('done');
        }
      } else if (i === idx) {
        pill.classList.remove('done');
        if (ev.status === 'hit') {
          pill.classList.remove('running');
          pill.classList.add('hit');
        } else if (ev.status === 'skipped') {
          pill.classList.remove('running');
          pill.classList.add('skipped');
        } else {
          pill.classList.add('running');
        }
      }
    });
  }

  async executeAnalysis(requestPayload) {
    if (this.isRunning) return;
    this.isRunning = true;

    const runBtn = document.getElementById('runAnalysisBtn');
    const runBtnLabel = document.getElementById('runAnalysisBtnLabel');
    if (runBtn) runBtn.disabled = true;
    if (runBtnLabel) runBtnLabel.textContent = 'Traversing Graph…';

    // Close open dropdowns & inspector
    for (const dd of document.querySelectorAll('.typeahead-dropdown')) dd.classList.remove('open');
    document.getElementById('nodeEdgeInspector')?.classList.remove('open');
    document.getElementById('clearIsolationBtn').style.display = 'none';

    this._resetPipelineUI();

    try {
      const analysis = await streamAnalysis(requestPayload, (stageEvt) => {
        this._handlePipelineStageEvent(stageEvt);
      });

      this.renderAnalysisIntoWorkspace(analysis);

      // Refresh lightweight saved count in background
      listSavedAnalyses(30).then((res) => {
        if (Array.isArray(res?.analyses)) {
          this.savedAnalyses = res.analyses;
          this._updateSavedCountBadge();
        }
      });
    } catch (err) {
      const stateBadge = document.getElementById('pipelineStateBadge');
      const msgText = document.getElementById('pipelineMessageText');
      if (stateBadge) {
        stateBadge.className = 'badge badge-warn';
        stateBadge.textContent = 'ERROR';
      }
      if (msgText) msgText.textContent = err.message || 'Analysis request failed';
      showToast(err.message || 'Request failed', 'error');
    } finally {
      this.isRunning = false;
      if (runBtn) runBtn.disabled = false;
      if (runBtnLabel) runBtnLabel.textContent = 'Run Verified Radar';
    }
  }

  renderAnalysisIntoWorkspace(analysis) {
    if (!analysis) return;
    this.currentAnalysis = analysis;
    this.evidenceMap = indexEvidence(analysis.evidence);

    // Update pipeline completion telemetry bar
    const pipelineBar = document.getElementById('pipelineBar');
    const msgText = document.getElementById('pipelineMessageText');
    const metaRight = document.getElementById('pipelineMetaRight');
    const stateBadge = document.getElementById('pipelineStateBadge');

    pipelineBar?.classList.add('visible');
    const isCached = Boolean(analysis.cached || analysis.storage_meta?.cached);
    const elapsed = analysis.request_elapsed_ms ?? analysis.elapsed_ms ?? analysis.storage_meta?.elapsed_ms;
    const cacheLayer = analysis.storage_meta?.cache_layer || 'cache';
    const storeBackend = analysis.storage_meta?.backend || 'store';

    if (stateBadge) {
      stateBadge.className = `badge ${isCached ? 'badge-dual' : 'badge-cala'}`;
      stateBadge.textContent = isCached ? `⚡ CACHED (${cacheLayer})` : '✓ VERIFIED RUN';
    }
    if (msgText) {
      msgText.textContent = analysis.summary || 'Analysis completed.';
    }

    if (metaRight) {
      metaRight.innerHTML = `
        <span class="badge badge-neutral mono">${formatMs(elapsed)}</span>
        <span class="badge badge-neutral">Store: ${escapeHtml(storeBackend)}</span>
        ${
          analysis.run_id
            ? `<button type="button" class="btn-ghost-sm mono" id="btnCopyRunId" title="Click to copy run_id">run:${escapeHtml(shortId(analysis.run_id, 12))}</button>
               <button type="button" class="btn-ghost-sm" id="btnInspectPromptTop" style="border-color:var(--ai-border);color:var(--ai-bright);">
                 Inspect Grounded LLM Prompt
               </button>`
            : ''
        }
      `;

      metaRight.querySelector('#btnCopyRunId')?.addEventListener('click', () => {
        copyTextToClipboard(analysis.run_id, `Copied run_id: ${analysis.run_id}`);
      });
      metaRight.querySelector('#btnInspectPromptTop')?.addEventListener('click', () => {
        this.openPromptModal(analysis.run_id);
      });
    }

    // 1) Disambiguation Panel (if needs_resolution / not_found)
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

    // 2) Interactive Knowledge Graph
    this.graphView.setAnalysis(analysis);

    // 3) Grounded Intelligence Column (Summary, Claims + Gemma, Slush Brief, Results, Evidence)
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
      },
      onInspectNodeById: (nodeId) => {
        const node =
          this.graphView.nodeMap.get(nodeId) ||
          (this.currentAnalysis.attendance_unverified || []).find((u) => u.id === nodeId);
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
     5. Graph Toolbar, Node/Edge Inspector & Live Cala /v1 Enrich
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
    document.getElementById('graphFitBtn')?.addEventListener('click', () => this.graphView.fitToView());
    document.getElementById('graphResetBtn')?.addEventListener('click', () => this.graphView.resetLayout());

    const clearIsoBtn = document.getElementById('clearIsolationBtn');
    clearIsoBtn?.addEventListener('click', () => {
      this.graphView.clearIsolation();
      clearIsoBtn.style.display = 'none';
      this._refreshIntelColumn();
    });
  }

  _openNodeInspector(node) {
    renderNodeInspector({
      node,
      inspectorEl: document.getElementById('nodeEdgeInspector'),
      evidenceMap: this.evidenceMap,
      enrichmentCacheMap: this.calaEnrichmentCache,
      onTriggerCalaEnrich: async (entityId) => {
        try {
          const payload = await enrichCalaEntity(entityId, false);
          this.calaEnrichmentCache.set(entityId, payload);
          return payload;
        } catch (err) {
          showToast(err.message || 'Live Cala /v1 request failed', 'error');
          return null;
        }
      },
      onPivotCompany: (companyNode) => {
        this.setQuestion('company_representatives', false);
        const cmpEl = document.getElementById('inputCompany');
        if (cmpEl) cmpEl.value = companyNode.name || '';
        this._setLockedId('company', companyNode.id);
        this.submitCurrentForm();
      },
      onClose: () => this.graphView.selectNode(null),
    });
  }

  _openEdgeInspector(edge) {
    renderEdgeInspector({
      edge,
      nodeMap: this.graphView.nodeMap,
      inspectorEl: document.getElementById('nodeEdgeInspector'),
      evidenceMap: this.evidenceMap,
      onClose: () => this.graphView.selectEdge(null),
    });
  }

  /* ========================================================================
     6. Partner Tech Challenge Views (History/Aiven, CRACI, Coverage)
     ======================================================================== */

  async _loadAndRenderHistoryView() {
    const container = document.getElementById('historyViewContainer');
    const [infra, saved] = await Promise.all([getInfrastructureStatus(), listSavedAnalyses(40)]);
    this.infraStatus = infra;
    this.savedAnalyses = Array.isArray(saved?.analyses) ? saved.analyses : [];
    this._updateSavedCountBadge();

    renderHistoryView({
      containerEl: container,
      infraStatus: this.infraStatus,
      analysesList: this.savedAnalyses,
      onRefresh: () => this._loadAndRenderHistoryView(),
      onRestoreRun: async (runId) => {
        try {
          const fullRun = await getSavedAnalysis(runId);
          this.switchView('explorer');
          // Sync form inputs to restored run
          const qid = fullRun.question_id || 'person_to_company';
          this.setQuestion(qid, false);
          const inp = fullRun.inputs || fullRun.original_request || {};
          if (qid === 'person_to_company' || qid === 'company_to_company') {
            document.getElementById('inputSource').value = inp.source || fullRun.resolved_entities?.source?.name || '';
            document.getElementById('inputTarget').value = inp.target || fullRun.resolved_entities?.target?.name || '';
            this._setLockedId('source', inp.source_id || null);
            this._setLockedId('target', inp.target_id || null);
          } else {
            document.getElementById('inputCompany').value = inp.company || fullRun.resolved_entities?.company?.name || '';
            this._setLockedId('company', inp.company_id || null);
          }
          this.renderAnalysisIntoWorkspace(fullRun);
          showToast(`Restored saved run ${shortId(runId, 12)} byte-for-byte.`);
        } catch (err) {
          showToast(err.message || 'Could not restore saved run', 'error');
        }
      },
      onInspectPrompt: (runId) => this.openPromptModal(runId),
    });
  }

  async _loadAndRenderCraciView() {
    const container = document.getElementById('craciViewContainer');
    if (!this.craciProvenance) {
      this.craciProvenance = await getCraciProvenance();
    }
    renderCraciView({
      containerEl: container,
      provenance: this.craciProvenance,
      lastAudit: this.lastCraciAudit,
      onRefreshProvenance: async () => {
        this.craciProvenance = await getCraciProvenance();
        await this._loadAndRenderCraciView();
      },
      onRunAudit: async () => {
        try {
          const mode = document.getElementById('composerModeSelect')?.value || 'auto';
          const audit = await runCraciAudit({ composer_mode: mode });
          this.lastCraciAudit = audit;
          return audit;
        } catch (err) {
          showToast(err.message || 'Supply-chain audit failed', 'error');
          return null;
        }
      },
      onPivotEntity: ({ name, id }) => {
        this.switchView('explorer');
        this.setQuestion('company_network', false);
        const cmpEl = document.getElementById('inputCompany');
        if (cmpEl) cmpEl.value = name || '';
        this._setLockedId('company', id || null);
        this.submitCurrentForm();
      },
    });
  }

  async _loadAndRenderCoverageView() {
    const container = document.getElementById('coverageViewContainer');
    if (!this.coverageData) {
      this.coverageData = await getCoverage();
    }
    renderCoverageView({
      containerEl: container,
      coverage: this.coverageData,
      featuredInvestors: this.featuredInvestors,
      onExploreInvestor: ({ question_id, company, company_id }) => {
        this.switchView('explorer');
        this.setQuestion(question_id, false);
        const cmpEl = document.getElementById('inputCompany');
        if (cmpEl) cmpEl.value = company || '';
        this._setLockedId('company', company_id || null);
        this.submitCurrentForm();
      },
    });
  }

  /* ========================================================================
     7. Grounded LLM Prompt Modal & Global Click/Keyboard Delegation
     ======================================================================== */

  async openPromptModal(runId) {
    if (!runId) return;
    const backdrop = document.getElementById('promptModalBackdrop');
    const body = document.getElementById('promptModalBody');
    if (!backdrop || !body) return;

    backdrop.classList.add('open');
    body.innerHTML = `<div style="padding:1rem;color:var(--text-muted);">Loading grounded prompt package for <code>${escapeHtml(runId)}</code>…</div>`;

    try {
      const promptPkg = await getAnalysisPrompt(runId);
      this.lastPromptPayload = promptPkg;
      body.innerHTML = `
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.85rem;">
          <span class="badge badge-ai">Prompt Version: ${escapeHtml(promptPkg.prompt_version || 'v2')}</span>
          <span class="badge badge-cala">Run ID: ${escapeHtml(runId)}</span>
          <span class="badge badge-dual">Strict Evidence-ID Constrained</span>
        </div>

        <div style="margin-bottom:0.95rem;">
          <div class="section-eyebrow" style="margin-bottom:0.35rem;">System Guardrail Instructions</div>
          <pre class="code-block">${escapeHtml(promptPkg.system || JSON.stringify(promptPkg, null, 2))}</pre>
        </div>

        <div style="margin-bottom:0.95rem;">
          <div class="section-eyebrow" style="margin-bottom:0.35rem;">Grounded Subgraph &amp; Evidence Context Sent to Model</div>
          <pre class="code-block">${escapeHtml(JSON.stringify(promptPkg.input || {}, null, 2))}</pre>
        </div>

        ${
          promptPkg.response_schema
            ? `<div>
                <div class="section-eyebrow" style="margin-bottom:0.35rem;">Enforced Output JSON Schema</div>
                <pre class="code-block">${escapeHtml(JSON.stringify(promptPkg.response_schema, null, 2))}</pre>
              </div>`
            : ''
        }
      `;
    } catch (err) {
      body.innerHTML = `<div class="honest-empty-banner"><div class="honest-empty-title">Prompt Package Unavailable</div><div>${escapeHtml(err.message || 'Could not load prompt for this run.')}</div></div>`;
    }
  }

  _bindModalAndGlobalShortcuts() {
    const backdrop = document.getElementById('promptModalBackdrop');
    document.getElementById('closePromptModalBtn')?.addEventListener('click', () => {
      backdrop?.classList.remove('open');
    });
    backdrop?.addEventListener('click', (e) => {
      if (e.target === backdrop) backdrop.classList.remove('open');
    });

    document.getElementById('copyPromptJsonBtn')?.addEventListener('click', () => {
      if (this.lastPromptPayload) {
        copyTextToClipboard(JSON.stringify(this.lastPromptPayload, null, 2), 'Copied Grounded Prompt JSON');
      }
    });

    // Global delegated click handler for ANY [ev:...] provenance chip across the entire UI
    document.addEventListener('click', (e) => {
      const chip = e.target.closest('.ev-chip[data-ev-id]');
      if (!chip) return;
      e.stopPropagation();
      const evId = chip.getAttribute('data-ev-id');
      if (this.activeView !== 'explorer') {
        this.switchView('explorer');
      }
      scrollToAndFlashEvidence(evId);
    });

    // Global Escape shortcut
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        backdrop?.classList.remove('open');
        for (const dd of document.querySelectorAll('.typeahead-dropdown')) {
          dd.classList.remove('open');
        }
      }
    });
  }
}

window.addEventListener('DOMContentLoaded', () => {
  const app = new UnicornRadarApp();
  window.__unicornRadar = app;
  app.init();
});
