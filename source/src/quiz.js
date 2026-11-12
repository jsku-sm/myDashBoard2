import { normalizeMathDelimiters } from './math-text.js'

export function validateSettings(settings) {
  if (!settings.unit?.trim() && !settings.range?.trim()) throw new Error('단원명이나 학습 범위를 입력해 주세요.')
  if (!Array.isArray(settings.standards) || !settings.standards.length || settings.standards.some((s) => !s.id || !s.text?.trim())) {
    throw new Error('성취기준을 하나 이상 선택하거나 직접 입력해 주세요.')
  }
  if (![3, 5, 7].includes(settings.count)) throw new Error('단계당 문항 수를 다시 선택해 주세요.')
  if (!Number.isInteger(settings.startStage) || settings.startStage < 0 || settings.startStage > 4) throw new Error('시작 난이도를 선택해 주세요.')
  return settings
}

const string = { type: 'string' }
const mappingSet = {
  type: 'object', additionalProperties: false, required: ['name', 'elements'],
  properties: { name: string, elements: { type: 'array', minItems: 1, maxItems: 6, items: string } },
}
export function quizSchema(count) {
  return {
    type: 'object', additionalProperties: false, required: ['title', 'questions'],
    properties: {
      title: string,
      questions: {
        type: 'array', minItems: count, maxItems: count,
        items: {
          type: 'object', additionalProperties: false,
          required: ['prompt', 'standardId', 'concept', 'options', 'correctIndex', 'hints', 'explanation', 'visual'],
          properties: {
            prompt: string, standardId: string, concept: string,
            options: { type: 'array', minItems: 5, maxItems: 5, items: string },
            correctIndex: { type: 'integer', minimum: 0, maximum: 4 },
            hints: { type: 'array', minItems: 3, maxItems: 3, items: string },
            explanation: string,
            visual: {
              anyOf: [{
                type: 'object', additionalProperties: false, required: ['type', 'title', 'caption', 'items'],
                properties: {
                  type: { type: 'string', enum: ['concept', 'bars', 'number_line', 'coordinate'] },
                  title: string, caption: string,
                  items: {
                    type: 'array', minItems: 1, maxItems: 8,
                    items: {
                      type: 'object', additionalProperties: false, required: ['label', 'x', 'y'],
                      properties: { label: string, x: { type: 'number' }, y: { type: 'number' } },
                    },
                  },
                },
              }, {
                type: 'object', additionalProperties: false, required: ['type', 'title', 'caption', 'diagrams'],
                properties: {
                  type: { type: 'string', enum: ['mapping'] }, title: string, caption: string,
                  diagrams: {
                    type: 'array', minItems: 1, maxItems: 5,
                    items: {
                      type: 'object', additionalProperties: false, required: ['label', 'leftSet', 'rightSet', 'connections'],
                      properties: {
                        label: string, leftSet: mappingSet, rightSet: mappingSet,
                        connections: {
                          type: 'array', minItems: 0, maxItems: 36,
                          items: {
                            type: 'object', additionalProperties: false, required: ['from', 'to'],
                            properties: { from: { type: 'integer', minimum: 0, maximum: 5 }, to: { type: 'integer', minimum: 0, maximum: 5 } },
                          },
                        },
                      },
                    },
                  },
                },
              }, { type: 'null' }],
            },
          },
        },
      },
    },
  }
}

export function validateQuiz(data, settings) {
  const invalid = () => { throw new Error('문항 구성을 확인하지 못했어요. 같은 설정으로 다시 생성해 주세요.') }
  if (!data || typeof data.title !== 'string' || !Array.isArray(data.questions) || data.questions.length !== settings.count) invalid()
  const standards = new Set(settings.standards.map((s) => s.id))
  const prompts = new Set()
  for (const q of data.questions) {
    if (!q || ['prompt', 'concept', 'explanation'].some((key) => typeof q[key] !== 'string' || !q[key].trim())) invalid()
    if (!standards.has(q.standardId) || prompts.has(q.prompt.trim())) invalid()
    prompts.add(q.prompt.trim())
    if (!Array.isArray(q.options) || q.options.length !== 5 || q.options.some((o) => typeof o !== 'string' || !o.trim())) invalid()
    if (new Set(q.options.map(normalizeMath)).size !== 5) invalid()
    if (!Number.isInteger(q.correctIndex) || q.correctIndex < 0 || q.correctIndex > 4) invalid()
    if (!Array.isArray(q.hints) || q.hints.length !== 3 || q.hints.some((h) => typeof h !== 'string' || !h.trim())) invalid()
    const v = q.visual
    if (v === null) continue
    if (!v || !['concept', 'bars', 'number_line', 'coordinate', 'mapping'].includes(v.type) || typeof v.title !== 'string' || typeof v.caption !== 'string') invalid()
    if (v.type === 'mapping') {
      if (!Array.isArray(v.diagrams) || !v.diagrams.length || v.diagrams.length > 5) invalid()
      const diagramLabels = new Set()
      for (const diagram of v.diagrams) {
        if (!diagram || typeof diagram.label !== 'string' || !diagram.label.trim() || diagram.label.length > 40 || diagramLabels.has(diagram.label.trim())) invalid()
        diagramLabels.add(diagram.label.trim())
        for (const set of [diagram.leftSet, diagram.rightSet]) {
          if (!set || typeof set.name !== 'string' || !set.name.trim() || set.name.length > 40) invalid()
          if (!Array.isArray(set.elements) || !set.elements.length || set.elements.length > 6) invalid()
          if (set.elements.some((label) => typeof label !== 'string' || !label.trim() || label.length > 80)) invalid()
          const labels = set.elements.map((label) => label.trim().replace(/\\[()[\]]|\$|\s/g, ''))
          if (new Set(labels).size !== labels.length) invalid()
        }
        if (!Array.isArray(diagram.connections) || diagram.connections.length > 36) invalid()
        const edges = new Set()
        for (const edge of diagram.connections) {
          if (!edge || !Number.isInteger(edge.from) || !Number.isInteger(edge.to) || edge.from < 0 || edge.to < 0 || edge.from >= diagram.leftSet.elements.length || edge.to >= diagram.rightSet.elements.length) invalid()
          const key = `${edge.from}:${edge.to}`
          if (edges.has(key)) invalid()
          edges.add(key)
        }
      }
    } else {
      if (!Array.isArray(v.items) || !v.items.length || v.items.length > 8) invalid()
      if (v.items.some((item) => !item || typeof item.label !== 'string' || !Number.isFinite(item.x) || !Number.isFinite(item.y) || Math.abs(item.x) > 1e6 || Math.abs(item.y) > 1e6)) invalid()
    }
  }
  return data
}

export function createProgress(questions) {
  return questions.map(() => ({ solved: false, attempts: [], hintsUsed: 0 }))
}

export function answerQuestion(question, progress, option) {
  if (!Number.isInteger(option) || option < 0 || option >= question.options.length) return progress
  if (progress.solved || progress.attempts.includes(option)) return progress
  const correct = option === question.correctIndex
  return { solved: correct, attempts: [...progress.attempts, option], hintsUsed: correct ? progress.hintsUsed : Math.min(3, progress.hintsUsed + 1) }
}

export function stageComplete(progress) {
  return progress.length > 0 && progress.every((p) => p.solved)
}

export function summarize(progress) {
  return {
    solved: progress.filter((p) => p.solved).length,
    firstTry: progress.filter((p) => p.solved && p.attempts.length === 1).length,
    retried: progress.filter((p) => p.solved && p.attempts.length > 1).length,
  }
}

export function normalizeMath(text) {
  return normalizeMathDelimiters(text).replace(/\\[()[\]]|\$|\s|[{}]/g, '').replace(/\\(?:left|right)/g, '').toLowerCase()
}

// 정답과 해설은 도우미 요청에 넣지 않습니다. 직접적인 정답 노출도 표시 전에 검사합니다.
export function guideContext(settings, question) {
  return {
    audience: '특성화고등학교 1학년 수학', unit: settings.unit, range: settings.range,
    standards: settings.standards, concept: question.concept, question: question.prompt,
    ...(question.visual?.type === 'mapping' ? { visual: question.visual } : {}),
  }
}

export function safeGuidance(text, question, hintIndex = 0) {
  const fallback = '먼저 문제에서 주어진 조건과 구하려는 것을 나누어 적어 볼까요? 지금 어떤 개념이나 계산 단계가 가장 헷갈리는지 알려 주세요.'
  if (typeof text !== 'string' || !text.trim()) return fallback
  const answer = normalizeMath(question.options[question.correctIndex])
  const normalized = normalizeMath(text)
  const revealsAnswer = answer && (answer.length > 2 ? normalized.includes(answer) : new RegExp(`(^|[^0-9a-z])${answer.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^0-9a-z]|$)`, 'i').test(normalized))
  const revealsChoice = /(?:정답|답)(?:은|는|\s*[:：])|[①②③④⑤]|(?:[1-5일이삼사오])\s*번\s*(?:이|가|을|를|입니다|이야|선택|고르|보기)/.test(text)
  if (!revealsAnswer && !revealsChoice) return text
  const hint = question.hints[Math.min(2, hintIndex)]
  return hint && hint !== text ? safeGuidance(hint, { ...question, hints: [] }) : fallback
}
