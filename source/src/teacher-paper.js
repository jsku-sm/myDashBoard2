import { renderMessage } from './render-message.js'
import { renderVisual } from './visuals.js'
import { STAGES } from './curriculum.js'

const node = (tag, className, text) => {
  const element = document.createElement(tag)
  element.className = className
  if (text !== undefined) element.textContent = text
  return element
}
const rich = (tag, className, text) => {
  const element = node(tag, className)
  renderMessage(element, text)
  return element
}

// This renderer has no RPC/save/answer handlers: reviewing a quiz is read-only.
export function mountTeacherPaper(root, paper, resize) {
  root.replaceChildren()
  root.className = 'teacher-paper'
  const header = node('header', 'paper-header')
  header.append(node('span', 'paper-eyebrow', 'TEACHER VIEW · 교사용 문제 확인'),
    rich('h1', '', paper.title),
    node('p', '', `${STAGES[paper.stage]?.name ?? ''} · ${paper.questions.length}문항${paper.code ? ` · 참여코드 ${paper.code}` : ''}`),
    node('p', 'paper-note', '문제와 보기를 한눈에 확인하세요. 정답·해설은 펼쳐 볼 수 있어요.'))
  const toggle = node('button', 'primary-button', '정답·해설 모두 보기')
  toggle.type = 'button'
  toggle.setAttribute('aria-expanded', 'false')
  const nav = node('nav', 'paper-nav')
  nav.setAttribute('aria-label', '문제 바로가기')
  header.append(toggle, nav)
  const list = node('main', 'paper-questions')
  const solutions = []
  const updateToggle = () => {
    const allOpen = solutions.every(d => d.open)
    toggle.textContent = allOpen ? '정답·해설 모두 숨기기' : '정답·해설 모두 보기'
    toggle.setAttribute('aria-expanded', String(allOpen))
    resize()
  }
  paper.questions.forEach((q, index) => {
    const card = node('article', 'paper-question')
    card.id = `paper-question-${index + 1}`
    card.tabIndex = -1
    card.setAttribute('aria-labelledby', `paper-title-${index + 1}`)
    const title = rich('h2', 'paper-prompt', q.prompt)
    title.id = `paper-title-${index + 1}`
    card.append(node('span', 'paper-number', `문제 ${String(index + 1).padStart(2, '0')}`), title)
    if (q.visual) card.append(renderVisual(q.visual))
    const options = node('ol', 'paper-options')
    options.setAttribute('aria-label', `${index + 1}번 문제 보기`)
    q.options.forEach((option, i) => {
      const item = node('li', 'paper-option')
      item.append(node('span', 'paper-option-number', String(i + 1)), rich('div', 'paper-option-copy', option))
      options.append(item)
    })
    const solution = node('details', 'paper-solution')
    solution.append(node('summary', '', '정답·해설 확인'))
    const content = node('div', 'paper-solution-content')
    content.append(node('h3', '', `정답 ${q.correctIndex + 1}번`),
      rich('p', 'paper-correct-answer', q.options[q.correctIndex]),
      node('h3', '', '해설'), rich('p', '', q.explanation),
      node('h3', '', '핵심 개념'), rich('p', '', q.concept), node('h3', '', '단계별 힌트'))
    const hints = node('ol', 'paper-hints')
    q.hints.forEach(hint => hints.append(rich('li', '', hint)))
    content.append(hints)
    const standard = paper.settings?.standards?.find(s => s.id === q.standardId)
    content.append(rich('p', 'paper-standard', `성취기준: ${standard?.text ?? q.standardId}`))
    solution.append(content)
    solutions.push(solution)
    solution.addEventListener('toggle', updateToggle)
    card.append(options, solution)
    list.append(card)
    const jump = node('button', 'secondary-button', `${index + 1}번`)
    jump.type = 'button'
    jump.addEventListener('click', () => {
      card.scrollIntoView({behavior: 'smooth', block: 'start'})
      card.focus({preventScroll: true})
    })
    nav.append(jump)
  })
  toggle.addEventListener('click', () => {
    const open = !solutions.every(d => d.open)
    solutions.forEach(d => { d.open = open })
    updateToggle()
  })
  root.append(header, list)
  resize()
}
