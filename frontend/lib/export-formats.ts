/**
 * Turning an agent's Markdown into files people can open anywhere.
 *
 * Agents write Markdown. On a laptop that opens fine; on a phone, or for
 * anyone who has never met the format, a .md file is a page of # and *
 * symbols. So the same text is offered as a Word document, with real
 * headings, lists and tables, and as plain text with the symbols gone.
 *
 * Both are built from a parsed tree rather than by stripping characters, so
 * "**bold**" becomes bold in Word and plain "bold" in text, and a literal
 * asterisk in the middle of a sentence survives.
 *
 * Loaded only when someone downloads: the Word library is the size of the rest
 * of the screen, and most visits never need it.
 */

import type {
  List,
  Nodes,
  PhrasingContent,
  Root,
  RootContent,
  Table,
} from 'mdast'
import remarkGfm from 'remark-gfm'
import remarkParse from 'remark-parse'
import { unified } from 'unified'

function parse(markdown: string): Root {
  return unified().use(remarkParse).use(remarkGfm).parse(markdown) as Root
}

// -- plain text ---------------------------------------------------------------

function inlineText(nodes: PhrasingContent[]): string {
  return nodes
    .map((node) => {
      switch (node.type) {
        case 'text':
        case 'inlineCode':
        case 'html':
          return node.value
        case 'break':
          return '\n'
        case 'image':
          return node.alt ?? ''
        case 'link': {
          const label = inlineText(node.children)
          // The address is kept: in plain text it is the only way to follow it.
          return label && label !== node.url ? `${label} (${node.url})` : node.url
        }
        default:
          return 'children' in node ? inlineText(node.children as PhrasingContent[]) : ''
      }
    })
    .join('')
}

function blockText(node: RootContent | Nodes, depth = 0): string {
  switch (node.type) {
    case 'heading':
    case 'paragraph':
      return inlineText(node.children)
    case 'list':
      return listText(node, depth)
    case 'blockquote':
      return node.children
        .map((child) => blockText(child, depth))
        .join('\n\n')
        .split('\n')
        .map((line) => `> ${line}`)
        .join('\n')
    case 'code':
      return node.value
    case 'thematicBreak':
      return '----------'
    case 'table':
      return tableText(node)
    case 'html':
      return node.value
    default:
      return 'children' in node
        ? (node.children as Nodes[]).map((child) => blockText(child, depth)).join('\n\n')
        : ''
  }
}

function listText(list: List, depth: number): string {
  const indent = '   '.repeat(depth)
  return list.children
    .map((item, index) => {
      const marker = list.ordered ? `${(list.start ?? 1) + index}.` : '•'
      const [first, ...rest] = item.children
      const head = first ? blockText(first, depth + 1) : ''
      const tail = rest.map((child) => blockText(child, depth + 1)).join('\n')
      return `${indent}${marker} ${head}${tail ? `\n${tail}` : ''}`
    })
    .join('\n')
}

function tableText(table: Table): string {
  return table.children
    .map((row) => row.children.map((cell) => inlineText(cell.children)).join(' | '))
    .join('\n')
}

/** The text with the Markdown symbols gone and the structure kept. */
export function markdownToPlainText(markdown: string): string {
  const tree = parse(markdown)
  return `${tree.children.map((node) => blockText(node)).join('\n\n').trim()}\n`
}

// -- Word ---------------------------------------------------------------------

/** A .docx file of the same text, with real headings, lists and tables. */
export async function markdownToDocx(markdown: string, title?: string): Promise<Blob> {
  const docx = await import('docx')
  const {
    AlignmentType,
    BorderStyle,
    Document,
    ExternalHyperlink,
    HeadingLevel,
    LevelFormat,
    Packer,
    Paragraph,
    Table: DocxTable,
    TableCell,
    TableRow,
    TextRun,
    WidthType,
  } = docx

  type Marks = { bold?: boolean; italics?: boolean; strike?: boolean; code?: boolean }
  type Run = InstanceType<typeof TextRun> | InstanceType<typeof ExternalHyperlink>

  const HEADINGS = [
    HeadingLevel.HEADING_1,
    HeadingLevel.HEADING_2,
    HeadingLevel.HEADING_3,
    HeadingLevel.HEADING_4,
    HeadingLevel.HEADING_5,
    HeadingLevel.HEADING_6,
  ]
  const MONO = 'Consolas'
  // Each numbered list restarts at 1; Word continues a shared numbering
  // unless each list is its own instance.
  let listInstance = 0

  function runs(nodes: PhrasingContent[], marks: Marks = {}): Run[] {
    return nodes.flatMap((node): Run[] => {
      switch (node.type) {
        case 'text':
        case 'html':
          return [
            new TextRun({
              text: node.value,
              bold: marks.bold,
              italics: marks.italics,
              strike: marks.strike,
              font: marks.code ? MONO : undefined,
            }),
          ]
        case 'inlineCode':
          return [new TextRun({ text: node.value, font: MONO, bold: marks.bold })]
        case 'strong':
          return runs(node.children, { ...marks, bold: true })
        case 'emphasis':
          return runs(node.children, { ...marks, italics: true })
        case 'delete':
          return runs(node.children, { ...marks, strike: true })
        case 'break':
          return [new TextRun({ text: '', break: 1 })]
        case 'image':
          return node.alt ? [new TextRun({ text: node.alt, italics: true })] : []
        case 'link':
          return [
            new ExternalHyperlink({
              link: node.url,
              children: [
                new TextRun({
                  text: inlineText(node.children) || node.url,
                  style: 'Hyperlink',
                  bold: marks.bold,
                  italics: marks.italics,
                }),
              ],
            }),
          ]
        default:
          return 'children' in node ? runs(node.children as PhrasingContent[], marks) : []
      }
    })
  }

  type Block = InstanceType<typeof Paragraph> | InstanceType<typeof DocxTable>

  function blocks(node: RootContent | Nodes, quoted = false): Block[] {
    const indent = quoted ? { left: 720 } : undefined
    switch (node.type) {
      case 'heading':
        return [
          new Paragraph({
            heading: HEADINGS[Math.min(node.depth, 6) - 1],
            children: runs(node.children),
            spacing: { before: 240, after: 120 },
          }),
        ]
      case 'paragraph':
        return [
          new Paragraph({
            children: runs(node.children, { italics: quoted }),
            indent,
            spacing: { after: 160 },
          }),
        ]
      case 'list':
        return listBlocks(node, 0)
      case 'blockquote':
        return node.children.flatMap((child) => blocks(child, true))
      case 'code':
        return node.value.split('\n').map(
          (line) =>
            new Paragraph({
              children: [new TextRun({ text: line || ' ', font: MONO, size: 20 })],
              spacing: { after: 0 },
            }),
        )
      case 'thematicBreak':
        return [
          new Paragraph({
            children: [],
            border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'BBBBBB', space: 1 } },
            spacing: { after: 160 },
          }),
        ]
      case 'table':
        return [tableBlock(node)]
      case 'html':
        return [new Paragraph({ children: [new TextRun(node.value)] })]
      default:
        return 'children' in node
          ? (node.children as Nodes[]).flatMap((child) => blocks(child, quoted))
          : []
    }
  }

  function listBlocks(list: List, level: number): Block[] {
    const instance = list.ordered ? ++listInstance : 0
    return list.children.flatMap((item) =>
      item.children.flatMap((child, index): Block[] => {
        if (child.type === 'list') return listBlocks(child, Math.min(level + 1, 2))
        if (child.type === 'paragraph' && index === 0) {
          return [
            new Paragraph({
              children: runs(child.children),
              ...(list.ordered
                ? { numbering: { reference: 'numbered', level, instance } }
                : { bullet: { level } }),
              spacing: { after: 80 },
            }),
          ]
        }
        // Anything after the first paragraph of an item, such as a code block.
        return blocks(child)
      }),
    )
  }

  function tableBlock(table: Table): InstanceType<typeof DocxTable> {
    return new DocxTable({
      width: { size: 100, type: WidthType.PERCENTAGE },
      rows: table.children.map(
        (row, rowIndex) =>
          new TableRow({
            tableHeader: rowIndex === 0,
            children: row.children.map(
              (cell) =>
                new TableCell({
                  children: [
                    new Paragraph({ children: runs(cell.children, { bold: rowIndex === 0 }) }),
                  ],
                  margins: { top: 60, bottom: 60, left: 100, right: 100 },
                }),
            ),
          }),
      ),
    })
  }

  const tree = parse(markdown)
  const body: Block[] = []
  if (title) body.push(new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun(title)] }))
  for (const node of tree.children) body.push(...blocks(node))

  const document = new Document({
    creator: 'Agenlate',
    title: title ?? 'Agenlate result',
    styles: { default: { document: { run: { font: 'Calibri', size: 22 } } } },
    numbering: {
      config: [
        {
          reference: 'numbered',
          levels: [0, 1, 2].map((level) => ({
            level,
            format: LevelFormat.DECIMAL,
            text: `%${level + 1}.`,
            alignment: AlignmentType.START,
            style: { paragraph: { indent: { left: 720 * (level + 1), hanging: 360 } } },
          })),
        },
      ],
    },
    sections: [{ children: body }],
  })
  return Packer.toBlob(document)
}
