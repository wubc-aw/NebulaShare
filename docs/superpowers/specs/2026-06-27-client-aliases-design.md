# Client Aliases in Network Hub

## Overview
Display and edit friendly aliases (e.g. "书房电视") for clients in the Network Hub gateway tab, instead of only showing raw IP addresses.

## Motivation
The backend already persists aliases via `/api/clients/names`, but the Network Hub UI only displays IPs. Users want to recognize devices at a glance.

## Scope
- **In scope:** Read aliases, display them in the client list, edit aliases inline via a popover.
- **Out of scope:** Auto-discovery of device types, MAC-based names, router DHCP integration.

## Design

### UI
In Network Hub → Gateway → 客户端:

- Each client row currently shows the IP as the primary label.
- With this feature:
  - **Primary label:** alias if one exists, otherwise the IP.
  - **Secondary label:** the IP shown in muted, smaller text when an alias exists; hidden when no alias exists (IP remains the primary label).
  - **Edit action:** a small pencil icon next to the primary label.
  - **Popover:** clicking the pencil opens a compact popover inline containing:
    - text input pre-filled with the current alias or IP
    - "保存" / "取消" buttons
    - pressing Enter saves, Escape cancels

### Data Flow
1. On entering the Gateway tab, fetch both:
   - `GET /api/mihomo/clients` — active client stats
   - `GET /api/clients/names` — persisted aliases
2. Merge aliases into the client list by IP on the frontend.
3. When the user saves an alias:
   - `POST /api/clients/names` with `{ ip, name }`
   - On success, refresh `/api/clients/names` (and optionally the client list)
   - On failure, keep the previous value and show an error message

### Edge Cases
- **No alias:** fall back to IP as primary label; do not show a secondary IP.
- **Empty alias:** treat as removal; POST with empty `name` deletes the alias.
- **Duplicate IPs:** impossible in the merged list because both endpoints key by IP.
- **Client offline:** aliases still display if the IP has appeared before and has an alias; if a client is not in the active list, it does not appear (aliases are not a device inventory).

### Error Handling
- Save failure: close popover, revert text, show inline error or simple alert.
- Fetch failure for aliases: silently skip aliases and show IPs only.

## Files to Change
- `nebula-share-frontend/components/network-hub.tsx`

## API Endpoints Used
- `GET /api/mihomo/clients` (existing)
- `GET /api/clients/names` (existing)
- `POST /api/clients/names` (existing)

## Testing
- Manual: set alias for a known IP, verify it appears as primary label; delete alias, verify IP returns; verify error state when backend rejects.
