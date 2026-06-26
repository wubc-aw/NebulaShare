export const CONTINENTS = [
  "亚洲",
  "欧洲",
  "北美洲",
  "南美洲",
  "大洋洲",
  "非洲",
  "其他",
] as const

export type Continent = (typeof CONTINENTS)[number]

const RULES: { continent: Continent; keywords: string[] }[] = [
  {
    continent: "亚洲",
    keywords: [
      "香港", "台湾", "日本", "新加坡", "韩国", "泰国", "马来西亚", "越南",
      "印度", "菲律宾", "印尼", "印度尼西亚", "中国", "上海", "北京", "广州",
      "深圳", "澳门", "HK", "TW", "JP", "SG", "KR", "TH", "MY", "VN", "IN",
      "PH", "ID", "HONGKONG", "TAIWAN", "JAPAN", "KOREA",
    ],
  },
  {
    continent: "欧洲",
    keywords: [
      "英国", "德国", "法国", "意大利", "荷兰", "西班牙", "瑞士", "瑞典",
      "俄罗斯", "波兰", "土耳其", "芬兰", "挪威", "丹麦", "比利时", "奥地利",
      "爱尔兰", "葡萄牙", "希腊", "罗马尼亚", "保加利亚", "塞尔维亚", "匈牙利",
      "捷克", "斯洛伐克", "乌克兰", "白俄罗斯", "爱沙尼亚", "拉脱维亚", "立陶宛",
      "UK", "GB", "DE", "FR", "IT", "NL", "ES", "CH", "SE", "RU", "PL", "TR",
      "FI", "NO", "DK", "BE", "AT", "IE", "PT", "GR", "RO", "BG", "RS", "HU",
      "CZ", "SK", "UA", "BY", "EE", "LV", "LT",
    ],
  },
  {
    continent: "北美洲",
    keywords: [
      "美国", "加拿大", "美國", "USA", "US", "CA", "CANADA", "AMERICA",
    ],
  },
  {
    continent: "南美洲",
    keywords: [
      "巴西", "阿根廷", "智利", "秘鲁", "哥伦比亚", "乌拉圭", "巴拉圭",
      "玻利维亚", "厄瓜多尔", "委内瑞拉", "BR", "AR", "CL", "PE", "CO", "UY",
      "PY", "BO", "EC", "VE", "BRAZIL", "ARGENTINA",
    ],
  },
  {
    continent: "大洋洲",
    keywords: [
      "澳大利亚", "新西兰", "澳洲", "AU", "NZ", "AUSTRALIA", "NEW ZEALAND",
    ],
  },
  {
    continent: "非洲",
    keywords: [
      "南非", "埃及", "尼日利亚", "肯尼亚", "摩洛哥", "阿尔及利亚", "突尼斯",
      "加纳", "坦桑尼亚", "乌干达", "埃塞俄比亚", "ZA", "EG", "NG", "KE", "MA",
      "DZ", "TN", "GH", "TZ", "UG", "ET", "SOUTH AFRICA", "EGYPT", "NIGERIA",
    ],
  },
]

const BOUNDARY_CHARS = new Set([
  " ", "-", "_", ".", "·", "•", "/", "\\", "(", ")", "[", "]", "{", "}",
  "<", ">", ":", ";", ",", "|", "&", "+", "=", "~", "`", "'", '"', "@",
  "#", "$", "%", "^", "*", "!", "?",
])

function isTokenMatch(text: string, keyword: string, startIndex: number): boolean {
  const before = startIndex === 0 || BOUNDARY_CHARS.has(text[startIndex - 1])
  const after =
    startIndex + keyword.length === text.length ||
    BOUNDARY_CHARS.has(text[startIndex + keyword.length])
  return before && after
}

function includesKeyword(text: string, keyword: string): boolean {
  const k = keyword.toUpperCase()
  const t = text.toUpperCase()
  if (k.length <= 2) {
    let idx = t.indexOf(k)
    while (idx !== -1) {
      if (isTokenMatch(t, k, idx)) return true
      idx = t.indexOf(k, idx + 1)
    }
    return false
  }
  return t.includes(k)
}

export function classifyRegion(name: string): Continent {
  const upper = name.toUpperCase()
  for (const rule of RULES) {
    for (const kw of rule.keywords) {
      if (includesKeyword(upper, kw)) {
        return rule.continent
      }
    }
  }
  return "其他"
}

export const CONTINENT_ORDER: Continent[] = [
  "亚洲",
  "欧洲",
  "北美洲",
  "南美洲",
  "大洋洲",
  "非洲",
  "其他",
]
