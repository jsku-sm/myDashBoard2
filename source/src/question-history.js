import { normalizeMath } from './quiz.js'
import { normalizeMathDelimiters } from './math-text.js'

export const QUESTION_HISTORY_KEY = 'quizpop.question-history.v1'
export const MAX_UNIT_QUESTIONS = 500
const MAX_UNITS = 20

const normalizedText = (text) => text.normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase()

export function unitHistoryKey(settings) {
  // 난이도·문항 수·선택 기준이 달라져도 같은 단원의 출제 이력을 공유합니다.
  return JSON.stringify([normalizedText(settings.course ?? ''), normalizedText(settings.unit?.trim() || settings.range?.trim() || '')])
}

export function questionSignatures(prompt) {
  prompt = normalizeMathDelimiters(prompt)
  const normalize = (text) => normalizeMath(text.normalize('NFKC')).replace(/[−–]/g, '-').replace(/[.,!?，。？！]/g, '')
  const signatures = [`text:${normalize(prompt)}`]
  const formulas = [...prompt.matchAll(/\\\(([\s\S]*?)\\\)|\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$|\$([^$\n]+)\$/g)]
    .map((match) => normalize(match.slice(1).find((part) => part !== undefined)))
    .filter(Boolean)
    .sort()
  // 말투나 LaTeX 구분자만 바꾼 동일 수식 문제도 중복으로 봅니다.
  if (formulas.length && formulas.some((formula) => /\d|[+\-*/=^]/.test(formula))) signatures.push(`math:${formulas.join('|')}`)
  return signatures
}

export function repeatedPrompts(questions, previous = []) {
  const seen = new Set(previous.flatMap(questionSignatures))
  const repeats = []
  for (const question of questions) {
    const signatures = questionSignatures(question.prompt)
    if (signatures.some((signature) => seen.has(signature))) repeats.push(question.prompt)
    signatures.forEach((signature) => seen.add(signature))
  }
  return repeats
}

export function shuffled(items, random = Math.random) {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

export function shuffleQuiz(quiz, random = Math.random) {
  return {
    ...quiz,
    questions: shuffled(quiz.questions, random).map((question) => {
      // 해설이 특정 보기 번호를 참조하면 그 문항의 보기 순서는 유지합니다.
      if (/[①②③④⑤]|[1-5일이삼사오첫두세네다섯]+\s*(?:번|번째)\s*(?:보기|선택|이|가|을|를|의|입니다)/.test(question.explanation)) return { ...question, options: [...question.options] }
      const indices = shuffled(question.options.map((_, index) => index), random)
      return { ...question, options: indices.map((index) => question.options[index]), correctIndex: indices.indexOf(question.correctIndex) }
    }),
  }
}

export function createQuestionHistory(storage) {
  let memory = []
  let storageUnavailable = !storage

  function read() {
    if (!storageUnavailable) {
      let raw
      try { raw = storage.getItem(QUESTION_HISTORY_KEY) ?? '[]' }
      catch { storageUnavailable = true; return memory }
      try {
        const data = JSON.parse(raw)
        memory = Array.isArray(data) ? data.filter((entry) => entry && typeof entry.key === 'string' && Array.isArray(entry.prompts))
          .slice(-MAX_UNITS).map((entry) => ({ key: entry.key, prompts: entry.prompts.filter((p) => typeof p === 'string' && p.trim()).slice(-MAX_UNIT_QUESTIONS) })) : []
      } catch { memory = [] }
    }
    return memory
  }

  return {
    get(settings) {
      return [...(read().find((entry) => entry.key === unitHistoryKey(settings))?.prompts ?? [])]
    },
    remember(settings, questions) {
      const key = unitHistoryKey(settings)
      const entries = read()
      const previous = entries.find((entry) => entry.key === key)?.prompts ?? []
      const prompts = [...new Set([...previous, ...questions.map((q) => q.prompt)])].slice(-MAX_UNIT_QUESTIONS)
      memory = [...entries.filter((entry) => entry.key !== key), { key, prompts }].slice(-MAX_UNITS)
      if (!storageUnavailable) {
        try { storage.setItem(QUESTION_HISTORY_KEY, JSON.stringify(memory)) }
        catch { storageUnavailable = true }
      }
    },
  }
}
