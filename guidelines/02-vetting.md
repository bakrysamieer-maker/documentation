# Layer 2 – Vetting

**Your job:** decide **PASS** or **REJECT** for every supplier Layer 1 handed you. Rule out
trading companies, suppliers without their own factory, anything outside scope, and suppliers
below the quality bar. Record the evidence for every decision. Only PASS suppliers go on to
the Layer 3 deep dive, so be strict but fair.

Read `00-common-rules.md` first. Use Layer 1's information as a starting point, but check it.
Layer 1 may be wrong.

## Step 1 – Scope

Confirm the supplier fits its segment (`garment` or `fabric`), makes clothing, and is
**woven**. If not, reject with `NOT_CLOTHING`, `NOT_WOVEN` or `KNIT_SPECIALIST`. Rate
`knit_share`:

- `none`
- `minor` (small side line; can still pass)
- `major` (half or more of what they sell; reject)
- `unknown`

## Step 2 – Own factory or trader?

Look for **factory signals** and **trader signals**, and record each with its source URL.

**Strong factory signals**

- A third-party audit names the company as a **manufacturer or factory**. Examples: a
  Made-in-China "Audited Supplier" report by SGS, BV, TÜV or Intertek, or an Alibaba
  "Verified" on-site check.
- Registry information shows production in the business scope (生产, 制造, 加工, 织造) **and**
  30 or more insured employees (参保人数).
- The company's own website gives a factory address in an industrial area **and** shows
  photos or videos of its own production lines. That means looms for fabric mills, and
  cutting and sewing lines for garment factories.

**Medium factory signals**

- B2B profile business type "Manufacturer/Factory" (self-reported).
- Factory floor area in m², workforce numbers, an equipment list without photos, or a
  factory tour video.
- A Chinese name with 纺织 / 织造 / 服装 / 制衣 / 印染 plus a production-related business scope,
  but no employee data.

**Weak factory signals**

- Only a "we are a factory" claim, stock photos, or photos that clearly belong to someone else.

**Trader signals**

- The name contains Trading, Trade, Import & Export, International or Supply Chain
  (贸易, 商贸, 进出口, 供应链, 国际).
- The registry business scope is only sales (销售, 批发, 零售, 货物进出口) with no production.
- The only address is an office (Room, Floor or Block in a commercial building) and no factory
  address is given.
- The B2B business type is "Trading Company".
- A very wide product range unrelated to one production process.
- Fewer than 15 employees.

**Decision**

- `TRADING_COMPANY` → REJECT if it is a trading company and there is **no strong** factory
  signal.
- `NO_FACTORY_EVIDENCE` → REJECT if there is neither **one strong** nor **two medium**
  factory signals.
- An "Industry and Trade" (工贸) company passes this step only with evidence of **its own**
  factory. A "partner factory" or "cooperating factories" does not count.

## Step 3 – Quality bar

A supplier must meet **all** of these:

1. **Established 3 or more years ago** (2023 or earlier). Otherwise `TOO_NEW`.
2. **At least one quality signal:**
   - A certification: ISO 9001, ISO 14001, BSCI/amfori, SEDEX/SMETA, WRAP, OEKO-TEX
     Standard 100, GOTS, GRS/RCS, bluesign or SA8000.
   - A third-party factory audit.
   - A Canton Fair "Brand Enterprise" or "CF Award" title shown on a source we may use.
   - Documented supply to recognized international brands or retailers.
3. **No serious red flags,** such as a cancelled or revoked registration (注销, 吊销) or
   repeated serious quality complaints.

If any of these fails → REJECT with `QUALITY_BAR_NOT_MET`, or `TOO_NEW` for the first one.
Mark each quality signal `verified: true` only if a third party confirms it, such as a
certificate database or an audit report. Self-reported certificates count toward the bar,
but say they are self-reported.

## Step 4 – Contacts

Write down every business contact you come across: email, phone, WeChat, WhatsApp,
LinkedIn URL from search results, website. Layer 3 will complete them.

## Step 5 – Verdict

- `verdict`: `PASS` or `REJECT`.
- `reject_reasons`: one or more of `TRADING_COMPANY`, `NO_FACTORY_EVIDENCE`,
  `KNIT_SPECIALIST`, `NOT_CLOTHING`, `NOT_WOVEN`, `QUALITY_BAR_NOT_MET`, `TOO_NEW`,
  `DUPLICATE`, `INSUFFICIENT_INFO`. Use an empty list for PASS.
- `confidence`:
  - `high`: clear evidence
  - `medium`: mostly clear
  - `low`: a judgement call; explain it in `summary`
- `summary`: two or three sentences explaining the decision.

**Effort:** about 4–8 searches or page reads per supplier. Stop as soon as the decision is
clear. A clear REJECT (for example an obvious trader) needs fewer.
