"use client"

import { useEffect, useRef, useState, useCallback, useMemo } from "react"
import * as d3 from "d3"
import { Search, X, ZoomIn, ZoomOut, Maximize2, GitBranch, Tag, Lightbulb, AlertCircle, Box, Layers, MessageSquare } from "lucide-react"
import { cn } from "@/lib/utils"

// ─── Types ──────────────────────────────────────────────────────────
export interface Node {
  id: string
  name?: string
  type: "Project" | "Technology" | "Decision" | "Problem" | "Concept" | "Session"
  group: number
  radius?: number
  // D3 simulation will add these:
  x?: number
  y?: number
  vx?: number
  vy?: number
  fx?: number | null
  fy?: number | null
}

export interface Edge {
  source: string | Node
  target: string | Node
  type: string
}

export interface GraphData {
  nodes: Node[]
  edges: Edge[]
}

interface KnowledgeGraphProps {
  data: GraphData
}

// ─── Constants ──────────────────────────────────────────────────────
const NODE_COLORS: Record<Node["type"], string> = {
  Project: "#3b82f6",
  Technology: "#22c55e",
  Decision: "#f97316",
  Problem: "#ef4444",
  Concept: "#a855f7",
  Session: "#6b7280",
}

const NODE_ICONS: Record<Node["type"], React.ReactNode> = {
  Project: <Box className="w-3.5 h-3.5" strokeWidth={1.5} />,
  Technology: <Layers className="w-3.5 h-3.5" strokeWidth={1.5} />,
  Decision: <Lightbulb className="w-3.5 h-3.5" strokeWidth={1.5} />,
  Problem: <AlertCircle className="w-3.5 h-3.5" strokeWidth={1.5} />,
  Concept: <Tag className="w-3.5 h-3.5" strokeWidth={1.5} />,
  Session: <MessageSquare className="w-3.5 h-3.5" strokeWidth={1.5} />,
}

const FORCE_CHARGE = -300
const FORCE_LINK_DISTANCE = 100
const FORCE_COLLIDE = 30

// ─── Component ──────────────────────────────────────────────────────
export function KnowledgeGraph({ data }: KnowledgeGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const simulationRef = useRef<d3.Simulation<Node, undefined> | null>(null)
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const gRef = useRef<d3.Selection<SVGGElement, unknown, null, undefined> | null>(null)

  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })

  // Compute node degrees for dynamic sizing
  const nodeDegrees = useMemo(() => {
    const degrees = new Map<string, number>()
    data.nodes.forEach(n => degrees.set(n.id, 0))
    data.edges.forEach(e => {
      const s = typeof e.source === "string" ? e.source : e.source.id
      const t = typeof e.target === "string" ? e.target : e.target.id
      degrees.set(s, (degrees.get(s) || 0) + 1)
      degrees.set(t, (degrees.get(t) || 0) + 1)
    })
    return degrees
  }, [data])

  // Get node radius based on degree
  const getNodeRadius = useCallback((node: Node) => {
    const degree = nodeDegrees.get(node.id) || 0
    return node.radius ?? Math.max(8, Math.min(24, 8 + degree * 2.5))
  }, [nodeDegrees])

  // Resize observer
  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setDimensions({ width, height })
      }
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  // Build / rebuild the D3 graph
  useEffect(() => {
    if (!svgRef.current || dimensions.width === 0 || dimensions.height === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll("*").remove()

    const { width, height } = dimensions

    // Arrow marker definition
    const defs = svg.append("defs")
    defs.append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 20)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", "var(--muted-foreground)")
      .attr("opacity", 0.4)

    // Glow filter
    const filter = defs.append("filter")
      .attr("id", "node-glow")
      .attr("x", "-50%")
      .attr("y", "-50%")
      .attr("width", "200%")
      .attr("height", "200%")
    filter.append("feGaussianBlur")
      .attr("stdDeviation", "3")
      .attr("result", "coloredBlur")
    const feMerge = filter.append("feMerge")
    feMerge.append("feMergeNode").attr("in", "coloredBlur")
    feMerge.append("feMergeNode").attr("in", "SourceGraphic")

    // Main group for zoom/pan
    const g = svg.append("g")
    gRef.current = g

    // Prepare data (deep clone to avoid mutating props)
    const nodes: Node[] = data.nodes.map(n => ({ ...n }))
    const links: d3.SimulationLinkDatum<Node>[] = data.edges.map(e => ({
      source: typeof e.source === "string" ? e.source : e.source.id,
      target: typeof e.target === "string" ? e.target : e.target.id,
      type: e.type,
    }))

    // Simulation
    const simulation = d3.forceSimulation<Node>(nodes)
      .force("link", d3.forceLink<Node, d3.SimulationLinkDatum<Node>>(links)
        .id(d => d.id)
        .distance(FORCE_LINK_DISTANCE)
      )
      .force("charge", d3.forceManyBody().strength(FORCE_CHARGE))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide<Node>().radius(d => getNodeRadius(d) + FORCE_COLLIDE).iterations(2))

    simulationRef.current = simulation

    // Links
    const link = g.append("g")
      .attr("class", "links")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "var(--muted-foreground)")
      .attr("stroke-opacity", 0.25)
      .attr("stroke-width", 1)
      .attr("marker-end", "url(#arrow)")

    // Link labels (edge type)
    const linkLabel = g.append("g")
      .attr("class", "link-labels")
      .selectAll("text")
      .data(links)
      .join("text")
      .attr("font-size", "9px")
      .attr("fill", "var(--muted-foreground)")
      .attr("text-anchor", "middle")
      .attr("opacity", 0.5)
      .text(d => (d as any).type || "")

    // Nodes group
    const node = g.append("g")
      .attr("class", "nodes")
      .selectAll("g")
      .data(nodes)
      .join("g")
      .attr("class", "node")
      .style("cursor", "pointer")
      .call(d3.drag<SVGGElement, Node>()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart()
          d.fx = d.x ?? null
          d.fy = d.y ?? null
        })
        .on("drag", (event, d) => {
          d.fx = event.x
          d.fy = event.y
        })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0)
          d.fx = null
          d.fy = null
        })
      )

    // Node circles
    const circles = node.append("circle")
      .attr("r", d => getNodeRadius(d))
      .attr("fill", d => NODE_COLORS[d.type])
      .attr("stroke", "var(--background)")
      .attr("stroke-width", 2)
      .attr("opacity", 0.9)

    // Node labels
    const labels = node.append("text")
      .text(d => (d as any).name || d.id)
      .attr("font-size", "11px")
      .attr("font-weight", 500)
      .attr("fill", "var(--foreground)")
      .attr("text-anchor", "middle")
      .attr("dy", d => getNodeRadius(d) + 14)
      .attr("paint-order", "stroke")
      .attr("stroke", "var(--background)")
      .attr("stroke-width", 3)
      .attr("stroke-opacity", 0.8)

    // Interactions
    node
      .on("click", (_event, d) => {
        setSelectedNode(d)
      })
      .on("mouseenter", (_event, d) => {
        circles.attr("opacity", n => n.id === d.id ? 1 : 0.3)
        labels.attr("opacity", n => n.id === d.id ? 1 : 0.3)
        link
          .attr("stroke-opacity", l => {
            const s = (l.source as Node).id
            const t = (l.target as Node).id
            return s === d.id || t === d.id ? 0.7 : 0.08
          })
          .attr("stroke-width", l => {
            const s = (l.source as Node).id
            const t = (l.target as Node).id
            return s === d.id || t === d.id ? 1.5 : 0.5
          })
        linkLabel.attr("opacity", l => {
          const s = (l.source as Node).id
          const t = (l.target as Node).id
          return s === d.id || t === d.id ? 0.8 : 0.15
        })
      })
      .on("mouseleave", () => {
        circles.attr("opacity", 0.9)
        labels.attr("opacity", 1)
        link.attr("stroke-opacity", 0.25).attr("stroke-width", 1)
        linkLabel.attr("opacity", 0.5)
      })

    // Tick
    simulation.on("tick", () => {
      link
        .attr("x1", d => (d.source as Node).x ?? 0)
        .attr("y1", d => (d.source as Node).y ?? 0)
        .attr("x2", d => (d.target as Node).x ?? 0)
        .attr("y2", d => (d.target as Node).y ?? 0)

      linkLabel
        .attr("x", d => {
          const sx = (d.source as Node).x ?? 0
          const tx = (d.target as Node).x ?? 0
          return (sx + tx) / 2
        })
        .attr("y", d => {
          const sy = (d.source as Node).y ?? 0
          const ty = (d.target as Node).y ?? 0
          return (sy + ty) / 2 - 4
        })

      node.attr("transform", d => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on("zoom", (event) => {
        g.attr("transform", event.transform)
      })

    zoomRef.current = zoom
    svg.call(zoom)

    // Initial center
    svg.call(zoom.transform, d3.zoomIdentity.translate(0, 0).scale(1))

    // Cleanup
    return () => {
      simulation.stop()
    }
  }, [data, dimensions, getNodeRadius])

  // Re-apply search highlight when query changes
  useEffect(() => {
    if (!svgRef.current) return
    const svg = d3.select(svgRef.current)

    if (!searchQuery.trim()) {
      svg.selectAll(".nodes circle").attr("opacity", 0.9)
      svg.selectAll(".nodes text").attr("opacity", 1)
      svg.selectAll(".links line").attr("stroke-opacity", 0.25)
      svg.selectAll(".link-labels text").attr("opacity", 0.5)
      return
    }

    const q = searchQuery.toLowerCase()

    svg.selectAll<SVGCircleElement, Node>(".nodes circle")
      .attr("opacity", d => {
        const matched = d.id.toLowerCase().includes(q) || d.type.toLowerCase().includes(q)
        return matched ? 1 : 0.15
      })

    svg.selectAll<SVGTextElement, Node>(".nodes text")
      .attr("opacity", d => {
        const matched = d.id.toLowerCase().includes(q) || d.type.toLowerCase().includes(q)
        return matched ? 1 : 0.15
      })

    svg.selectAll<SVGLineElement, d3.SimulationLinkDatum<Node>>(".links line")
      .attr("stroke-opacity", d => {
        const s = ((d.source as Node).id).toLowerCase()
        const t = ((d.target as Node).id).toLowerCase()
        const matched = s.includes(q) || t.includes(q)
        return matched ? 0.5 : 0.05
      })

    svg.selectAll<SVGTextElement, d3.SimulationLinkDatum<Node>>(".link-labels text")
      .attr("opacity", d => {
        const s = ((d.source as Node).id).toLowerCase()
        const t = ((d.target as Node).id).toLowerCase()
        const matched = s.includes(q) || t.includes(q)
        return matched ? 0.7 : 0.1
      })
  }, [searchQuery])

  // Zoom controls
  const handleZoomIn = () => {
    if (!svgRef.current || !zoomRef.current) return
    d3.select(svgRef.current).transition().duration(300).call(zoomRef.current.scaleBy, 1.3)
  }
  const handleZoomOut = () => {
    if (!svgRef.current || !zoomRef.current) return
    d3.select(svgRef.current).transition().duration(300).call(zoomRef.current.scaleBy, 1 / 1.3)
  }
  const handleZoomReset = () => {
    if (!svgRef.current || !zoomRef.current) return
    d3.select(svgRef.current).transition().duration(300).call(zoomRef.current.transform, d3.zoomIdentity)
  }

  // Connected nodes for detail panel
  const connectedNodes = useMemo(() => {
    if (!selectedNode) return { incoming: [] as Node[], outgoing: [] as Node[] }
    const incoming: Node[] = []
    const outgoing: Node[] = []
    data.edges.forEach(e => {
      const s = typeof e.source === "string" ? e.source : e.source.id
      const t = typeof e.target === "string" ? e.target : e.target.id
      if (t === selectedNode.id) {
        const node = data.nodes.find(n => n.id === s)
        if (node) incoming.push(node)
      }
      if (s === selectedNode.id) {
        const node = data.nodes.find(n => n.id === t)
        if (node) outgoing.push(node)
      }
    })
    return { incoming, outgoing }
  }, [selectedNode, data])

  return (
    <div ref={containerRef} className="relative w-full h-full overflow-hidden rounded-xl bg-background border border-border/40">
      {/* SVG Canvas */}
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        className="block"
        style={{ touchAction: "none" }}
      />

      {/* Search Bar */}
      <div className="absolute top-3 left-3 flex items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/50" strokeWidth={1.5} />
          <input
            type="text"
            placeholder="搜索节点..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="pl-8 pr-7 py-1.5 rounded-lg bg-card/90 backdrop-blur text-sm placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/30 border border-border/40 w-48"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground"
            >
              <X className="w-3 h-3" strokeWidth={1.5} />
            </button>
          )}
        </div>
      </div>

      {/* Zoom Controls */}
      <div className="absolute bottom-3 left-3 flex flex-col gap-1">
        <button
          onClick={handleZoomIn}
          className="w-8 h-8 rounded-lg bg-card/90 backdrop-blur border border-border/40 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          title="放大"
        >
          <ZoomIn className="w-4 h-4" strokeWidth={1.5} />
        </button>
        <button
          onClick={handleZoomOut}
          className="w-8 h-8 rounded-lg bg-card/90 backdrop-blur border border-border/40 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          title="缩小"
        >
          <ZoomOut className="w-4 h-4" strokeWidth={1.5} />
        </button>
        <button
          onClick={handleZoomReset}
          className="w-8 h-8 rounded-lg bg-card/90 backdrop-blur border border-border/40 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          title="重置视图"
        >
          <Maximize2 className="w-4 h-4" strokeWidth={1.5} />
        </button>
      </div>

      {/* Legend */}
      <div className="absolute bottom-3 right-3 p-3 rounded-xl bg-card/90 backdrop-blur border border-border/40">
        <p className="text-[11px] font-medium text-muted-foreground mb-2 flex items-center gap-1">
          <GitBranch className="w-3 h-3" strokeWidth={1.5} />图例
        </p>
        <div className="space-y-1.5">
          {(Object.keys(NODE_COLORS) as Node["type"][]).map(type => (
            <div key={type} className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: NODE_COLORS[type] }}
              />
              <span className="text-[11px] text-muted-foreground">{type}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Node Count */}
      <div className="absolute top-3 right-3 px-2.5 py-1 rounded-lg bg-card/90 backdrop-blur border border-border/40 text-[11px] text-muted-foreground">
        {data.nodes.length} 节点 · {data.edges.length} 关系
      </div>

      {/* Detail Panel (slide from right) */}
      <div
        className={cn(
          "absolute top-0 right-0 h-full w-72 bg-card/95 backdrop-blur border-l border-border/40 transform transition-transform duration-300 ease-out z-10",
          selectedNode ? "translate-x-0" : "translate-x-full"
        )}
      >
        {selectedNode && (
          <div className="h-full flex flex-col p-4">
            {/* Header */}
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-2">
                <span
                  className="w-3 h-3 rounded-full shrink-0"
                  style={{ backgroundColor: NODE_COLORS[selectedNode.type] }}
                />
                <div>
                  <h3 className="text-sm font-semibold leading-tight">{selectedNode.name || selectedNode.id}</h3>
                  <p className="text-[11px] text-muted-foreground">{selectedNode.type}</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedNode(null)}
                className="w-6 h-6 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              >
                <X className="w-3.5 h-3.5" strokeWidth={1.5} />
              </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 gap-2 mb-4">
              <div className="p-2.5 rounded-lg bg-secondary/50">
                <p className="text-[10px] text-muted-foreground">连接数</p>
                <p className="text-lg font-semibold">{nodeDegrees.get(selectedNode.id) || 0}</p>
              </div>
              <div className="p-2.5 rounded-lg bg-secondary/50">
                <p className="text-[10px] text-muted-foreground">分组</p>
                <p className="text-lg font-semibold">{selectedNode.group}</p>
              </div>
            </div>

            {/* Connected nodes */}
            {connectedNodes.incoming.length > 0 && (
              <div className="mb-3">
                <p className="text-[11px] font-medium text-muted-foreground mb-1.5">来源节点</p>
                <div className="space-y-1">
                  {connectedNodes.incoming.map(n => (
                    <button
                      key={n.id}
                      onClick={() => setSelectedNode(n)}
                      className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-secondary/50 transition-colors text-left"
                    >
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: NODE_COLORS[n.type] }}
                      />
                      <span className="text-xs truncate">{n.name || n.id}</span>
                      <span className="text-[10px] text-muted-foreground ml-auto shrink-0">{n.type}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {connectedNodes.outgoing.length > 0 && (
              <div className="mb-3">
                <p className="text-[11px] font-medium text-muted-foreground mb-1.5">指向节点</p>
                <div className="space-y-1">
                  {connectedNodes.outgoing.map(n => (
                    <button
                      key={n.id}
                      onClick={() => setSelectedNode(n)}
                      className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-secondary/50 transition-colors text-left"
                    >
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: NODE_COLORS[n.type] }}
                      />
                      <span className="text-xs truncate">{n.name || n.id}</span>
                      <span className="text-[10px] text-muted-foreground ml-auto shrink-0">{n.type}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Node type info */}
            <div className="mt-auto pt-3 border-t border-border/40">
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                {NODE_ICONS[selectedNode.type]}
                <span>{selectedNode.type} 类型节点</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
