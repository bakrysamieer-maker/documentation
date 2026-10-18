# Layer 1 – Discovery

**Your job:** find suppliers in your assigned slice that **exhibit at the Canton Fair**, make
**clothing** (finished woven garments, or woven fabric for clothing), and look like
**manufacturers**. You hand them to Layer 2, which does the strict checks. Your job is to give
Layer 2 good candidates with evidence, not to vet them fully.

Read `00-common-rules.md` first. Its scope, exclusions and forbidden-site rules apply here.

## 1. What to return

- Up to the number of candidates given in your instructions, all inside your slice
  (segment, products and regions).
- Skip every company in the "already known" list you receive (same company, any spelling).
- Never return a company without Canton Fair evidence. Quality beats quantity: returning 12
  solid candidates is better than 18 doubtful ones.

## 2. Canton Fair evidence (required for every candidate)

You cannot use the Canton Fair website. Find the evidence elsewhere and rate it:

| Strength | What counts |
|---|---|
| `strong` | The company's own website, news page or social post announcing a **specific recent session** (136th–140th, 2024–2026) or a **booth number** (for example `14.4D36`, meaning hall 14, floor 4, booth D36). A third-party exhibitor list for a recent session also counts. |
| `medium` | Older sessions (before 2024), or "we exhibit at the Canton Fair" without a year. A B2B profile listing the Canton Fair under trade shows also counts. |
| `weak` | Only indirect hints, such as a marketplace listing tagged "Canton Fair" that does not name the company as an exhibitor. Return weak candidates only if you cannot fill your quota otherwise, and say so in `notes`. |

Useful places to look:

- Company news or blog pages: "138th Canton Fair", "visit us at Canton Fair booth",
  "广交会 展位", "第138届广交会".
- The "Trade Shows" section of `made-in-china.com` and `alibaba.com` supplier pages.
- Exhibition invitations on the company's Facebook, YouTube or Instagram pages, found through search.
- Sourcing-agent blogs and trade publications that list exhibitors.

## 3. Who to prefer

- **Manufacturer signals:** "Manufacturer" or "Factory" business type, a factory address,
  photos of their own production lines, equipment lists, workforce numbers.
- **Clearly woven products.** Examples are in `00-common-rules.md`.
- **Bonus, not required:** Middle East or Saudi exports, and Arab-market products such as
  thobe fabric, abayas or thobes.

## 4. Who to leave out

- Anything outside scope, and knitting specialists. See `00-common-rules.md`.
- **Obvious trading companies:** "Trading", "Trade", "Import & Export", "International Trade"
  or "Supply Chain" (贸易, 商贸, 进出口, 供应链) in the name **and** no sign of a factory.
  "Industry and Trade" (工贸) companies are often factories with an export arm. Keep those
  and flag them `possible_trader`.
- Shops in wholesale markets (for example Guangzhou Zhongda fabric market or the Keqiao
  China Textile City market halls) with no factory evidence.

## 5. How to search

Use several angles. Each one finds companies the others miss:

1. **Product + Canton Fair:** `"Canton Fair" poplin shirting manufacturer booth`,
   `"Canton Fair" men's shirts factory OEM booth 2025`, `广交会 梭织面料 生产厂家 展位`.
2. **Made-in-China directories:** `made-in-china.com/manufacturers/<product>.html` pages,
   then the supplier pages. Read their **Business Type**, **Audited** status and **Trade Shows**.
3. **Company news:** `"138th Canton Fair" fabric mill`, `"139th Canton Fair" garment factory`.
4. **Your slice's cluster cities** combined with the product and "Canton Fair". For example
   Shaoxing Keqiao, Wujiang Shengze, Changzhou, Humen, Xintang or Ningbo.

Always pass `blocked_domains: ["cantonfair.org.cn"]` to WebSearch.

## 6. Fields to fill

| Field | Meaning |
|---|---|
| `name_en` | Official English company name, as the company writes it. |
| `name_cn` | Chinese legal name if you saw it, else `null`. |
| `segment` | `garment` or `fabric`. |
| `province`, `city` | Where the company is based (`null` if unknown). |
| `main_products` | Short list of their main woven products. |
| `woven_evidence` | One sentence: why you believe they are woven, not knit. |
| `canton_fair` | `strength`, `session` (for example "138th, Oct 2025" or `null`), `booth` (or `null`), `evidence_url`, `evidence_note` (what the page says). |
| `business_type_claimed` | `manufacturer`, `manufacturer_and_trading`, `trading` or `unknown`, based on what the company or its B2B profile claims. |
| `website` | Official website, or `null`. |
| `b2b_profiles` | URLs of their made-in-china / alibaba / 1688 pages. |
| `flags` | Any of `possible_trader`, `possible_knit`, `mixed_knit_woven`, `possible_non_clothing`. |
| `notes` | Anything Layer 2 should know (one or two sentences). |

Also return `search_notes`: a few lines on which searches worked and what you could not find.
