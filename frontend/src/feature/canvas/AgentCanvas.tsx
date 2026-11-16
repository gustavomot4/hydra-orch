import { useEffect, useId, useRef, useState } from 'react';
import { Hand, Maximize, Minus, Move, Network, Plus, RotateCcw } from 'lucide-react';
import {
  CanvasGraph,
  CanvasNode,
  layoutNodes,
  NODE_HEIGHT,
  NODE_WIDTH,
  Point,
  statusMeta,
} from './canvasModel';

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
type View = { x: number; y: number; scale: number; automaticFit?: boolean };
function restoreView(key: string): View | null {
  try {
    const value = JSON.parse(localStorage.getItem('hydra:canvas-view:' + key) || 'null');
    if (
      value &&
      Number.isFinite(value.x) &&
      Number.isFinite(value.y) &&
      Number.isFinite(value.scale) &&
      Math.abs(value.x) < 100000 &&
      Math.abs(value.y) < 100000 &&
      value.scale >= 0.25 &&
      value.scale <= 1.8
    )
      return value;
  } catch {
    /* optional local layout */
  }
  return null;
}

function restore(key: string, nodes: CanvasNode[]) {
  const base = layoutNodes(nodes);
  try {
    const saved = JSON.parse(localStorage.getItem('hydra:canvas:' + key) || 'null');
    for (const node of nodes) {
      const p = saved?.[node.id];
      if (
        p &&
        Number.isFinite(p.x) &&
        Number.isFinite(p.y) &&
        Math.abs(p.x) < 100000 &&
        Math.abs(p.y) < 100000
      )
        base[node.id] = p;
    }
  } catch {
    /* Layout persistence is optional. */
  }
  return base;
}

export function AgentCanvas({
  graph,
  workId,
  selected,
  onSelect,
}: {
  graph: CanvasGraph;
  workId: string;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const stage = useRef<HTMLDivElement>(null);
  const fontProbe = useRef<HTMLSpanElement>(null);
  // Keep graph geometry and its text together when the browser's text size changes.
  const [textScale, setTextScale] = useState(1);
  const measuredFontScale = useRef<number | null>(null);
  useEffect(() => {
    const element = fontProbe.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.max(0.5, entry.contentRect.width / 16);
      if (measuredFontScale.current !== null && measuredFontScale.current !== next)
        automaticFit.current = false; // Browser text enlargement must enlarge the graph as a unit.
      measuredFontScale.current = next;
      setTextScale(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const arrowId = useId().replace(/:/g, '') + '-arrow';
  const labelId = arrowId + '-label';
  const helpId = arrowId + '-help';
  const nodesRef = useRef(graph.nodes);
  nodesRef.current = graph.nodes;
  const [positions, setPositions] = useState(() => restore(workId, graph.nodes));
  const [view, setView] = useState<View>(() => restoreView(workId) || { x: 24, y: 24, scale: 0.8 });
  const automaticFit = useRef(!restoreView(workId) || restoreView(workId)?.automaticFit === true);
  const viewRef = useRef(view);
  viewRef.current = view;
  const drag = useRef<{ id?: string; x: number; y: number; start: Point } | null>(null);
  const suppressClick = useRef(false);
  const [dragging, setDragging] = useState(false);
  const identity = graph.nodes.map((n) => n.id).join('|');
  useEffect(() => {
    setPositions((previous) => {
      const next = restore(workId, nodesRef.current);
      for (const id of Object.keys(next)) if (previous[id]) next[id] = previous[id];
      return next;
    });
  }, [workId, identity]); // Preserve manual positions across status updates.
  useEffect(() => {
    const timeout = setTimeout(() => {
      try {
        localStorage.setItem('hydra:canvas:' + workId, JSON.stringify(positions));
      } catch {
        /* optional */
      }
    }, 200);
    return () => clearTimeout(timeout);
  }, [workId, positions]);
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(
          'hydra:canvas-view:' + workId,
          JSON.stringify({ ...view, automaticFit: automaticFit.current }),
        );
      } catch {
        /* optional */
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [view, workId]);
  const bound = Object.values(positions).reduce(
    (r, p) => ({
      left: Math.min(r.left, p.x),
      top: Math.min(r.top, p.y),
      right: Math.max(r.right, p.x + NODE_WIDTH),
      bottom: Math.max(r.bottom, p.y + NODE_HEIGHT),
    }),
    { left: 0, top: 0, right: 680, bottom: 500 },
  );
  const fit = () => {
    automaticFit.current = true;
    const width = stage.current?.clientWidth || 800,
      height = stage.current?.clientHeight || 600;
    const scale = clamp(
      Math.min(
        (width - 64) / ((bound.right - bound.left) * textScale),
        (height - 64) / ((bound.bottom - bound.top) * textScale),
      ),
      0.25,
      1,
    );
    setView({
      scale,
      x:
        (width - (bound.right - bound.left) * scale * textScale) / 2 -
        bound.left * scale * textScale,
      y:
        (height - (bound.bottom - bound.top) * scale * textScale) / 2 -
        bound.top * scale * textScale,
    });
  };
  const zoom = (amount: number, point?: Point) => {
    automaticFit.current = false;
    setView((old) => {
      const scale = clamp(Math.round((old.scale + amount) * 100) / 100, 0.25, 1.8);
      const center = point || {
        x: (stage.current?.clientWidth || 800) / 2,
        y: (stage.current?.clientHeight || 600) / 2,
      };
      return {
        scale,
        x: center.x - ((center.x - old.x) * scale) / old.scale,
        y: center.y - ((center.y - old.y) * scale) / old.scale,
      };
    });
  };
  const fitRef = useRef(fit);
  fitRef.current = fit;
  useEffect(() => {
    if (automaticFit.current) fitRef.current();
  }, [textScale, positions]);
  useEffect(() => {
    const element = stage.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      if (automaticFit.current) fitRef.current();
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const element = stage.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      if (event.ctrlKey || !event.shiftKey)
        zoom(event.deltaY > 0 ? -0.08 : 0.08, {
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
        });
      else {
        automaticFit.current = false;
        setView((v) => ({ ...v, x: v.x - event.deltaY, y: v.y - event.deltaX }));
      }
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  }, []);
  useEffect(() => {
    const restored = restoreView(workId);
    if (restored) setView(restored);
    else fitRef.current();
  }, [workId]);
  const moveNode = (id: string, x: number, y: number) => {
    automaticFit.current = false;
    setPositions((old) => ({
      ...old,
      [id]: { x: clamp(x, -10000, 10000), y: clamp(y, -10000, 10000) },
    }));
  };

  return (
    <div className="agent-map" data-testid="agent-map">
      <span ref={fontProbe} className="canvas-font-probe" aria-hidden="true" />
      <span id={labelId} className="sr-only">
        Canvas de agentes
      </span>
      <span id={helpId} className="sr-only">
        Use setas para navegar, mais e menos para zoom e Home para enquadrar.
      </span>
      <div
        ref={stage}
        className={`agent-map-stage ${dragging ? 'is-dragging' : ''}`}
        role="region"
        aria-labelledby={labelId}
        aria-describedby={helpId}
        tabIndex={0}
        data-testid="canvas-viewport"
        data-scale={view.scale}
        style={{
          backgroundPosition: `${view.x}px ${view.y}px`,
          backgroundSize: `${24 * view.scale}px ${24 * view.scale}px`,
        }}
        onPointerDown={(event) => {
          if (event.button !== 0 || (event.target as HTMLElement).closest('button,a,input,select'))
            return;
          event.currentTarget.focus();
          automaticFit.current = false;
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { x: event.clientX, y: event.clientY, start: { x: view.x, y: view.y } };
          setDragging(true);
        }}
        onPointerMove={(event) => {
          const moving = drag.current;
          if (!moving) return;
          if (
            Math.hypot(event.clientX - moving.x, event.clientY - moving.y) < 5 &&
            !suppressClick.current
          )
            return;
          suppressClick.current = true;
          setDragging(true);
          if (moving.id)
            moveNode(
              moving.id,
              moving.start.x + (event.clientX - moving.x) / (viewRef.current.scale * textScale),
              moving.start.y + (event.clientY - moving.y) / (viewRef.current.scale * textScale),
            );
          else
            setView((old) => ({
              ...old,
              x: moving.start.x + event.clientX - moving.x,
              y: moving.start.y + event.clientY - moving.y,
            }));
        }}
        onPointerUp={() => {
          drag.current = null;
          setDragging(false);
        }}
        onPointerCancel={() => {
          drag.current = null;
          suppressClick.current = false;
          setDragging(false);
        }}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          const delta: Record<string, Point> = {
            ArrowLeft: { x: 60, y: 0 },
            ArrowRight: { x: -60, y: 0 },
            ArrowUp: { x: 0, y: 60 },
            ArrowDown: { x: 0, y: -60 },
          };
          if (delta[event.key]) {
            automaticFit.current = false;
            event.preventDefault();
            setView((v) => ({ ...v, x: v.x + delta[event.key].x, y: v.y + delta[event.key].y }));
          }
          if (['+', '=', '-', 'Home'].includes(event.key)) {
            event.preventDefault();
            event.key === 'Home' ? fit() : zoom(event.key === '-' ? -0.1 : 0.1);
          }
        }}
      >
        <div
          className="agent-map-world"
          style={{
            transform: `translate(${view.x}px,${view.y}px) scale(${view.scale * textScale})`,
          }}
        >
          <svg className="agent-map-links" width="1" height="1" aria-hidden="true">
            <defs>
              <marker id={arrowId} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0 0 L8 4 L0 8" fill="var(--accent)" />
              </marker>
            </defs>
            {graph.edges.map((edge, index) => {
              const a = positions[edge.source],
                b = positions[edge.target];
              if (!a || !b) return null;
              const horizontal =
                Math.abs(a.y - b.y) < NODE_HEIGHT && Math.abs(a.x - b.x) > NODE_WIDTH;
              const right = b.x > a.x;
              const upwards = a.y > b.y;
              const x1 = horizontal
                  ? a.x + (right ? NODE_WIDTH : 0)
                  : a.x + NODE_WIDTH / 2 + (upwards ? 50 : 0),
                y1 = horizontal ? a.y + NODE_HEIGHT / 2 : a.y + (upwards ? 0 : NODE_HEIGHT);
              const x2 = horizontal
                  ? b.x + (right ? 0 : NODE_WIDTH)
                  : b.x + NODE_WIDTH / 2 + (upwards ? 50 : 0),
                y2 = horizontal ? b.y + NODE_HEIGHT / 2 : b.y + (upwards ? NODE_HEIGHT : 0);
              const bend = (y1 + y2) / 2;
              const path = horizontal
                ? `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`
                : `M${x1},${y1} C${x1},${bend} ${x2},${bend} ${x2},${y2}`;
              return (
                <g key={edge.id}>
                  <path
                    className={`agent-edge ${edge.source === selected || edge.target === selected ? 'selected' : ''}`}
                    d={path}
                    markerEnd={`url(#${arrowId})`}
                  />
                  <g
                    transform={`translate(${(x1 + x2) / 2},${bend + (horizontal ? 0 : (index % 2) * 18)})`}
                  >
                    <rect x="-59" y="-13" width="118" height="26" rx="8" />
                    <text textAnchor="middle" y="5">
                      {edge.label}
                    </text>
                  </g>
                </g>
              );
            })}
          </svg>
          {graph.nodes.map((node) => {
            const position = positions[node.id];
            if (!position) return null;
            const state = statusMeta(node.state);
            return (
              <article
                key={node.id}
                className={`agent-node tone-${state.tone} ${node.id === selected ? 'is-selected' : ''}`}
                style={{
                  left: position.x,
                  top: position.y,
                  width: NODE_WIDTH,
                  minHeight: NODE_HEIGHT,
                }}
                data-testid={`agent-node-${node.id}`}
              >
                <button
                  className="agent-node-move"
                  aria-label={`Mover ${node.title}. Use as setas.`}
                  title="Arraste ou use as setas para mover"
                  onPointerDown={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    stage.current?.setPointerCapture(event.pointerId);
                    drag.current = {
                      id: node.id,
                      x: event.clientX,
                      y: event.clientY,
                      start: position,
                    };
                    setDragging(true);
                  }}
                  onKeyDown={(event) => {
                    const delta: Record<string, Point> = {
                      ArrowLeft: { x: -24, y: 0 },
                      ArrowRight: { x: 24, y: 0 },
                      ArrowUp: { x: 0, y: -24 },
                      ArrowDown: { x: 0, y: 24 },
                    };
                    if (delta[event.key]) {
                      event.preventDefault();
                      event.stopPropagation();
                      moveNode(
                        node.id,
                        position.x + delta[event.key].x,
                        position.y + delta[event.key].y,
                      );
                    }
                  }}
                >
                  <Move size={16} aria-hidden="true" />
                </button>
                <button
                  className="agent-node-open"
                  aria-pressed={node.id === selected}
                  onPointerDown={(event) => {
                    if (event.button !== 0) return;
                    event.stopPropagation();
                    suppressClick.current = false;
                    event.currentTarget.setPointerCapture(event.pointerId);
                    drag.current = {
                      id: node.id,
                      x: event.clientX,
                      y: event.clientY,
                      start: position,
                    };
                  }}
                  onClick={() => {
                    if (suppressClick.current) {
                      suppressClick.current = false;
                      return;
                    }
                    onSelect(node.id);
                  }}
                  onFocus={() => {
                    const width = stage.current?.clientWidth || 800,
                      height = stage.current?.clientHeight || 600;
                    if (
                      position.x * view.scale * textScale + view.x < 0 ||
                      (position.x + NODE_WIDTH) * view.scale * textScale + view.x > width ||
                      position.y * view.scale * textScale + view.y < 0 ||
                      (position.y + NODE_HEIGHT) * view.scale * textScale + view.y > height - 80
                    )
                      setView((v) => ({
                        ...v,
                        x: width / 2 - (position.x + NODE_WIDTH / 2) * v.scale * textScale,
                        y: height / 2 - (position.y + NODE_HEIGHT / 2) * v.scale * textScale,
                      }));
                  }}
                >
                  <span className="agent-node-role">
                    <Network size={16} aria-hidden="true" />
                    {node.role === 'coordinator'
                      ? 'Coordenação'
                      : node.role === 'review'
                        ? 'Revisão'
                        : 'Agente'}
                  </span>
                  <strong>{node.title}</strong>
                  <span className="agent-node-executor">
                    {node.executor} · {node.model}
                  </span>
                  <span className={`canvas-status tone-${state.tone}`}>
                    <span aria-hidden="true">{state.symbol}</span>
                    {state.label}
                  </span>
                  <span className="agent-node-action">{node.action}</span>
                </button>
              </article>
            );
          })}
        </div>
      </div>
      <div className="canvas-controls" aria-label="Navegação do canvas">
        <span className="canvas-pan-hint">
          <Hand size={16} aria-hidden="true" />
          Arraste o fundo para navegar
        </span>
        <div className="canvas-control-group">
          <button
            onClick={() => {
              setPositions(layoutNodes(graph.nodes));
              setView({ x: 24, y: 24, scale: 0.8 });
            }}
          >
            <RotateCcw size={16} aria-hidden="true" />
            Organizar
          </button>
          <button onClick={fit}>
            <Maximize size={16} aria-hidden="true" />
            Enquadrar
          </button>
          <button onClick={() => zoom(-0.1)} aria-label="Diminuir zoom">
            <Minus size={16} />
          </button>
          <output aria-live="polite" aria-label="Zoom">
            {Math.round(view.scale * 100)}%
          </output>
          <button onClick={() => zoom(0.1)} aria-label="Aumentar zoom">
            <Plus size={16} />
          </button>
        </div>
      </div>
      <button
        className="canvas-minimap"
        aria-label="Minimapa: enquadrar todos os agentes"
        onClick={fit}
      >
        <svg
          viewBox={`${bound.left - 30} ${bound.top - 30} ${bound.right - bound.left + 60} ${bound.bottom - bound.top + 60}`}
          aria-hidden="true"
        >
          {graph.nodes.map(
            (node) =>
              positions[node.id] && (
                <rect
                  key={node.id}
                  x={positions[node.id].x}
                  y={positions[node.id].y}
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx="22"
                  className={node.id === selected ? 'active' : ''}
                />
              ),
          )}
        </svg>
      </button>
    </div>
  );
}
