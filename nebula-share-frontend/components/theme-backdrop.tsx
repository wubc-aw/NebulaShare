const MARQUEE_WORDS =
  "NEBULA SHARE · FILES · NETWORK · INTEL · CLAUDE · KNOWLEDGE · MCP · SKILLS · "
const MARQUEE_DATA =
  "SYS OK · UPLINK 1000MBPS · NODE RASPBERRY-PI-4B · GRID 46PX · ACCENT #AACFD1 · SESSION LIVE · "

/**
 * Decorative fixed background layers for the `vivid` and `tron` themes.
 * Always rendered; visibility is gated purely by CSS (`html.<theme> .theme-backdrop`),
 * so there is no JS flash when switching themes.
 */
export function ThemeBackdrop() {
  return (
    <div className="theme-backdrop" aria-hidden="true">
      {/* Vivid — aurora gradient blobs */}
      <div className="backdrop-vivid">
        <div className="vivid-blob vivid-blob-1" />
        <div className="vivid-blob vivid-blob-2" />
        <div className="vivid-blob vivid-blob-3" />
      </div>

      {/* Tron — drifting line grids + scrolling marquee rows */}
      <div className="backdrop-tron">
        <div className="tron-grid tron-grid-lg" />
        <div className="tron-grid" />
        <div className="tron-marquee tron-marquee-hero tron-marquee-reverse">
          <span>{MARQUEE_WORDS.repeat(3)}</span>
          <span>{MARQUEE_WORDS.repeat(3)}</span>
        </div>
        <div className="tron-marquee tron-marquee-top">
          <span>{MARQUEE_DATA.repeat(4)}</span>
          <span>{MARQUEE_DATA.repeat(4)}</span>
        </div>
        <div className="tron-marquee tron-marquee-bottom tron-marquee-reverse">
          <span>{MARQUEE_DATA.repeat(4)}</span>
          <span>{MARQUEE_DATA.repeat(4)}</span>
        </div>
      </div>
    </div>
  )
}
