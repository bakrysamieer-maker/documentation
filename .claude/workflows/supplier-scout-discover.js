export const meta = {
  name: 'supplier-scout-discover',
  description: 'Layer 1: find Canton Fair clothing exhibitors (woven garment factories and woven apparel fabric mills) from public sources, never the Canton Fair site',
  whenToUse: 'Start of a new supplier batch. Pass args.slices from config/discovery-slices.json and args.known_names from data/processed.json; feed the result to supplier-scout-research.',
  phases: [
    { title: 'Discover', detail: 'one agent per product/region slice' },
    { title: 'Top-up', detail: 'extra slices when a segment is short' },
  ],
}

const A = args || {}
const ROOT = A.root || '/home/user/documentation'
const TOTAL = A.total || 50
const PER_SEGMENT = A.per_segment || 25
const PER_AGENT = A.per_agent || 18
const MAX_TOPUP_ROUNDS = A.max_topup_rounds ?? 1
const KNOWN = A.known_names || []
const SLICES = A.slices || []

const NULLABLE_STRING = { type: ['string', 'null'] }
const CANDIDATE = {
  type: 'object',
  properties: {
    name_en: { type: 'string' },
    name_cn: NULLABLE_STRING,
    segment: { type: 'string', enum: ['garment', 'fabric'] },
    province: NULLABLE_STRING,
    city: NULLABLE_STRING,
    main_products: { type: 'string' },
    woven_evidence: { type: 'string' },
    canton_fair: {
      type: 'object',
      properties: {
        strength: { type: 'string', enum: ['strong', 'medium', 'weak'] },
        session: NULLABLE_STRING,
        booth: NULLABLE_STRING,
        evidence_url: { type: 'string' },
        evidence_note: { type: 'string' },
      },
      required: ['strength', 'session', 'booth', 'evidence_url', 'evidence_note'],
    },
    business_type_claimed: { type: 'string', enum: ['manufacturer', 'manufacturer_and_trading', 'trading', 'unknown'] },
    website: NULLABLE_STRING,
    b2b_profiles: { type: 'array', items: { type: 'string' } },
    flags: { type: 'array', items: { type: 'string', enum: ['possible_trader', 'possible_knit', 'mixed_knit_woven', 'possible_non_clothing'] } },
    notes: { type: 'string' },
  },
  required: ['name_en', 'name_cn', 'segment', 'province', 'city', 'main_products', 'woven_evidence',
    'canton_fair', 'business_type_claimed', 'website', 'b2b_profiles', 'flags', 'notes'],
}
const DISCOVERY_SCHEMA = {
  type: 'object',
  properties: {
    candidates: { type: 'array', items: CANDIDATE },
    search_notes: { type: 'string' },
  },
  required: ['candidates', 'search_notes'],
}

// Same company under different spellings: drop legal suffixes and punctuation before comparing.
function norm(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/\(.*?\)|（.*?）/g, ' ')
    .replace(/co\.?,?\s*ltd\.?|company limited|limited|ltd\.?|corporation|corp\.?|co\.|inc\.?|有限责任公司|有限公司|股份/g, ' ')
    .replace(/[^a-z0-9一-鿿]+/g, '')
}

const STRENGTH_ORDER = { strong: 0, medium: 1, weak: 2 }
const BUSINESS_ORDER = { manufacturer: 0, manufacturer_and_trading: 1, unknown: 2, trading: 3 }
function byPromise(a, b) {
  const ka = [STRENGTH_ORDER[a.canton_fair?.strength] ?? 3, BUSINESS_ORDER[a.business_type_claimed] ?? 2, (a.flags || []).length]
  const kb = [STRENGTH_ORDER[b.canton_fair?.strength] ?? 3, BUSINESS_ORDER[b.business_type_claimed] ?? 2, (b.flags || []).length]
  for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] - kb[i]
  return 0
}

function discoveryPrompt(slice, known, n) {
  const knownList = known.length ? known.map(k => `- ${k}`).join('\n') : '- (none)'
  return `You are the Layer 1 Discovery agent of the supplier-scout pipeline.

First read these two files and follow them exactly:
- ${ROOT}/guidelines/00-common-rules.md
- ${ROOT}/guidelines/01-discovery.md

Your slice:
- id: ${slice.id}
- segment: ${slice.segment}
- products: ${slice.products}
- regions: ${slice.regions}
- search ideas: ${slice.search_ideas}

Return up to ${n} candidates for this slice, all with segment "${slice.segment}".

Already known companies (skip these, any spelling):
${knownList}

Never open cantonfair.org.cn, and pass blocked_domains: ["cantonfair.org.cn"] on every WebSearch call.`
}

const found = []
const seen = new Set(KNOWN.map(norm).filter(Boolean))
const searchNotes = []

function addCandidates(result, sliceId) {
  if (!result) {
    log(`slice ${sliceId}: agent returned nothing`)
    return
  }
  searchNotes.push({ slice: sliceId, notes: result.search_notes })
  let added = 0
  for (const c of result.candidates || []) {
    const keys = [norm(c.name_en), norm(c.name_cn)].filter(Boolean)
    if (!keys.length || keys.some(k => seen.has(k))) continue
    keys.forEach(k => seen.add(k))
    found.push({ ...c, slice: sliceId })
    added++
  }
  log(`slice ${sliceId}: ${added} new candidates`)
}

const countSegment = seg => found.filter(c => c.segment === seg).length

phase('Discover')
const primary = SLICES.filter(s => !s.topup)
const firstRound = await parallel(primary.map(s => () =>
  agent(discoveryPrompt(s, KNOWN, PER_AGENT), { label: `discover:${s.id}`, phase: 'Discover', schema: DISCOVERY_SCHEMA, effort: 'medium' })))
firstRound.forEach((r, i) => addCandidates(r, primary[i].id))

for (let round = 0; round < MAX_TOPUP_ROUNDS; round++) {
  const shortSegments = ['garment', 'fabric'].filter(seg => countSegment(seg) < PER_SEGMENT)
  const topups = SLICES.filter(s => s.topup && shortSegments.includes(s.segment))
  if (!topups.length) break
  phase('Top-up')
  const knownNow = KNOWN.concat(found.map(c => c.name_en))
  const results = await parallel(topups.map(s => () =>
    agent(discoveryPrompt(s, knownNow, Math.min(PER_AGENT, PER_SEGMENT - countSegment(s.segment) + 5)),
      { label: `topup:${s.id}`, phase: 'Top-up', schema: DISCOVERY_SCHEMA, effort: 'medium' })))
  results.forEach((r, i) => addCandidates(r, topups[i].id))
}

// Fill each segment up to PER_SEGMENT, then let the other segment use any spare slots up to TOTAL.
const garments = found.filter(c => c.segment === 'garment').sort(byPromise)
const fabrics = found.filter(c => c.segment === 'fabric').sort(byPromise)
let takeG = Math.min(garments.length, PER_SEGMENT)
let takeF = Math.min(fabrics.length, PER_SEGMENT)
let spare = TOTAL - takeG - takeF
if (spare > 0) {
  const moreG = Math.min(spare, garments.length - takeG)
  takeG += moreG
  spare -= moreG
  takeF += Math.min(spare, fabrics.length - takeF)
}
const pad = i => String(i + 1).padStart(2, '0')
const selected = [
  ...garments.slice(0, takeG).map((c, i) => ({ id: `G${pad(i)}`, ...c })),
  ...fabrics.slice(0, takeF).map((c, i) => ({ id: `F${pad(i)}`, ...c })),
]
const extras = [...garments.slice(takeG), ...fabrics.slice(takeF)]
log(`selected ${selected.length} (garment ${takeG}, fabric ${takeF}); ${extras.length} extra candidates kept for a later batch`)

return {
  selected,
  extras,
  stats: { found: found.length, garment_found: garments.length, fabric_found: fabrics.length, selected_garment: takeG, selected_fabric: takeF },
  search_notes: searchNotes,
}
