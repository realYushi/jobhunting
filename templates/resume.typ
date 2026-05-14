// Renders a normalized resume JSON to PDF.
// Pass JSON path via: typst compile templates/resume.typ out.pdf --input data=/path/to/resume.json
// The JSON shape is what tools.lib.pdf._normalize_resume() produces, not raw base-resume.json.
//
// Layout notes — serif-led hierarchy with an ink-blue accent and tight editorial
// rhythm. Experience and project items use a three-row Role / Actions / Impact
// pattern when those fields are filled; otherwise they fall back to bullet body.
// Skills and certifications are intentionally compressed to keep the resume two
// pages.

#let data = json(sys.inputs.data)

// === Tokens ===
#let ink       = rgb("#1e3a5f")   // accent (links, section underlines, highlights)
#let body-col  = rgb("#1a1a1a")
#let muted     = rgb("#6b6b6b")
#let rule-col  = rgb("#d9d2c1")

#let serif = ("Charter", "Source Serif Pro", "EB Garamond", "Libertinus Serif", "New Computer Modern", "Times New Roman")

// === Page ===
#set page(
  paper: "a4",
  margin: (x: 14mm, y: 16mm),
)
#set text(font: serif, size: 9.6pt, fill: body-col, lang: "en")
#set par(leading: 0.55em, justify: false)

#show link: set text(fill: ink)
#show heading.where(level: 2): it => {
  v(1.1em, weak: true)
  block({
    text(size: 9.5pt, weight: "bold", tracking: 0.12em, fill: ink, upper(it.body))
    v(2pt, weak: true)
    line(length: 100%, stroke: 0.5pt + ink)
  })
  v(0.3em, weak: true)
}

// === Helpers ===
#let title-row(left-body, right-body) = grid(
  columns: (1fr, auto),
  align: (left, right),
  left-body,
  right-body,
)

#let muted-text(content) = text(size: 8.6pt, fill: muted, content)

#let label-row(label, body) = if body != "" and body != none {
  grid(
    columns: (auto, 1fr),
    column-gutter: 6pt,
    text(size: 8.4pt, fill: ink, tracking: 0.05em, weight: "semibold", upper(label)),
    text(body),
  )
}

#let metrics-row(metrics) = {
  // Match the ROLE/ACTIONS/IMPACT label-row pattern so the metrics line sits
  // inside the same visual grid instead of floating loose.
  let max-len = 0
  for m in metrics { if m.len() > max-len { max-len = m.len() } }
  let vertical = metrics.len() >= 3 or max-len > 28
  let body = if vertical {
    metrics.map(m => [· #m]).join(linebreak())
  } else {
    metrics.join("  ·  ")
  }
  label-row("Metrics", body)
}

// Branch: three-row Kami layout if any of role/actions/impact/metrics present;
// otherwise legacy bullet body. Wrapped in a non-breakable block so the title
// row never gets orphaned from its content across a page break.
#let kami-item(item) = block(breakable: false, {
  let has-three-row = (
    item.role != "" or item.actions != "" or item.impact != ""
      or item.metrics.len() > 0
  )
  title-row(
    text(weight: "bold", item.title),
    muted-text(item.meta),
  )
  if item.subtitle != "" {
    muted-text(item.subtitle)
    linebreak()
  }
  if has-three-row {
    v(2pt, weak: true)
    label-row("Role", item.role)
    label-row("Actions", item.actions)
    label-row("Impact", item.impact)
    if item.metrics.len() > 0 {
      // Match the inter-label rhythm (label-rows have no extra v() between
      // them); a metrics row that came after `v(1pt, weak)` visually glued
      // itself to the previous line.
      metrics-row(item.metrics)
    }
  } else if item.body != "" {
    item.body
  }
  v(0.55em, weak: true)
})

// Compact one-line item (skills group, language, certification).
#let compact-item(label, value, right) = {
  grid(
    columns: (auto, 1fr, auto),
    column-gutter: 8pt,
    text(weight: "bold", label),
    text(value),
    muted-text(right),
  )
  v(0.25em, weak: true)
}

// === Header ===
#align(center)[
  #text(size: 20pt, weight: "bold", tracking: 0.02em, data.name) \
  #v(-2pt)
  #text(size: 10.5pt, style: "italic", fill: muted, data.headline) \
  #v(1pt)
  #muted-text(data.contact.join("  ·  "))
]

// === Summary ===
#if data.summary != "" [
  == #data.summary_title
  #data.summary
]

// === Sections ===
#for section in data.sections [
  == #section.title
  #if section.title == "Skills" [
    #for item in section.items [
      #compact-item(item.title, item.body, "")
    ]
  ] else if section.title == "Languages" [
    #for item in section.items [
      #compact-item(item.title, item.subtitle, "")
    ]
  ] else if section.title == "Certifications" [
    #for item in section.items [
      #compact-item(item.title, item.subtitle, item.meta)
    ]
  ] else [
    #for item in section.items [
      #kami-item(item)
    ]
  ]
]
