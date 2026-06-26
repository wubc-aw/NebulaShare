# Client Aliases in Network Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display friendly aliases for clients in Network Hub's gateway client list and allow editing them inline via a popover.

**Architecture:** Extend the existing `NetworkHub` component to fetch aliases from `/api/clients/names`, merge them into the active client list by IP, and render an edit popover for each row. All changes stay in `network-hub.tsx`; backend endpoints already exist.

**Tech Stack:** React 19, TypeScript, Next.js 16, Tailwind CSS v4, lucide-react icons.

## Global Constraints
- No new dependencies.
- Keep changes inside `nebula-share-frontend/components/network-hub.tsx`.
- Follow existing styling patterns (bg-secondary/20, rounded-xl, text-muted-foreground, cn helper).
- Manual verification only; project has no frontend test framework.

---

### Task 1: Add alias state and fetch helpers

**Files:**
- Modify: `nebula-share-frontend/components/network-hub.tsx`

**Interfaces:**
- Consumes: `GET /api/clients/names` → `{ ok: boolean, names: Record<string, string> }`
- Produces: `clientNames` state, `fetchClientNames()` callback, `saveClientName(ip, name)` callback

- [ ] **Step 1: Add `clientNames` state and edit state near other state declarations**

Add after `const [clientsLoading, setClientsLoading] = useState(false)`:

```tsx
const [clientNames, setClientNames] = useState<Record<string, string>>({})
const [editingClientIp, setEditingClientIp] = useState<string | null>(null)
const [editName, setEditName] = useState("")
const [saveNameError, setSaveNameError] = useState<string | null>(null)
```

- [ ] **Step 2: Add `fetchClientNames` callback after `fetchClients`**

```tsx
const fetchClientNames = useCallback(async () => {
  try {
    const res = await fetch("/api/clients/names")
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (!data.ok) throw new Error("Backend returned ok: false")
    setClientNames(data.names || {})
  } catch (err) {
    console.error("Failed to fetch client names:", err)
  }
}, [])
```

- [ ] **Step 3: Add `saveClientName` callback**

```tsx
const saveClientName = useCallback(async (ip: string, name: string) => {
  setSaveNameError(null)
  try {
    const res = await fetch("/api/clients/names", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ip, name: name.trim() }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (!data.ok) throw new Error(data.error || "save failed")
    setClientNames(data.names || {})
    setEditingClientIp(null)
    setEditName("")
  } catch (err) {
    setSaveNameError(err instanceof Error ? err.message : "保存失败")
  }
}, [])
```

- [ ] **Step 4: Wire `fetchClientNames` into the Gateway tab effect**

In the effect at `useEffect(() => { if (activeTab === "gateway") { ... } }, [activeTab, ...])`, add `fetchClientNames()` alongside `fetchClients()`:

```tsx
useEffect(() => {
  if (activeTab === "gateway") {
    fetchStatus()
    fetchNodes()
    fetchClients()
    fetchClientNames()
    fetchSearchHub()
    const interval = setInterval(fetchClients, 3000)
    return () => clearInterval(interval)
  }
}, [activeTab, fetchStatus, fetchNodes, fetchClients, fetchClientNames, fetchSearchHub])
```

- [ ] **Step 5: Commit**

```bash
git add nebula-share-frontend/components/network-hub.tsx
git commit -m "feat(network): add client alias fetch and save helpers"
```

---

### Task 2: Render alias and edit popover in client rows

**Files:**
- Modify: `nebula-share-frontend/components/network-hub.tsx`

**Interfaces:**
- Consumes: `clientNames`, `editingClientIp`, `editName`, `saveNameError`, `saveClientName`, `setEditingClientIp`, `setEditName`
- Produces: Updated client row UI with alias display and inline popover editor

- [ ] **Step 1: Import the Pencil icon**

Add `Pencil` to the lucide-react import block:

```tsx
import {
  Power,
  Wifi,
  Globe,
  ArrowUpDown,
  RefreshCw,
  Zap,
  Activity,
  Users,
  ChevronRight,
  ChevronDown,
  Search,
  KeyRound,
  Pencil,
} from "lucide-react"
```

- [ ] **Step 2: Replace the client row label block**

Find the existing client row block (around line 768-795):

```tsx
<div className="flex-1 min-w-0">
  <div className="flex items-center gap-2">
    <span className="text-sm font-medium font-mono">{client.ip}</span>
    <span className="text-xs text-muted-foreground">{client.connections} 连接</span>
  </div>
  ...
</div>
```

Replace it with:

```tsx
<div className="flex-1 min-w-0">
  {editingClientIp === client.ip ? (
    <div className="flex items-center gap-2">
      <input
        autoFocus
        type="text"
        value={editName}
        onChange={(e) => setEditName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") saveClientName(client.ip, editName)
          if (e.key === "Escape") {
            setEditingClientIp(null)
            setEditName("")
            setSaveNameError(null)
          }
        }}
        className="px-2 py-1 text-sm rounded-md bg-background border border-border focus:outline-none focus:ring-1 focus:ring-primary w-40"
        placeholder="别名"
      />
      <button
        onClick={() => saveClientName(client.ip, editName)}
        className="text-xs px-2 py-1 bg-foreground text-background rounded-md hover:opacity-90"
      >
        保存
      </button>
      <button
        onClick={() => {
          setEditingClientIp(null)
          setEditName("")
          setSaveNameError(null)
        }}
        className="text-xs px-2 py-1 bg-secondary/60 rounded-md hover:bg-secondary"
      >
        取消
      </button>
    </div>
  ) : (
    <div className="flex items-center gap-2">
      <span className="text-sm font-medium">
        {clientNames[client.ip] || client.ip}
      </span>
      {clientNames[client.ip] && (
        <span className="text-xs text-muted-foreground font-mono">{client.ip}</span>
      )}
      <button
        onClick={() => {
          setEditingClientIp(client.ip)
          setEditName(clientNames[client.ip] || "")
          setSaveNameError(null)
        }}
        className="p-1 hover:bg-secondary rounded-md transition-colors"
        aria-label="编辑别名"
      >
        <Pencil className="w-3 h-3 text-muted-foreground" strokeWidth={1.5} />
      </button>
    </div>
  )}
  {saveNameError && editingClientIp === client.ip && (
    <p className="text-xs text-destructive mt-1">{saveNameError}</p>
  )}
  <div className="flex items-center gap-3 mt-0.5">
    <span className="text-xs text-muted-foreground font-mono">
      ↑ {formatBytesPerSec(client.upload_rate)}
    </span>
    <span className="text-xs text-muted-foreground font-mono">
      ↓ {formatBytesPerSec(client.download_rate)}
    </span>
  </div>
</div>
```

- [ ] **Step 3: Build and verify**

Run:

```bash
cd nebula-share-frontend
npm run build
```

Expected: build succeeds with no new errors.

- [ ] **Step 4: Sync build to static**

```bash
rsync -a --delete /home/aw/vibeProjects/NebulaShare/nebula-share-frontend/dist/ /home/aw/vibeProjects/NebulaShare/static/
```

- [ ] **Step 5: Manual verification**

1. Open Network Hub → 网关 → 客户端.
2. Confirm any IP with a saved alias now shows the alias as the main label, with the IP in muted text below.
3. Click the pencil icon next to a client; type a new alias, press Enter or 保存.
4. Confirm the label updates immediately and persists after refresh.
5. Click pencil, clear the input, press Enter; confirm the alias is removed and the IP becomes the main label again.
6. Disconnect the backend briefly and try saving; confirm an error message appears and the old value remains.

- [ ] **Step 6: Commit**

```bash
git add nebula-share-frontend/components/network-hub.tsx
git commit -m "feat(network): display and edit client aliases in gateway client list"
```

---

## Self-Review

**Spec coverage:**
- Display aliases as primary label ✓ Task 2 Step 2
- Show IP as secondary muted text when alias exists ✓ Task 2 Step 2
- Edit via pencil icon + inline popover ✓ Task 2 Step 2
- Fetch aliases on Gateway tab load ✓ Task 1 Step 4
- Save via POST `/api/clients/names` ✓ Task 1 Step 3
- Error handling / revert ✓ Task 1 Step 3 + Task 2 Step 2
- Empty alias deletes alias ✓ Task 2 Step 5 verification

**Placeholder scan:** No TBD, TODO, or vague instructions. Code and commands are exact.

**Type consistency:** `clientNames` is `Record<string, string>` throughout; `saveClientName` signature is consistent.
