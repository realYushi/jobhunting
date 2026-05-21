// Renders a normalized cover letter JSON to PDF.
// Pass JSON path via: typst compile templates/cover-letter.typ out.pdf --input data=/path/to/cover.json

#let data = json(sys.inputs.data)

#let ink      = rgb("#1e3a5f")
#let body-col = rgb("#1a1a1a")
#let muted    = rgb("#6b6b6b")
#let rule-col = rgb("#d9d2c1")
#let serif = ("Charter", "Source Serif Pro", "EB Garamond", "Libertinus Serif", "New Computer Modern", "Times New Roman")

#set page(
  paper: "a4",
  margin: (x: 22mm, y: 22mm),
)
#set text(font: serif, size: 10.5pt, fill: body-col, lang: "en")
#set par(leading: 0.68em, justify: false)

#data.salutation

#v(8pt)

#for paragraph in data.paragraphs [
  #paragraph
  #v(8pt)
]

#v(2pt)
#data.signoff \
#data.name
