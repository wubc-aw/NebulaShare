import assert from "node:assert"
import { classifyRegion } from "./proxy-regions.ts"

const cases = [
  ["日本 03", "亚洲"],
  ["HK-01", "亚洲"],
  ["美国 IEPL", "北美洲"],
  ["USA LA", "北美洲"],
  ["英国 01", "欧洲"],
  ["UK London", "欧洲"],
  ["巴西 01", "南美洲"],
  ["澳大利亚 Sydney", "大洋洲"],
  ["南非 01", "非洲"],
  ["Unknown Node", "其他"],
  ["IEPL-HK", "亚洲"],
  ["SGIEPL-US", "北美洲"],
]

for (const [name, expected] of cases) {
  const actual = classifyRegion(name)
  assert.strictEqual(actual, expected, `classifyRegion(${JSON.stringify(name)}) expected ${expected}, got ${actual}`)
}

console.log("All region classification tests passed.")
