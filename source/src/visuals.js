import { renderMessage } from './render-message.js'

const NS = 'http://www.w3.org/2000/svg'
let mappingId = 0
function svgNode(tag, attributes = {}, text) {
  const node = document.createElementNS(NS, tag)
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)))
  if (text !== undefined) node.textContent = text
  return node
}

export function renderVisual(visual) {
  const figure = document.createElement('figure')
  figure.className = `question-visual visual-${visual.type}`
  const heading = document.createElement('figcaption')
  heading.className = 'visual-heading'
  renderMessage(heading, visual.title || '문제 살펴보기')
  figure.append(heading)
  if (visual.type === 'mapping') {
    const diagrams = document.createElement('div')
    diagrams.className = 'mapping-diagrams'
    visual.diagrams.forEach((diagram) => diagrams.append(drawMapping(diagram)))
    figure.append(diagrams)
  } else if (visual.type === 'concept') {
    const cards = document.createElement('div')
    cards.className = 'concept-items'
    visual.items.forEach((item) => {
      const card = document.createElement('div')
      card.className = 'concept-item'
      renderMessage(card, item.label)
      cards.append(card)
    })
    figure.append(cards)
  } else {
    const svg = svgNode('svg', { viewBox: '0 0 600 240', role: 'img', 'aria-label': `${visual.title}: ${visual.items.map((p) => `${p.label}, ${p.x}${visual.type === 'coordinate' ? `, ${p.y}` : ''}`).join('; ')}` })
    if (visual.type === 'number_line') drawNumberLine(svg, visual.items)
    else if (visual.type === 'bars') drawBars(svg, visual.items)
    else drawCoordinates(svg, visual.items)
    figure.append(svg)
  }
  const caption = document.createElement('p')
  caption.className = 'visual-note'
  renderMessage(caption, visual.caption)
  figure.append(caption)
  return figure
}

function mathLabel(svg, text, x, y, name = false) {
  const box = svgNode('foreignObject', { x: x - 42, y: y - 22, width: 84, height: 44 })
  const label = document.createElement('div')
  label.className = `mapping-label${name ? ' mapping-set-name' : ''}`
  const delimited = /\\[([]|\$/.test(text)
  renderMessage(label, delimited ? text : `\\(${text}\\)`)
  box.append(label)
  svg.append(box)
}

function chartLabel(svg, text, x, y, width, align = 'start') {
  const box = svgNode('foreignObject', { x, y, width, height: 30 })
  const label = document.createElement('div')
  label.className = `chart-label chart-label-${align}`
  renderMessage(label, text)
  box.append(label)
  svg.append(box)
}

function drawMapping(diagram) {
  const panel = document.createElement('div')
  panel.className = 'mapping-diagram'
  const label = document.createElement('p')
  label.className = 'mapping-diagram-label'
  renderMessage(label, diagram.label)
  const id = `mapping-${++mappingId}`
  const height = Math.max(284, 108 + Math.max(diagram.leftSet.elements.length, diagram.rightSet.elements.length) * 48)
  const centerY = (height + 32) / 2
  const row = (index, count) => count === 1 ? centerY : 84 + index * (height - 136) / (count - 1)
  const svg = svgNode('svg', { viewBox: `0 0 360 ${height}`, role: 'img', 'aria-labelledby': `${id}-title ${id}-description`, focusable: 'false', class: 'mapping-svg' })
  svg.append(svgNode('title', { id: `${id}-title` }, `${diagram.label} 집합 ${diagram.leftSet.name}에서 ${diagram.rightSet.name}로의 대응`))
  svg.append(svgNode('desc', { id: `${id}-description` }, [
    `${diagram.leftSet.name}의 원소: ${diagram.leftSet.elements.join(', ')}`,
    `${diagram.rightSet.name}의 원소: ${diagram.rightSet.elements.join(', ')}`,
    ...diagram.connections.map(({ from, to }) => `${diagram.leftSet.elements[from]}에서 ${diagram.rightSet.elements[to]}로 연결`),
    ...diagram.leftSet.elements.filter((_, index) => !diagram.connections.some(({ from }) => from === index)).map((element) => `${element}에서 나가는 연결 없음`),
  ].join('. ')))
  const defs = svgNode('defs')
  const marker = svgNode('marker', { id: `${id}-arrow`, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto' })
  marker.append(svgNode('path', { d: 'M 0 1 L 9 5 L 0 9 L 2 5 Z', class: 'mapping-arrow-head' }))
  defs.append(marker)
  svg.append(defs)
  for (const centerX of [75, 285]) svg.append(svgNode('ellipse', { cx: centerX, cy: centerY, rx: 56, ry: (height - 56) / 2, class: 'mapping-set' }))
  diagram.connections.forEach(({ from, to }) => {
    svg.append(svgNode('line', {
      x1: 107, y1: row(from, diagram.leftSet.elements.length),
      x2: 253, y2: row(to, diagram.rightSet.elements.length),
      class: 'mapping-connection', 'marker-end': `url(#${id}-arrow)`,
    }))
  })
  for (const [set, x] of [[diagram.leftSet, 75], [diagram.rightSet, 285]]) {
    mathLabel(svg, set.name, x, 22, true)
    set.elements.forEach((element, index) => mathLabel(svg, element, x, row(index, set.elements.length)))
  }
  panel.append(label, svg)
  return panel
}

function drawNumberLine(svg, items) {
  const low = Math.min(0, ...items.map((p) => p.x)) - 1
  const high = Math.max(1, ...items.map((p) => p.x)) + 1
  const scale = (x) => 45 + (x - low) / (high - low) * 510
  svg.append(svgNode('line', { x1: 35, y1: 125, x2: 565, y2: 125, class: 'chart-axis' }))
  for (let i = 0; i <= 8; i++) {
    const x = low + (high - low) * i / 8
    svg.append(svgNode('line', { x1: scale(x), y1: 120, x2: scale(x), y2: 130, class: 'chart-tick' }))
    svg.append(svgNode('text', { x: scale(x), y: 155, 'text-anchor': 'middle' }, Number(x.toFixed(2))))
  }
  items.forEach((p, i) => {
    svg.append(svgNode('circle', { cx: scale(p.x), cy: 125, r: 7, class: 'chart-point' }))
    chartLabel(svg, `${p.label} (${p.x})`, scale(p.x) - 70, 65 - (i % 2) * 25, 140, 'center')
  })
}

function drawBars(svg, items) {
  const low = Math.min(0, ...items.map((p) => p.x))
  const high = Math.max(1, ...items.map((p) => p.x))
  const scale = (x) => 160 + (x - low) / (high - low || 1) * 360
  const step = 170 / items.length
  svg.append(svgNode('line', { x1: scale(0), y1: 20, x2: scale(0), y2: 215, class: 'chart-axis' }))
  items.forEach((p, i) => {
    const y = 25 + i * step
    chartLabel(svg, p.label, 5, y + step / 2 - 15, 130, 'end')
    svg.append(svgNode('rect', { x: Math.min(scale(0), scale(p.x)), y, width: Math.max(2, Math.abs(scale(p.x) - scale(0))), height: Math.max(10, step - 10), rx: 5, class: 'chart-bar' }))
    svg.append(svgNode('text', { x: scale(p.x) + 10, y: y + step / 2 + 5 }, p.x))
  })
}

function drawCoordinates(svg, items) {
  const minX = Math.min(-1, ...items.map((p) => p.x)) - 1, maxX = Math.max(1, ...items.map((p) => p.x)) + 1
  const minY = Math.min(-1, ...items.map((p) => p.y)) - 1, maxY = Math.max(1, ...items.map((p) => p.y)) + 1
  const x = (n) => 50 + (n - minX) / (maxX - minX) * 500
  const y = (n) => 205 - (n - minY) / (maxY - minY) * 175
  for (let i = 0; i <= 5; i++) {
    const vx = minX + (maxX - minX) * i / 5, vy = minY + (maxY - minY) * i / 5
    svg.append(svgNode('line', { x1: x(vx), y1: 25, x2: x(vx), y2: 210, class: 'chart-grid' }))
    svg.append(svgNode('line', { x1: 45, y1: y(vy), x2: 560, y2: y(vy), class: 'chart-grid' }))
    svg.append(svgNode('text', { x: x(vx), y: 233, 'text-anchor': 'middle' }, Number(vx.toFixed(1))))
    svg.append(svgNode('text', { x: 35, y: y(vy) + 4, 'text-anchor': 'end' }, Number(vy.toFixed(1))))
  }
  svg.append(svgNode('line', { x1: 45, y1: y(0), x2: 560, y2: y(0), class: 'chart-axis' }))
  svg.append(svgNode('line', { x1: x(0), y1: 25, x2: x(0), y2: 210, class: 'chart-axis' }))
  svg.append(svgNode('polyline', { points: items.map((p) => `${x(p.x)},${y(p.y)}`).join(' '), fill: 'none', class: 'chart-line' }))
  items.forEach((p) => {
    svg.append(svgNode('circle', { cx: x(p.x), cy: y(p.y), r: 5, class: 'chart-point' }))
    chartLabel(svg, p.label, x(p.x) + 8, y(p.y) - 32, 110)
  })
}
