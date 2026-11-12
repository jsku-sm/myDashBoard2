import { UNITS } from './curriculum.js'
import { repeatedPrompts, shuffled, shuffleQuiz } from './question-history.js'

export const DEMO_SETTINGS = {
  course: '공통수학1', unit: '다항식', range: '다항식의 덧셈, 뺄셈과 곱셈',
  standards: [{ id: UNITS[0].standards[0][0], text: UNITS[0].standards[0][1] }],
  count: 3, startStage: 0,
}

const math = (s) => `\\(${s}\\)`

export function demoQuiz(stage, { previous = [], randomize = false, random = Math.random } = {}) {
  const parameters = randomize
    ? shuffled(Array.from({ length: 24 }, (_, a) => Array.from({ length: 25 }, (_, offset) => ({ a: a + 2, b: a + offset + 3 }))).flat().filter(({ a, b }) => b !== 2 * a), random)
    : [{ a: 2, b: 3 }, { a: 3, b: 4 }, { a: 4, b: 5 }]
  const questions = []
  for (const { a, b } of parameters) {
    const i = questions.length
    let prompt, options, explanation, hints, concept
    if (stage === 0) {
      prompt = `${math(`${a}x+${b}x`)}를 간단히 하면 무엇일까요?`
      options = [`${a + b}x`, `${a * b}x`, `${a + b}x^2`, `${b - a}x`, `${a}x^2+${b}`]
      explanation = `같은 문자와 차수를 가진 항은 계수끼리 더해요. ${math(`${a}x+${b}x=(${a}+${b})x=${a + b}x`)}입니다.`
      concept = '동류항과 계수'
      hints = ['두 항에 들어 있는 문자와 차수가 같은지 살펴볼까요?', '같은 종류의 항끼리는 문자 부분을 유지하고 계수끼리 계산해요.', '문자 앞에 붙은 수끼리 더해 본 뒤, 문자 부분을 다시 붙여 볼까요?']
    } else if (stage === 1) {
      prompt = `${math(`(${a}x+${b})+(x+${a})`)}를 간단히 한 식을 골라 보세요.`
      options = [`${a + 1}x+${a + b}`, `${a}x+${a + b}`, `${a + 1}x+${b - a}`, `${a + b}x+${a + 1}`, `${a + 1}x^2+${a + b}`]
      explanation = `문자항과 상수항을 각각 모으면 ${math(`(${a}+1)x+(${b}+${a})=${options[0]}`)}입니다.`
      concept = '다항식의 덧셈'
      hints = ['문자항과 상수항을 다른 색으로 표시한다고 생각해 보세요.', '괄호 앞이 더하기이면 괄호 안의 부호는 그대로 유지돼요.', '문자항끼리 한 묶음, 상수항끼리 한 묶음으로 계산해 볼까요?']
    } else if (stage === 2) {
      prompt = `한 상자에 ${math(`x+${b}`)}개의 부품이 들어 있어요. 이런 상자 ${math(`${a}`)}개와 낱개 부품 ${math('x')}개를 합친 전체 부품 수를 식으로 나타내세요.`
      options = [`${a + 1}x+${a * b}`, `${a + 1}x+${b}`, `${a}x+${a * b}`, `${a * b}x+${a}`, `${a + 1}x+${a + b}`]
      explanation = `전체 수는 ${math(`${a}(x+${b})+x=${a}x+${a * b}+x=${options[0]}`)}입니다. 괄호 안의 두 항 모두에 상자 수를 곱해요.`
      concept = '분배법칙과 상황의 식 표현'
      hints = ['상자에 들어 있는 부품과 낱개 부품을 따로 생각해 보세요.', '상자 수는 괄호 안의 문자항과 상수항 모두에 곱해져요.', '상자 속 부품을 식으로 쓴 뒤 낱개 부품을 더하고 동류항끼리 모아 볼까요?']
    } else if (stage === 3) {
      prompt = `직사각형의 가로가 ${math(`x+${a}`)}, 세로가 ${math(`x+${b}`)}일 때, 넓이를 전개한 식을 고르세요.`
      options = [`x^2+${a + b}x+${a * b}`, `x^2+${a * b}x+${a + b}`, `x^2+${a + b}x+${a + b}`, `2x^2+${a * b}`, `x^2+${b - a}x+${a * b}`]
      explanation = `각 항을 빠짐없이 곱하면 ${math(`x^2+${b}x+${a}x+${a * b}=${options[0]}`)}입니다.`
      concept = '다항식의 곱셈과 넓이'
      hints = ['직사각형을 네 작은 직사각형으로 나눈다고 생각해 보세요.', '한 괄호의 각 항을 다른 괄호의 각 항에 한 번씩 곱해요.', '곱해서 생긴 네 항 중 동류항을 찾아 한데 모아 볼까요?']
    } else {
      prompt = `다항식 ${math(`(x+${a})^3-(x-${b})^3`)}를 전개했을 때 ${math('x^2')}의 계수는 무엇일까요?`
      options = [`${3 * (a + b)}`, `${3 * (b - a)}`, `${a + b}`, `${3 * a * b}`, `${a ** 3 + b ** 3}`]
      explanation = `세제곱을 전개하면 ${math(`(x+${a})^3=x^3+${3 * a}x^2+${3 * a * a}x+${a ** 3}`)}, ${math(`(x-${b})^3=x^3-${3 * b}x^2+${3 * b * b}x-${b ** 3}`)}입니다. 빼면 ${math('x^2')}항의 계수는 ${math(`${3 * a}-(-${3 * b})=${3 * (a + b)}`)}예요.`
      concept = '세제곱 전개와 특정 차수의 계수'
      hints = ['전체 식의 모든 항을 구해야 할까요? 필요한 차수의 항만 추적해 보세요.', '곱으로 펼쳤을 때 문자 두 개와 상수 한 개를 선택하는 방법을 생각해 보세요.', '두 번째 괄호를 빼면서 그 안의 항의 부호가 어떻게 바뀌는지 확인해 볼까요?']
    }
    const correctIndex = (stage + i + 1) % 5
    const answer = options.shift()
    options.splice(correctIndex, 0, answer)
    const question = {
      prompt, options: options.map(math), correctIndex, explanation, hints, concept,
      standardId: '10공수1-01-01',
      visual: null,
    }
    if (repeatedPrompts([question], previous).length) continue
    questions.push(question)
    if (questions.length === 3) break
  }
  if (questions.length < 3) throw new Error('새 예시 문제를 준비하지 못했어요. 다시 시작해 주세요.')
  const quiz = { title: '다항식과 친해지는 시간', questions }
  return randomize ? shuffleQuiz(quiz, random) : quiz
}
