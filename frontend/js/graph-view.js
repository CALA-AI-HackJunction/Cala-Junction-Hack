/**
 * Unicorn Radar — Pure SVG Interactive Knowledge Graph Engine (ES2022)
 * Zero external dependencies. Supports Path-Layered (Q1/Q2) and Radial/Force (Q3/Q4) layouts,
 * parallel multi-edge Bezier fan-out, true factual edge arrowheads, zoom/pan, node dragging,
 * and path isolation.
 */

import { detectOriginKind, humanizePredicate } from './utils.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

const COLORS = {
  cala: '#2563EB',
  slush: '#D97706',
  both: '#0D9488',
  personStroke: '#6D28D9',
  companyStroke: '#2563EB',
};

function createSvgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v !== undefined && v !== null) {
      el.setAttribute(k, String(v));
    }
  }
  return el;
}

function truncateLabel(text, max = 24) {
  const s = String(text || '');
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export class KnowledgeGraphView {
  constructor({ svgEl, emptyOverlayEl, emptyTitleEl, emptySubEl, statsFooterEl, onSelectNode, onSelectEdge }) {
    this.svg = svgEl;
    this.emptyOverlay = emptyOverlayEl;
    this.emptyTitle = emptyTitleEl;
    this.emptySub = emptySubEl;
    this.statsFooter = statsFooterEl;
    this.onSelectNode = onSelectNode;
    this.onSelectEdge = onSelectEdge;

    this.nodes = [];
    this.edges = [];
    this.paths = [];
    this.nodeMap = new Map();
    this.edgeMap = new Map();
    this.positions = new Map();

    this.questionId = 'person_to_company';
    this.resolvedEntities = {};
    this.layoutMode = 'auto'; // 'auto' | 'layered' | 'radial'
    this.isolatedPathId = null;
    this.selectedNodeId = null;
    this.selectedEdgeId = null;

    // Viewport transform (pan + zoom)
    this.transform = { x: 0, y: 0, scale: 1 };
    this._isPanning = false;
    this._panStart = { x: 0, y: 0 };
    this._draggingNodeId = null;
    this._dragMoved = false;

    this._initSvgStructure();
    this._bindInteractions();
  }

  _initSvgStructure() {
    this.svg.innerHTML = '';

    const defs = createSvgEl('defs');
    // Directional arrow markers for cala, slush, both
    for (const [key, color] of Object.entries({ cala: COLORS.cala, slush: COLORS.slush, both: COLORS.both })) {
      const marker = createSvgEl('marker', {
        id: `arrow-${key}`,
        viewBox: '0 0 10 10',
        refX: '9',
        refY: '5',
        markerWidth: '6.5',
        markerHeight: '6.5',
        orient: 'auto',
      });
      marker.appendChild(
        createSvgEl('path', {
          d: 'M 0 1.5 L 9.5 5 L 0 8.5 z',
          fill: color,
        })
      );
      defs.appendChild(marker);
    }

    // Subtle radial glow filter for focal nodes
    const glow = createSvgEl('filter', { id: 'focal-glow', x: '-40%', y: '-40%', width: '180%', height: '180%' });
    const blur = createSvgEl('feGaussianBlur', { stdDeviation: '3.5', result: 'coloredBlur' });
    const merge = createSvgEl('feMerge');
    merge.appendChild(createSvgEl('feMergeNode', { in: 'coloredBlur' }));
    merge.appendChild(createSvgEl('feMergeNode', { in: 'SourceGraphic' }));
    glow.appendChild(blur);
    glow.appendChild(merge);
    defs.appendChild(glow);

    this.svg.appendChild(defs);

    this.viewportGroup = createSvgEl('g', { class: 'graph-viewport' });
    this.edgesLayer = createSvgEl('g', { class: 'graph-edges-layer' });
    this.nodesLayer = createSvgEl('g', { class: 'graph-nodes-layer' });
    this.viewportGroup.appendChild(this.edgesLayer);
    this.viewportGroup.appendChild(this.nodesLayer);
    this.svg.appendChild(this.viewportGroup);
  }

  _bindInteractions() {
    // Wheel zoom centered on pointer
    this.svg.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        const rect = this.svg.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const factor = e.deltaY < 0 ? 1.13 : 0.88;
        this._zoomAtPoint(factor, mx, my);
      },
      { passive: false }
    );

    // Background pan start
    this.svg.addEventListener('pointerdown', (e) => {
      if (e.target === this.svg || e.target.closest('.graph-viewport') === null) {
        this._isPanning = true;
        this._panStart = { x: e.clientX - this.transform.x, y: e.clientY - this.transform.y };
        this.svg.setPointerCapture?.(e.pointerId);
      }
    });

    window.addEventListener('pointermove', (e) => {
      if (this._draggingNodeId) {
        const rect = this.svg.getBoundingClientRect();
        const wx = (e.clientX - rect.left - this.transform.x) / this.transform.scale;
        const wy = (e.clientY - rect.top - this.transform.y) / this.transform.scale;
        const prev = this.positions.get(this._draggingNodeId);
        if (prev && (Math.abs(prev.x - wx) > 2 || Math.abs(prev.y - wy) > 2)) {
          this._dragMoved = true;
        }
        this.positions.set(this._draggingNodeId, { x: wx, y: wy });
        this._renderScene();
        return;
      }

      if (this._isPanning) {
        this.transform.x = e.clientX - this._panStart.x;
        this.transform.y = e.clientY - this._panStart.y;
        this._applyTransform();
      }
    });

    window.addEventListener('pointerup', () => {
      this._isPanning = false;
      this._draggingNodeId = null;
    });
  }

  _zoomAtPoint(factor, cx, cy) {
    const nextScale = Math.min(2.6, Math.max(0.28, this.transform.scale * factor));
    const ratio = nextScale / this.transform.scale;
    this.transform.x = cx - (cx - this.transform.x) * ratio;
    this.transform.y = cy - (cy - this.transform.y) * ratio;
    this.transform.scale = nextScale;
    this._applyTransform();
  }

  zoomBy(factor) {
    const rect = this.svg.getBoundingClientRect();
    this._zoomAtPoint(factor, rect.width / 2, rect.height / 2);
  }

  _applyTransform() {
    this.viewportGroup.setAttribute(
      'transform',
      `translate(${this.transform.x.toFixed(1)}, ${this.transform.y.toFixed(1)}) scale(${this.transform.scale.toFixed(3)})`
    );
  }

  setLayoutMode(mode) {
    this.layoutMode = mode;
    this._computePositions();
    this._renderScene();
    this.fitToView();
  }

  setAnalysis(analysis) {
    this.isolatedPathId = null;
    this.selectedNodeId = null;
    this.selectedEdgeId = null;

    this.questionId = analysis?.question_id || 'person_to_company';
    this.resolvedEntities = analysis?.resolved_entities || {};

    const rawNodes = Array.isArray(analysis?.graph?.nodes) ? [...analysis.graph.nodes] : [];
    const seenIds = new Set(rawNodes.map((n) => n.id));

    // Include resolved focal entities on canvas even if 0 edges exist (e.g. Trust Exchange <-> Slicker honest no-path)
    for (const ent of Object.values(this.resolvedEntities)) {
      if (ent && ent.id && !seenIds.has(ent.id)) {
        rawNodes.push(ent);
        seenIds.add(ent.id);
      }
    }

    this.nodes = rawNodes;
    this.edges = Array.isArray(analysis?.graph?.edges) ? analysis.graph.edges : [];
    this.paths = Array.isArray(analysis?.graph?.paths) ? analysis.graph.paths : [];

    this.nodeMap = new Map(this.nodes.map((n) => [n.id, n]));
    this.edgeMap = new Map(this.edges.map((e) => [e.id, e]));

    if (this.statsFooter) {
      this.statsFooter.textContent = `${this.nodes.length} node${this.nodes.length === 1 ? '' : 's'} · ${this.edges.length} verified edge${this.edges.length === 1 ? '' : 's'} · ${this.paths.length} path${this.paths.length === 1 ? '' : 's'}`;
    }

    // Show honest overlay only when there are zero nodes at all
    if (this.emptyOverlay) {
      if (this.nodes.length === 0) {
        this.emptyOverlay.classList.add('visible');
        if (this.emptyTitle) {
          this.emptyTitle.textContent =
            analysis?.status === 'needs_resolution'
              ? 'Select a Canonical Entity Above to Render Subgraph'
              : 'No Resolved Subgraph Entities';
        }
        if (this.emptySub) {
          this.emptySub.textContent =
            analysis?.summary ||
            'Ambiguous names are never silently merged. Pick the exact entity record to traverse verified connections.';
        }
      } else {
        this.emptyOverlay.classList.remove('visible');
      }
    }

    this._computePositions();
    this._renderScene();
    requestAnimationFrame(() => this.fitToView());
  }

  resetLayout() {
    this._computePositions();
    this._renderScene();
    this.fitToView();
  }

  isolatePath(pathId) {
    this.isolatedPathId = this.isolatedPathId === pathId ? null : pathId;
    this._updateHighlighting();
    return this.isolatedPathId;
  }

  clearIsolation() {
    this.isolatedPathId = null;
    this._updateHighlighting();
  }

  selectNode(nodeId) {
    this.selectedNodeId = nodeId;
    this.selectedEdgeId = null;
    this._updateHighlighting();
  }

  selectEdge(edgeId) {
    this.selectedEdgeId = edgeId;
    this.selectedNodeId = null;
    this._updateHighlighting();
  }

  _effectiveLayout() {
    if (this.layoutMode === 'layered' || this.layoutMode === 'radial') {
      return this.layoutMode;
    }
    return this.questionId === 'company_network' || this.questionId === 'company_representatives'
      ? 'radial'
      : 'layered';
  }

  _computePositions() {
    this.positions.clear();
    if (this.nodes.length === 0) return;

    const rect = this.svg.getBoundingClientRect();
    const width = Math.max(rect.width || 720, 520);
    const height = Math.max(rect.height || 520, 420);

    const mode = this._effectiveLayout();
    if (mode === 'layered') {
      this._computeLayeredLayout(width, height);
    } else {
      this._computeRadialSpringLayout(width, height);
    }
  }

  _computeLayeredLayout(width, height) {
    const sourceId = this.resolvedEntities?.source?.id || this.resolvedEntities?.company?.id || this.nodes[0]?.id;
    const targetId = this.resolvedEntities?.target?.id || null;

    // Assign column indices using path positions first, then BFS hops
    const layerOf = new Map();
    let maxCols = 1;

    if (this.paths.length > 0) {
      const longestHop = Math.max(...this.paths.map((p) => (p.node_ids?.length || 2) - 1), 1);
      maxCols = longestHop;
      for (const p of this.paths) {
        const nids = p.node_ids || [];
        const denom = Math.max(nids.length - 1, 1);
        nids.forEach((nid, idx) => {
          const scaledCol = Math.round((idx / denom) * maxCols);
          if (!layerOf.has(nid)) {
            layerOf.set(nid, scaledCol);
          }
        });
      }
    }

    if (sourceId) layerOf.set(sourceId, 0);
    if (targetId && targetId !== sourceId) layerOf.set(targetId, Math.max(maxCols, 1));

    // Place any remaining nodes via undirected BFS from source
    const adj = new Map();
    for (const n of this.nodes) adj.set(n.id, []);
    for (const e of this.edges) {
      adj.get(e.source)?.push(e.target);
      adj.get(e.target)?.push(e.source);
    }

    const queue = sourceId ? [sourceId] : [];
    const dist = new Map(sourceId ? [[sourceId, 0]] : []);
    while (queue.length > 0) {
      const cur = queue.shift();
      for (const nb of adj.get(cur) || []) {
        if (!dist.has(nb)) {
          dist.set(nb, (dist.get(cur) || 0) + 1);
          queue.push(nb);
        }
      }
    }

    for (const n of this.nodes) {
      if (!layerOf.has(n.id)) {
        const d = dist.get(n.id) ?? 1;
        layerOf.set(n.id, Math.min(d, Math.max(maxCols, 1)));
      }
    }

    const cols = new Map();
    for (const n of this.nodes) {
      const c = layerOf.get(n.id) ?? 0;
      if (!cols.has(c)) cols.set(c, []);
      cols.get(c).push(n.id);
    }

    const sortedColKeys = [...cols.keys()].sort((a, b) => a - b);
    const colCount = sortedColKeys.length;
    const xPad = 115;
    const usableW = Math.max(width - xPad * 2, 260);
    const colSpacing = colCount > 1 ? Math.max(usableW / (colCount - 1), 185) : 0;

    sortedColKeys.forEach((colKey, colIdx) => {
      const members = cols.get(colKey);
      const x = colCount === 1 ? width / 2 : xPad + colIdx * colSpacing;
      const rowSpacing = Math.min(125, Math.max(88, (height - 120) / Math.max(members.length, 1)));
      const totalH = (members.length - 1) * rowSpacing;
      const startY = height / 2 - totalH / 2;

      members.forEach((nid, rIdx) => {
        this.positions.set(nid, { x, y: startY + rIdx * rowSpacing });
      });
    });
  }

  _computeRadialSpringLayout(width, height) {
    const cx = width / 2;
    const cy = height / 2;
    const centerId =
      this.resolvedEntities?.company?.id ||
      this.resolvedEntities?.source?.id ||
      this.nodes[0]?.id;

    // BFS distance from center
    const adj = new Map();
    for (const n of this.nodes) adj.set(n.id, []);
    for (const e of this.edges) {
      adj.get(e.source)?.push(e.target);
      adj.get(e.target)?.push(e.source);
    }

    const dist = new Map();
    if (centerId) {
      dist.set(centerId, 0);
      const q = [centerId];
      while (q.length > 0) {
        const u = q.shift();
        for (const v of adj.get(u) || []) {
          if (!dist.has(v)) {
            dist.set(v, (dist.get(u) || 0) + 1);
            q.push(v);
          }
        }
      }
    }

    const ring1 = [];
    const ring2 = [];
    for (const n of this.nodes) {
      if (n.id === centerId) {
        this.positions.set(n.id, { x: cx, y: cy });
      } else if ((dist.get(n.id) ?? 1) <= 1) {
        ring1.push(n.id);
      } else {
        ring2.push(n.id);
      }
    }

    const r1Radius = Math.max(165, ring1.length * 24);
    ring1.forEach((nid, i) => {
      const angle = (2 * Math.PI * i) / Math.max(ring1.length, 1) - Math.PI / 2;
      this.positions.set(nid, {
        x: cx + r1Radius * Math.cos(angle),
        y: cy + r1Radius * Math.sin(angle),
      });
    });

    const r2Radius = r1Radius + 145;
    ring2.forEach((nid, i) => {
      const angle = (2 * Math.PI * i) / Math.max(ring2.length, 1) - Math.PI / 4;
      this.positions.set(nid, {
        x: cx + r2Radius * Math.cos(angle),
        y: cy + r2Radius * Math.sin(angle),
      });
    });

    // Gentle spring/repulsion pass so labels never overlap
    const ids = this.nodes.map((n) => n.id);
    for (let iter = 0; iter < 36; iter++) {
      for (let i = 0; i < ids.length; i++) {
        for (let j = i + 1; j < ids.length; j++) {
          const a = this.positions.get(ids[i]);
          const b = this.positions.get(ids[j]);
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const d = Math.hypot(dx, dy) || 1;
          const minDist = 112;
          if (d < minDist) {
            const push = (minDist - d) * 0.35;
            const ux = dx / d;
            const uy = dy / d;
            if (ids[i] !== centerId) {
              a.x -= ux * push;
              a.y -= uy * push;
            }
            if (ids[j] !== centerId) {
              b.x += ux * push;
              b.y += uy * push;
            }
          }
        }
      }
    }
  }

  fitToView() {
    if (this.nodes.length === 0) return;
    const rect = this.svg.getBoundingClientRect();
    const vw = rect.width || 700;
    const vh = rect.height || 520;

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    for (const pos of this.positions.values()) {
      minX = Math.min(minX, pos.x - 95);
      maxX = Math.max(maxX, pos.x + 95);
      minY = Math.min(minY, pos.y - 68);
      maxY = Math.max(maxY, pos.y + 72);
    }

    const contentW = Math.max(maxX - minX, 220);
    const contentH = Math.max(maxY - minY, 180);
    const scale = Math.min(1.18, Math.max(0.38, Math.min((vw - 56) / contentW, (vh - 56) / contentH)));

    const centerContentX = (minX + maxX) / 2;
    const centerContentY = (minY + maxY) / 2;

    this.transform.scale = scale;
    this.transform.x = vw / 2 - centerContentX * scale;
    this.transform.y = vh / 2 - centerContentY * scale;
    this._applyTransform();
  }

  _renderScene() {
    this.edgesLayer.innerHTML = '';
    this.nodesLayer.innerHTML = '';

    // Honest visual separator when 2+ focal entities resolved with 0 professional bridges
    if (this.nodes.length >= 2 && this.edges.length === 0) {
      const pts = [...this.positions.values()];
      if (pts.length >= 2) {
        const mx = (pts[0].x + pts[pts.length - 1].x) / 2;
        const my = (pts[0].y + pts[pts.length - 1].y) / 2;
        const badgeGroup = createSvgEl('g');
        badgeGroup.appendChild(
          createSvgEl('rect', {
            x: mx - 132,
            y: my - 16,
            width: 264,
            height: 32,
            rx: 16,
            fill: 'rgba(220, 38, 38, 0.08)',
            stroke: 'rgba(220, 38, 38, 0.45)',
            'stroke-dasharray': '4 3',
          })
        );
        const txt = createSvgEl('text', {
          x: mx,
          y: my,
          fill: '#B91C1C',
          'font-family': 'JetBrains Mono, monospace',
          'font-size': '10.5',
          'font-weight': '600',
          'text-anchor': 'middle',
          'dominant-baseline': 'central',
        });
        txt.textContent = '∅ NO VERIFIED RELATIONSHIP PATH';
        badgeGroup.appendChild(txt);
        this.edgesLayer.appendChild(badgeGroup);
      }
    }

    // Group parallel edges between unordered pairs so multi-edges fan out cleanly
    const pairBuckets = new Map();
    for (const edge of this.edges) {
      const a = edge.source < edge.target ? edge.source : edge.target;
      const b = edge.source < edge.target ? edge.target : edge.source;
      const key = `${a}||${b}`;
      if (!pairBuckets.has(key)) pairBuckets.set(key, []);
      pairBuckets.get(key).push(edge);
    }

    for (const bucket of pairBuckets.values()) {
      const total = bucket.length;
      bucket.forEach((edge, idx) => {
        const p1 = this.positions.get(edge.source);
        const p2 = this.positions.get(edge.target);
        if (!p1 || !p2) return;

        const originKind = detectOriginKind(edge);
        const strokeColor = COLORS[originKind] || COLORS.cala;

        // Canonical perpendicular normal so parallel edges in opposite directions still separate
        const canonA = edge.source < edge.target ? p1 : p2;
        const canonB = edge.source < edge.target ? p2 : p1;
        const cdx = canonB.x - canonA.x;
        const cdy = canonB.y - canonA.y;
        const cLen = Math.hypot(cdx, cdy) || 1;
        const nx = -cdy / cLen;
        const ny = cdx / cLen;

        const offsetStep = 44;
        const curveOffset = (idx - (total - 1) / 2) * offsetStep;

        const mx = (p1.x + p2.x) / 2 + nx * curveOffset;
        const my = (p1.y + p2.y) / 2 + ny * curveOffset;

        // Shorten start & end points so arrowhead lands crisply at node boundary
        const startPad = 28;
        const endPad = 31;

        const sdx = mx - p1.x;
        const sdy = my - p1.y;
        const sLen = Math.hypot(sdx, sdy) || 1;
        const sx = p1.x + (sdx / sLen) * Math.min(startPad, sLen * 0.35);
        const sy = p1.y + (sdy / sLen) * Math.min(startPad, sLen * 0.35);

        const edx = p2.x - mx;
        const edy = p2.y - my;
        const eLen = Math.hypot(edx, edy) || 1;
        const ex = p2.x - (edx / eLen) * Math.min(endPad, eLen * 0.38);
        const ey = p2.y - (edy / eLen) * Math.min(endPad, eLen * 0.38);

        const dPath = `M ${sx.toFixed(1)} ${sy.toFixed(1)} Q ${mx.toFixed(1)} ${my.toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`;

        // Midpoint of quadratic Bezier at t=0.5
        const lx = 0.25 * sx + 0.5 * mx + 0.25 * ex;
        const ly = 0.25 * sy + 0.5 * my + 0.25 * ey;

        const g = createSvgEl('g', {
          class: 'g-edge-group',
          'data-edge-id': edge.id,
        });

        g.appendChild(createSvgEl('path', { class: 'g-edge-hit', d: dPath }));
        g.appendChild(
          createSvgEl('path', {
            class: 'g-edge-path',
            d: dPath,
            stroke: strokeColor,
            'marker-end': `url(#arrow-${originKind})`,
          })
        );

        const predLabel = truncateLabel(humanizePredicate(edge.type), 22);
        const pillW = Math.max(predLabel.length * 6.1 + 14, 54);
        g.appendChild(
          createSvgEl('rect', {
            class: 'g-edge-label-bg',
            x: (lx - pillW / 2).toFixed(1),
            y: (ly - 9.5).toFixed(1),
            width: pillW.toFixed(1),
            height: 19,
          })
        );

        const labelEl = createSvgEl('text', {
          class: 'g-edge-label-text',
          x: lx.toFixed(1),
          y: ly.toFixed(1),
        });
        labelEl.textContent = predLabel;
        g.appendChild(labelEl);

        g.addEventListener('click', (ev) => {
          ev.stopPropagation();
          this.selectEdge(edge.id);
          this.onSelectEdge?.(edge);
        });

        this.edgesLayer.appendChild(g);
      });
    }

    // Render Nodes
    const focalIds = new Set(
      Object.values(this.resolvedEntities)
        .filter(Boolean)
        .map((e) => e.id)
    );

    for (const node of this.nodes) {
      const pos = this.positions.get(node.id);
      if (!pos) continue;

      const isPerson = node.entity_type === 'Person';
      const isFocal = focalIds.has(node.id);
      const originKind = detectOriginKind(node);
      const borderColor =
        originKind === 'both'
          ? COLORS.both
          : originKind === 'slush'
            ? COLORS.slush
            : isPerson
              ? COLORS.personStroke
              : COLORS.companyStroke;

      const ng = createSvgEl('g', {
        class: 'g-node-group',
        'data-node-id': node.id,
        transform: `translate(${pos.x.toFixed(1)}, ${pos.y.toFixed(1)})`,
      });

      if (isFocal) {
        ng.appendChild(
          createSvgEl('circle', {
            r: 31,
            fill: 'none',
            stroke: borderColor,
            'stroke-width': '1.2',
            'stroke-dasharray': '3 3',
            opacity: '0.65',
          })
        );
      }

      if (isPerson) {
        ng.appendChild(
          createSvgEl('circle', {
            class: 'g-node-shape',
            r: 22,
            fill: '#FFFFFF',
            stroke: borderColor,
            'stroke-width': isFocal ? '2.8' : '2.1',
          })
        );
        // Crisp person silhouette glyph
        ng.appendChild(createSvgEl('circle', { cx: 0, cy: -4, r: 4.5, fill: borderColor }));
        ng.appendChild(
          createSvgEl('path', {
            d: 'M -8.5 9 C -8.5 3.5, 8.5 3.5, 8.5 9',
            fill: 'none',
            stroke: borderColor,
            'stroke-width': '2',
            'stroke-linecap': 'round',
          })
        );
      } else {
        ng.appendChild(
          createSvgEl('rect', {
            class: 'g-node-shape',
            x: -24,
            y: -21,
            width: 48,
            height: 42,
            rx: 10,
            fill: '#FFFFFF',
            stroke: borderColor,
            'stroke-width': isFocal ? '2.8' : '2.1',
          })
        );
        // Crisp company/VC building glyph
        ng.appendChild(
          createSvgEl('rect', {
            x: -8,
            y: -9,
            width: 16,
            height: 18,
            rx: 2,
            fill: 'none',
            stroke: borderColor,
            'stroke-width': '1.8',
          })
        );
        ng.appendChild(createSvgEl('line', { x1: -4, y1: -4, x2: 4, y2: -4, stroke: borderColor, 'stroke-width': '1.5' }));
        ng.appendChild(createSvgEl('line', { x1: -4, y1: 1, x2: 4, y2: 1, stroke: borderColor, 'stroke-width': '1.5' }));
      }

      // Slush participation mini-pip on top-right of node
      if (Array.isArray(node.participation) && node.participation.length > 0) {
        ng.appendChild(
          createSvgEl('circle', {
            cx: 17,
            cy: -16,
            r: 5.5,
            fill: COLORS.slush,
            stroke: '#FFFFFF',
            'stroke-width': '1.8',
          })
        );
      }

      const nameLabel = createSvgEl('text', {
        class: 'g-node-title',
        y: 36,
      });
      nameLabel.textContent = truncateLabel(node.name || node.id, 26);
      ng.appendChild(nameLabel);

      const subtitleStr =
        node.profile?.job_title ||
        (originKind === 'both' ? 'Cala + Slush' : originKind === 'slush' ? 'Slush 2026' : 'Cala Graph');
      const subLabel = createSvgEl('text', {
        class: 'g-node-sub',
        y: 49,
      });
      subLabel.textContent = truncateLabel(subtitleStr, 28);
      ng.appendChild(subLabel);

      ng.addEventListener('pointerdown', (ev) => {
        ev.stopPropagation();
        this._draggingNodeId = node.id;
        this._dragMoved = false;
      });

      ng.addEventListener('click', (ev) => {
        ev.stopPropagation();
        if (!this._dragMoved) {
          this.selectNode(node.id);
          this.onSelectNode?.(node);
        }
      });

      this.nodesLayer.appendChild(ng);
    }

    this._updateHighlighting();
  }

  _updateHighlighting() {
    let activeNodes = null;
    let activeEdges = null;

    if (this.isolatedPathId) {
      const pathObj = this.paths.find((p) => p.id === this.isolatedPathId);
      if (pathObj) {
        activeNodes = new Set(pathObj.node_ids || []);
        activeEdges = new Set(pathObj.edge_ids || []);
      }
    }

    for (const el of this.nodesLayer.querySelectorAll('.g-node-group')) {
      const nid = el.getAttribute('data-node-id');
      el.classList.toggle('selected', nid === this.selectedNodeId);
      el.classList.toggle('dimmed', Boolean(activeNodes && !activeNodes.has(nid)));
    }

    for (const el of this.edgesLayer.querySelectorAll('.g-edge-group')) {
      const eid = el.getAttribute('data-edge-id');
      el.classList.toggle('selected', eid === this.selectedEdgeId);
      el.classList.toggle('dimmed', Boolean(activeEdges && !activeEdges.has(eid)));
    }
  }
}
