export const meta = {
  name: 'supplier-scout-research',
  description: 'Layers 2-3: vet suppliers (own factory, scope, quality bar), then deep-dive the passing ones (Chinese sources, KSA export, contacts, scores)',
  whenToUse: 'After supplier-scout-discover. Pass args.run_dir (its candidates/<id>.json files come from scripts/batch.py save-discovery) and args.candidate_ids; then run scripts/collect_results.py on the transcript dir.',
  phases: [
    { title: 'Vet', detail: 'Layer 2: factory vs trader, scope, quality bar' },
    { title: 'Deep dive', detail: 'Layer 3: Chinese sources, KSA export, contacts, scores' },
  ],
}

const A = args || {}
const ROOT = A.root || '/home/user/documentation'
const RUN_DIR = A.run_dir
const CANDIDATES = (A.candidate_ids || []).map(id => ({ id }))
const CANDIDATE_DIR = `${RUN_DIR}/candidates`
const VET_GROUP = A.vet_group_size || 5
const DEEP_GROUP = A.deep_group_size || 2

const S = { type: 'string' }
const NS = { type: ['string', 'null'] }
const STRINGS = { type: 'array', items: S }
const SEGMENT = { type: 'string', enum: ['garment', 'fabric'] }
const SOURCED = { type: 'object', properties: { signal: S, source_url: S }, required: ['signal', 'source_url'] }
const FACTORY_SIGNAL = {
  type: 'object',
  properties: { signal: S, source_url: S, strength: { type: 'string', enum: ['strong', 'medium', 'weak'] } },
  required: ['signal', 'source_url', 'strength'],
}
const QUALITY_SIGNAL = {
  type: 'object',
  properties: { signal: S, source_url: S, verified: { type: 'boolean' } },
  required: ['signal', 'source_url', 'verified'],
}
const CONTACT_LIST = {
  type: 'array',
  items: { type: 'object', properties: { value: S, label: S, source_url: S }, required: ['value', 'label', 'source_url'] },
}
const CONTACTS = {
  type: 'object',
  properties: {
    emails: CONTACT_LIST,
    phones: CONTACT_LIST,
    wechat: CONTACT_LIST,
    whatsapp: CONTACT_LIST,
    linkedin: CONTACT_LIST,
    website: NS,
    b2b_profiles: STRINGS,
    people: {
      type: 'array',
      items: { type: 'object', properties: { name: S, title: S, source_url: S }, required: ['name', 'title', 'source_url'] },
    },
  },
  required: ['emails', 'phones', 'wechat', 'whatsapp', 'linkedin', 'website', 'b2b_profiles', 'people'],
}
const REJECT_REASONS = ['TRADING_COMPANY', 'NO_FACTORY_EVIDENCE', 'KNIT_SPECIALIST', 'NOT_CLOTHING', 'NOT_WOVEN',
  'QUALITY_BAR_NOT_MET', 'TOO_NEW', 'DUPLICATE', 'INSUFFICIENT_INFO']

const VET_ITEM = {
  type: 'object',
  properties: {
    id: S,
    name_en: S,
    name_cn: NS,
    segment: SEGMENT,
    verdict: { type: 'string', enum: ['PASS', 'REJECT'] },
    reject_reasons: { type: 'array', items: { type: 'string', enum: REJECT_REASONS } },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    business_type: { type: 'string', enum: ['manufacturer', 'manufacturer_and_trading', 'trading', 'unknown'] },
    knit_share: { type: 'string', enum: ['none', 'minor', 'major', 'unknown'] },
    factory_signals: { type: 'array', items: FACTORY_SIGNAL },
    trader_signals: { type: 'array', items: SOURCED },
    quality_signals: { type: 'array', items: QUALITY_SIGNAL },
    established_year: { type: ['integer', 'null'] },
    employees: NS,
    factory_address: NS,
    website: NS,
    contacts: CONTACTS,
    summary: S,
  },
  required: ['id', 'name_en', 'name_cn', 'segment', 'verdict', 'reject_reasons', 'confidence', 'business_type', 'knit_share',
    'factory_signals', 'trader_signals', 'quality_signals', 'established_year', 'employees', 'factory_address', 'website',
    'contacts', 'summary'],
}
const VET_SCHEMA = { type: 'object', properties: { results: { type: 'array', items: VET_ITEM } }, required: ['results'] }

const score = max => ({ type: 'integer', minimum: 0, maximum: max })
const DEEP_ITEM = {
  type: 'object',
  properties: {
    id: S,
    name_en: S,
    name_cn: NS,
    segment: SEGMENT,
    final_verdict: { type: 'string', enum: ['CONFIRMED', 'REJECT'] },
    reject_reason: NS,
    registry: {
      type: 'object',
      properties: {
        established: NS,
        registered_capital: NS,
        company_type: NS,
        production_in_scope: { type: ['boolean', 'null'] },
        insured_employees: NS,
        registered_address: NS,
        status: NS,
        credit_code: NS,
        risk_findings: STRINGS,
        source_urls: STRINGS,
      },
      required: ['established', 'registered_capital', 'company_type', 'production_in_scope', 'insured_employees',
        'registered_address', 'status', 'credit_code', 'risk_findings', 'source_urls'],
    },
    location: {
      type: 'object',
      properties: {
        province: NS,
        city: NS,
        factory_addresses: STRINGS,
        industrial_cluster: NS,
        plant_area: NS,
        other_sites: STRINGS,
        address_note: NS,
      },
      required: ['province', 'city', 'factory_addresses', 'industrial_cluster', 'plant_area', 'other_sites', 'address_note'],
    },
    capacity: {
      type: 'object',
      properties: {
        workforce: NS,
        equipment: NS,
        monthly_output: NS,
        moq: NS,
        lead_time: NS,
        main_products: STRINGS,
        customers: STRINGS,
      },
      required: ['workforce', 'equipment', 'monthly_output', 'moq', 'lead_time', 'main_products', 'customers'],
    },
    quality: {
      type: 'object',
      properties: {
        certifications: {
          type: 'array',
          items: {
            type: 'object',
            properties: { name: S, holder_match: { type: ['boolean', 'null'] }, verified: { type: 'boolean' }, source_url: S },
            required: ['name', 'holder_match', 'verified', 'source_url'],
          },
        },
        audits: { type: 'array', items: QUALITY_SIGNAL },
        notes: S,
      },
      required: ['certifications', 'audits', 'notes'],
    },
    chinese_web: {
      type: 'object',
      properties: {
        chinese_website: NS,
        store_1688: NS,
        wechat_official_account: NS,
        other_platforms: STRINGS,
        news: { type: 'array', items: { type: 'object', properties: { title: S, url: S }, required: ['title', 'url'] } },
      },
      required: ['chinese_website', 'store_1688', 'wechat_official_account', 'other_platforms', 'news'],
    },
    ksa_export: {
      type: 'object',
      properties: {
        rating: { type: 'string', enum: ['strong', 'moderate', 'weak', 'unknown'] },
        markets: STRINGS,
        saso_saber: { type: 'string', enum: ['yes', 'no', 'unknown'] },
        signals: { type: 'array', items: SOURCED },
        notes: S,
      },
      required: ['rating', 'markets', 'saso_saber', 'signals', 'notes'],
    },
    contacts: CONTACTS,
    scores: {
      type: 'object',
      properties: { factory: score(30), quality: score(25), ksa_export: score(25), scale: score(10), contactability: score(10) },
      required: ['factory', 'quality', 'ksa_export', 'scale', 'contactability'],
    },
    summary: S,
    strengths: STRINGS,
    risks: STRINGS,
    recommendation: { type: 'string', enum: ['shortlist', 'consider', 'low_priority'] },
    sources: { type: 'array', items: { type: 'object', properties: { title: S, url: S }, required: ['title', 'url'] } },
  },
  required: ['id', 'name_en', 'name_cn', 'segment', 'final_verdict', 'reject_reason', 'registry', 'location', 'capacity',
    'quality', 'chinese_web', 'ksa_export', 'contacts', 'scores', 'summary', 'strengths', 'risks', 'recommendation', 'sources'],
}
const DEEP_SCHEMA = { type: 'object', properties: { suppliers: { type: 'array', items: DEEP_ITEM } }, required: ['suppliers'] }

const FORBIDDEN = 'Never open cantonfair.org.cn, and pass blocked_domains: ["cantonfair.org.cn"] on every WebSearch call.'

function vetPrompt(group) {
  return `You are the Layer 2 Vetting agent of the supplier-scout pipeline.

First read these two files and follow them exactly:
- ${ROOT}/guidelines/00-common-rules.md
- ${ROOT}/guidelines/02-vetting.md

Vet these ${group.length} suppliers found by Layer 1: ${idsOf(group)}.
Their Layer 1 records are in ${CANDIDATE_DIR}/<id>.json (one file per id).
Return exactly one result per supplier, with the same "id".

${FORBIDDEN}`
}

function deepPrompt(items) {
  return `You are the Layer 3 Deep-dive agent of the supplier-scout pipeline.

First read these two files and follow them exactly:
- ${ROOT}/guidelines/00-common-rules.md
- ${ROOT}/guidelines/03-deep-dive.md

Research each of these ${items.length} suppliers in depth: ${items.map(i => i.id).join(',')}. They passed Layer 2 vetting.
Their Layer 1 records are in ${CANDIDATE_DIR}/<id>.json (one file per id). Their Layer 2 findings are below. Return exactly one profile per supplier, with the same "id".

<layer2_findings>
${JSON.stringify(items, null, 1)}
</layer2_findings>

${FORBIDDEN}`
}

function chunk(list, size) {
  const out = []
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size))
  return out
}
const idsOf = list => list.map(c => c.id).join(',')

// Keep only results for the ids this agent was given (agents are told to echo them unchanged).
function attachIds(results, group) {
  const ids = new Set(group.map(c => c.id))
  return (results || []).map(r => ({ ...r, id: String(r.id).trim().toUpperCase() })).filter(r => ids.has(r.id))
}

async function vetGroup(group) {
  const first = await agent(vetPrompt(group), { label: `vet:${idsOf(group)}`, phase: 'Vet', schema: VET_SCHEMA, effort: 'medium' })
  let results = attachIds(first && first.results, group)
  const missing = group.filter(c => !results.some(r => r.id === c.id))
  if (missing.length) {
    log(`vet ${idsOf(group)}: retrying ${idsOf(missing)}`)
    const retry = await agent(vetPrompt(missing), { label: `vet-retry:${idsOf(missing)}`, phase: 'Vet', schema: VET_SCHEMA, effort: 'medium' })
    results = results.concat(attachIds(retry && retry.results, missing))
  }
  const passed = results.filter(r => r.verdict === 'PASS').length
  log(`vet ${idsOf(group)}: ${passed}/${group.length} passed`)
  return results
}

async function deepDive(vetResults) {
  const passed = vetResults.filter(r => r.verdict === 'PASS')
  const profiles = await parallel(chunk(passed, DEEP_GROUP).map(pg => () =>
    agent(deepPrompt(pg),
      { label: `deep:${idsOf(pg)}`, phase: 'Deep dive', schema: DEEP_SCHEMA, effort: 'high' })
      .then(r => attachIds(r && r.suppliers, pg))))
  const deep = profiles.filter(Boolean).flat()
  const missing = passed.filter(v => !deep.some(d => d.id === v.id)).map(v => v.id)
  if (missing.length) log(`deep dive missing for ${missing.join(',')}`)
  return { vetting: vetResults, deep_dive: deep, deep_missing: missing }
}

const groups = chunk(CANDIDATES, VET_GROUP)
const results = await pipeline(groups, group => vetGroup(group), vetResults => deepDive(vetResults))

const done = results.filter(Boolean)
const vetting = done.flatMap(r => r.vetting)
const deep = done.flatMap(r => r.deep_dive)
const unvetted = CANDIDATES.filter(c => !vetting.some(v => v.id === c.id)).map(c => c.id)
if (unvetted.length) log(`not vetted (agent failures): ${unvetted.join(',')}`)

// Full results stay in the workflow journal (scripts/collect_results.py extracts them); return a compact summary.
const total = d => Object.values(d.scores || {}).reduce((a, b) => a + b, 0)
return {
  vetting: vetting.map(v => ({ id: v.id, name: v.name_en, verdict: v.verdict, reasons: v.reject_reasons, confidence: v.confidence })),
  deep_dive: deep.map(d => ({ id: d.id, name: d.name_en, final_verdict: d.final_verdict, recommendation: d.recommendation, total: total(d) })),
  unvetted,
  deep_missing: done.flatMap(r => r.deep_missing),
}
