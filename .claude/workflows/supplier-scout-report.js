export const meta = {
  name: 'supplier-scout-report',
  description: 'Layer 4 (part 1): batch editor checks score consistency, ranks confirmed suppliers per segment and writes the batch overview',
  whenToUse: 'After supplier-scout-research and scripts/batch.py report-input. Pass args.run_dir; then run batch.py save-report and scripts/render_pdfs.py.',
  phases: [{ title: 'Report', detail: 'one batch-editor agent, no web research' }],
}

const A = args || {}
const ROOT = A.root || '/home/user/documentation'
const RUN_DIR = A.run_dir

const S = { type: 'string' }
const REPORT_SCHEMA = {
  type: 'object',
  properties: {
    overview: S,
    rankings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: S,
          segment: { type: 'string', enum: ['garment', 'fabric'] },
          rank: { type: 'integer', minimum: 1 },
          final_score: { type: 'integer', minimum: 0, maximum: 100 },
          adjustment_note: { type: ['string', 'null'] },
          one_line: S,
        },
        required: ['id', 'segment', 'rank', 'final_score', 'adjustment_note', 'one_line'],
      },
    },
    consistency_notes: { type: 'array', items: S },
  },
  required: ['overview', 'rankings', 'consistency_notes'],
}

phase('Report')
const report = await agent(`You are the Layer 4 Batch editor of the supplier-scout pipeline.

First read these files and follow them exactly:
- ${ROOT}/guidelines/00-common-rules.md
- ${ROOT}/guidelines/04-report.md (Part 1 is your job)
- ${ROOT}/guidelines/03-deep-dive.md (section H is the scoring rubric)

Your input is ${RUN_DIR}/report-input.json: batch stats plus the compact confirmed profiles.
Do no web research. Work only with that data. Rank every confirmed supplier exactly once.`, { label: 'batch-editor', phase: 'Report', schema: REPORT_SCHEMA, effort: 'medium' })

return report
