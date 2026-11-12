import 'katex/dist/katex.min.css'
import './style.css'
import { UNITS, STAGES, SOURCES } from './curriculum.js'
import { ready, request, getContext, onContext, resize } from './dashboard-bridge.js'
import { generateQuiz, askGuide } from './dashboard-quiz-api.js'
import { validateSettings, createProgress, answerQuestion, stageComplete, summarize, safeGuidance } from './quiz.js'
import { demoQuiz, DEMO_SETTINGS } from './demo.js'
import { renderMessage } from './render-message.js'
import { renderVisual } from './visuals.js'
import { createQuestionHistory } from './question-history.js'
import { createGuideLayout } from './guide-layout.js'
import { createLearningEffects } from './learning-effects.js'
import { mountTeacherPaper } from './teacher-paper.js'

const initial = await ready
if (initial.data.teacherPaper) {
  let rendered = ''
  const renderPaper = (context) => {
    if (context.data.role !== 'teacher' || !context.data.teacherPaper) return
    const next = JSON.stringify(context.data.teacherPaper)
    if (next === rendered) return
    rendered = next
    mountTeacherPaper(document.getElementById('app'), context.data.teacherPaper, resize)
  }
  renderPaper(initial)
  onContext(renderPaper)
} else {
const isAssigned = Boolean(initial.data.assignment)
const apiKey = initial.enabled ? 'server-managed' : ''
const unavailableMessage = initial.unavailableMessage || 'AI 연결이 아직 준비되지 않았어요. 선생님에게 알려 주세요. [QUIZ_NOT_READY]'
const MODEL = initial.model
let historyStorage
try {
  const prefix = `quizpop:${initial.data.userId}:${initial.data.preview ? 'teacher' : 'student'}:`
  historyStorage = {getItem:key=>window.localStorage.getItem(prefix+key), setItem:(key,value)=>window.localStorage.setItem(prefix+key,value)}
} catch { /* 저장소가 차단되면 현재 방문 동안만 이력을 유지합니다. */ }
const questionHistory = createQuestionHistory(historyStorage)
const $ = (selector) => document.querySelector(selector)
const node = (tag, className = '', text) => {
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
const action = (text, className, callback) => {
  const button = node('button', className, text)
  button.type = 'button'
  button.addEventListener('click', callback)
  return button
}
let session = null
let generationController = null
let guideController = null
let pendingGuideThread = null
let generationError = ''
let pendingStage = 0
let showingSummary = false

$('#app').innerHTML = `
  <header class="site-header">
    <a href="#" id="quizpop-home" class="wordmark" aria-label="퀴즈팝 처음 화면"><svg class="logo-mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="1" y="1" width="30" height="30" rx="8" class="logo-surface"/><path d="M16 7v18M7 16h18M9.6 9.6l12.8 12.8M9.6 22.4 22.4 9.6" class="logo-strokes"/></svg>퀴즈팝</a>
    <span class="header-description">한 문제씩, 나의 속도로.</span>
    <div class="header-actions"><button class="icon-button" id="help-button" type="button">사용 방법</button></div>
  </header>
  <div class="page-intro">
    <div class="journey-heading"><h1 id="journey-title">오늘의 수학 퀴즈</h1><p id="journey-description">배울 단원과 성취기준을 고르고, 나의 속도로 풀어 보세요.</p></div>
    <span class="session-chip" id="session-chip" role="status">학습 준비</span>
  </div>
  <main class="app-layout">
    <aside class="settings-panel">
      <details id="settings-details" open>
        <summary><span class="settings-summary-title">학습 설정</span><span id="settings-summary-info">단원과 성취기준을 선택해요.</span><span class="details-chevron" aria-hidden="true">⌄</span></summary>
        <form id="settings-form">

          <fieldset id="settings-fields">
            <section class="settings-content" aria-labelledby="content-heading">
              <h2 id="content-heading">무엇을 배울까요?</h2>
              <div class="field-pair"><div><label class="field-label" for="course">과목</label><select id="course" name="course"><option>공통수학1</option><option>공통수학2</option></select></div><div><label class="field-label" for="unit">단원</label><select id="unit" name="unit"></select></div></div>
              <label id="custom-unit-label" class="field-label" for="custom-unit" hidden>단원명 직접 입력</label><input id="custom-unit" autocomplete="off" maxlength="100" placeholder="예: 이차함수의 최댓값과 최솟값" hidden>
              <div class="label-row"><span class="field-label">성취기준</span><span class="tiny-label">여러 개 선택 가능</span></div>
              <div id="standards" class="standards-list" role="group" aria-label="성취기준 선택"></div>
              <p class="source-note">선택 문구는 원문의 요약입니다. <a id="standards-source" target="_blank" rel="noopener noreferrer">교육청 자료</a></p>
            </section>
            <section class="settings-method" aria-labelledby="method-heading">
              <h2 id="method-heading">어떻게 시작할까요?</h2>
              <label class="field-label" for="difficulty">시작 난이도</label><select id="difficulty" ></select>
              <label class="field-label" for="question-count">단계당 문항 수</label><select id="question-count" ><option value="3">3문항</option><option value="5">5문항</option><option value="7">7문항</option></select>
              <p class="method-note">한 단계의 문제를 모두 풀면 다음 난이도로 이어져요.</p>
            </section>
            <details class="additional-settings"><summary>학습 범위와 성취기준 직접 입력</summary><div class="additional-fields"><div><label class="field-label" for="range">학습 범위 <span>선택</span></label><textarea id="range" rows="2" maxlength="700" placeholder="예: 교과서 20~35쪽, 다항식의 덧셈과 곱셈"></textarea></div><div><label class="field-label" for="custom-standards">성취기준 직접 입력 <span>선택</span></label><textarea id="custom-standards" rows="2" maxlength="1500" placeholder="학교에서 사용하는 기준을 한 줄에 하나씩 입력하세요."></textarea></div></div></details>
          </fieldset>
          <div class="setup-actions"><button class="primary-button start-button" id="start-button" type="button">퀴즈 만들기</button><button class="secondary-button reset-settings" id="reset-button" type="button" hidden>설정 바꾸고 새로 시작</button><button class="text-button demo-button" id="demo-button" type="button">예시 퀴즈 체험</button><p id="setup-error" class="inline-error" role="alert" hidden></p></div>


          <p class="setup-footnote" id="setup-footnote">선택한 단계부터 최상위까지 차근차근 이어져요.</p>
        </form>
      </details>
      <div class="settings-bottom"><span id="connection-dot" hidden></span><span id="connection-label" role="status"></span></div>
    </aside>
    <section class="learning-column" aria-label="퀴즈 학습">
      <h2 class="course-heading">나의 학습 단계</h2>
      <ol class="stage-track" id="stage-track" aria-label="난이도 학습 단계"></ol>
      <div id="session-progress" class="session-progress" hidden><div><span id="progress-label"></span><strong id="progress-value"></strong></div><progress id="total-progress" max="100" value="0" aria-label="전체 학습 진행률"></progress></div>
      <section id="quiz-publication" class="quiz-publication" aria-live="polite" tabindex="-1" hidden><span class="publication-label">학생 참여코드</span><strong id="publication-code" hidden></strong><p id="publication-message"></p><button id="publication-retry" type="button" class="secondary-button" hidden>참여코드 생성 다시 시도</button></section>
      <div id="quiz-workspace" aria-live="polite"></div>
      <p class="learning-footnote">틀려도 괜찮아요. 힌트와 질문으로 다시 생각하면, 그것도 배움이에요.</p>
    </section>
    <aside class="guide-panel" aria-labelledby="guide-heading">
      <div class="guide-top"><h2 id="guide-heading">생각 길잡이</h2><p>답 대신, 다음 한 걸음.</p></div>
      <div class="guide-context" id="guide-context">퀴즈를 시작하면 함께할게요.</div>
      <div class="guide-log" id="guide-log" role="log" aria-live="polite" aria-label="생각 길잡이 대화"></div>
      <div class="guide-prompts" id="guide-prompts"></div>
      <p class="inline-error guide-error" id="guide-error" role="alert" hidden></p>
      <form id="guide-form"><label class="field-label" for="guide-input">모르는 부분 질문하기</label><div class="guide-composer"><textarea id="guide-input" rows="3" maxlength="1200" placeholder="어떤 부분이 헷갈리나요?" disabled></textarea><button id="guide-send" type="submit" disabled>질문 보내기</button></div></form>
      <p class="guide-note">정답·보기 번호를 알려주지 않아요.<br>개념을 함께 짚으며 스스로 풀도록 도와요.</p>
    </aside>
  </main>
  <div class="dashboard-save" role="status"><span id="dashboard-save-message">학습 기록 준비 중</span><button type="button" id="dashboard-save-retry" hidden>다시 저장</button></div>
  <footer class="site-footer"><span>퀴즈팝</span><p>AI 문항은 오류가 있을 수 있어요. 수업 활용 전 확인해 주세요. <button id="local-help" type="button">학습·저장 안내</button></p></footer>
  <dialog id="help-dialog" aria-labelledby="help-title"><button class="close-dialog" id="close-help" type="button" aria-label="안내 닫기">×</button><h2 id="help-title">퀴즈팝 사용 방법</h2><ol><li>단원 또는 범위와 성취기준을 선택해요.</li><li>시작 난이도와 문항 수를 정하고 퀴즈를 만들어요.</li><li>보기의 번호나 내용을 누르면 바로 채점돼요. 키보드 숫자 1~5도 사용할 수 있어요.</li><li>오답이면 힌트를 보고 다른 답을 골라요. 모르는 것은 생각 길잡이에게 물어보세요.</li><li>한 단계의 모든 문제를 맞히면 결과를 확인하고 다음 단계로 올라가요.</li></ol><div class="local-help"><h3>나의 학습 기록</h3><p>단계별 풀이와 힌트·질문 기록은 로그인한 계정에 저장됩니다. 학생은 화면 아래에서 GitHub 저장 상태를 확인할 수 있어요. 교사 체험은 학생 기록에 반영되지 않아요.</p><p>AI 연결이 준비되지 않아도 다항식 예시 퀴즈를 체험할 수 있어요.</p><p>출제 모델: <span class="model-label"></span></p></div></dialog>
`

let saveTimer = null, saving = false, saveError = '', savedJSON = '', pendingSave = null
let focusedPublication = '', publishingRetry = false, publicationRetryError = ''
function renderPublication() {
  const panel=$('#quiz-publication'), code=$('#publication-code'), message=$('#publication-message'), retry=$('#publication-retry')
  panel.hidden=isAssigned || !session?.questions.length || Boolean(generationController)
  if (panel.hidden) return
  const publication=getContext().data.publication
  const current=publication?.runId===session.runId && publication?.stage===session.stage ? publication : null
  const ready=current?.status==='ready' && /^\d{6}$/.test(current.code)
  code.hidden=!ready; code.textContent=ready ? current.code : ''
  retry.hidden=!(saveError || current?.status==='error' || publicationRetryError)
  retry.disabled=publishingRetry || saving
  retry.textContent=saveError ? '문항 다시 저장하고 참여코드 만들기' : publishingRetry ? '참여코드 확인 중…' : '참여코드 생성 다시 시도'
  message.textContent=ready ? `학생에게 위 코드를 알려 주세요. 학생 화면의 ‘참여코드 입력’에서 ${session.questions.length}문항에 참여할 수 있습니다.`
    : current?.status==='closed' ? '참여가 종료된 퀴즈입니다. 새 퀴즈를 생성하면 새 참여코드가 발급됩니다.'
    : saveError || publicationRetryError || current?.error || '문항이 준비됐어요. 참여코드를 생성하고 저장하는 중입니다…'
  panel.dataset.status=ready ? 'ready' : current?.status || (saveError ? 'error' : 'pending')
  if (ready && focusedPublication!==current.code) {
    focusedPublication=current.code
    focusContent('#quiz-publication')
  }
  resize()
}
$('#publication-retry').addEventListener('click',async()=>{
  if (publishingRetry) return
  publicationRetryError=''
  if (saveError) {saveError='';await flushSave();renderPublication();return}
  publishingRetry=true;renderPublication()
  try {await request('publish',{})}
  catch(error) {publicationRetryError=error.message}
  finally {publishingRetry=false;renderPublication()}
})
function saveStatus(message) {
  $('#dashboard-save-message').textContent = message
  $('#dashboard-save-retry').hidden = !saveError
  renderPublication()
  resize()
}
function scheduleSave() {
  if (generationController || guideController) return
  const value = {session: session ? {...session, threads:session.threads.map(t=>t.slice(-8))} : null, showingSummary}
  const serialized = JSON.stringify(value)
  if (serialized === savedJSON) return
  pendingSave = {value: JSON.parse(serialized), serialized}
  clearTimeout(saveTimer)
  saveTimer = setTimeout(flushSave, 450)
  if (!saveError) saveStatus('학습 기록 반영 대기 중…')
}
async function flushSave() {
  if (saving || saveError || !pendingSave) return
  const target=pendingSave;pendingSave=null;saving=true
  saveStatus('학습 기록 반영 중…')
  try {
    await request('save', target.value)
    savedJSON=target.serialized
    saveStatus(initial.data.preview ? '교사 체험 기록 반영됨' : '학습 기록 서버 반영됨 · 아래 GitHub 저장 상태 확인')
  } catch (error) {
    saveError=error.message
    if (!pendingSave) pendingSave=target
    saveStatus(saveError)
  } finally {saving=false;renderPublication();if(pendingSave && !saveError) void flushSave()}
}
$('#dashboard-save-retry').addEventListener('click',()=>{saveError='';void flushSave()})
window.addEventListener('beforeunload',event=>{if(pendingSave || saving){event.preventDefault();event.returnValue=''}})

const guideLayout = createGuideLayout()
const learningEffects = createLearningEffects()
$('.model-label').textContent = MODEL
STAGES.forEach((stage, i) => $('#difficulty').append(new Option(`${stage.name} (${stage.subtitle})`, i)))

function populateUnits() {
  $('#unit').replaceChildren()
  UNITS.filter((u) => u.course === $('#course').value).forEach((u) => $('#unit').append(new Option(u.name, u.id)))
  $('#unit').append(new Option('단원 / 범위 직접 입력', 'custom'))
  populateStandards()
}
function populateStandards() {
  const unit = UNITS.find((u) => u.id === $('#unit').value)
  $('#standards').replaceChildren()
  for (const [index, [id, text]] of (unit?.standards ?? []).entries()) {
    const label = node('label', 'standard-option')
    const input = node('input')
    input.type = 'checkbox'
    input.value = id
    input.checked = index === 0
    input.dataset.text = text
    const copy = node('span')
    copy.append(node('small', 'standard-code', id), node('span', '', text))
    label.append(input, copy)
    $('#standards').append(label)
  }
  const custom = !unit
  $('#custom-unit').hidden = !custom
  $('#custom-unit-label').hidden = !custom
  if (custom) $('.additional-settings').open = true
  $('#standards').hidden = custom
  $('#custom-standards').placeholder = custom ? '성취기준이나 학습목표를 반드시 입력해 주세요.' : '추가할 성취기준을 한 줄에 하나씩 입력하세요.'
  $('#standards-source').href = $('#course').value === '공통수학1' ? SOURCES.common1 : SOURCES.common2
}
function readSettings() {
  const unit = UNITS.find((u) => u.id === $('#unit').value)
  const standards = [...document.querySelectorAll('#standards input:checked')].map((input) => ({ id: input.value, text: input.dataset.text }))
  $('#custom-standards').value.split('\n').map((s) => s.trim()).filter(Boolean).forEach((text, i) => standards.push({ id: `custom-${i + 1}`, text }))
  return validateSettings({ course: $('#course').value, unit: unit?.name ?? $('#custom-unit').value.trim(), range: $('#range').value.trim(), standards, count: Number($('#question-count').value), startStage: Number($('#difficulty').value) })
}
function setConnection(state, text) {
  $('#connection-dot').dataset.state = state
  $('#connection-label').textContent = text
}
function setupLock() {
  const active = Boolean(session)
  $('#settings-fields').disabled = active
  $('#settings-summary-info').textContent = active ? `${session.settings.course} / ${session.settings.unit || '직접 입력한 범위'} / ${session.settings.count}문항씩` : '단원과 성취기준을 선택해요.'
  $('#start-button').hidden = active
  $('#reset-button').hidden = !active
  $('#demo-button').hidden = active
  $('#setup-footnote').textContent = active ? '설정을 바꾸려면 새로 시작을 눌러 주세요.' : '선택한 단계부터 최상위까지 차근차근 이어져요.'
}
function currentQuestion() { return session?.questions[session.questionIndex] }
function currentProgress() { return session?.progress[session.questionIndex] }
function abortGuide() {
  guideController?.abort()
  guideController = null
  if (pendingGuideThread?.at(-1)?.role === 'user') pendingGuideThread.pop()
  pendingGuideThread = null
  $('#guide-log').setAttribute('aria-busy', 'false')
}
function focusContent(selector, block = 'start') {
  const element = $(selector)
  if (!element) return
  element.tabIndex = -1
  element.focus({ preventScroll: true })
  element.scrollIntoView?.({ block, behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
}
function resetSession() {
  if (isAssigned) { focusContent('#quiz-workspace'); return }
  learningEffects.clear()
  generationController?.abort()
  generationController = null
  abortGuide()
  session = null
  showingSummary = false
  generationError = ''
  $('#setup-error').hidden = true
  $('#guide-error').hidden = true
  $('#guide-input').value = ''
  $('#settings-details').open = true
  setConnection(apiKey ? 'ready' : 'missing', apiKey ? 'AI 퀴즈 설정 준비됨' : '예시 퀴즈 체험 가능')
  setupLock()
  renderAll()
}
function begin(settings, mode) {
  if (isAssigned) return
  publicationRetryError=''
  learningEffects.clear()
  abortGuide()
  session = { runId: globalThis.crypto?.randomUUID?.() ?? `run-${Date.now()}-${Math.random().toString(16).slice(2)}`, settings, mode, stage: settings.startStage, questions: [], progress: [], questionIndex: 0, history: [], threads: [], previous: [] }
  showingSummary = false
  $('#setup-error').hidden = true
  setupLock()
  $('#settings-details').open = false
  void loadStage(settings.startStage)
}
async function loadStage(stage) {
  if (isAssigned) return
  if (!session || generationController) return
  abortGuide()
  const target = session
  const controller = new AbortController()
  generationController = controller
  pendingStage = stage
  generationError = ''
  renderAll()
  setConnection('loading', '맞춤 문항 생성 중')
  focusContent('#quiz-workspace')
  try {
    const previous = [...new Set([...questionHistory.get(target.settings), ...target.previous])]
    const quiz = target.mode === 'demo'
      ? demoQuiz(stage, { previous, randomize: true })
      : await generateQuiz({ apiKey, settings: target.settings, stage, previous, signal: controller.signal })
    if (generationController !== controller || session !== target) return
    questionHistory.remember(target.settings, quiz.questions)
    if (target.questions.length) {
      target.history.push({ stage: target.stage, ...summarize(target.progress), concepts: target.questions.filter((_, i) => target.progress[i].attempts.length > 1).map((q) => q.concept) })
    }
    target.stage = stage
    target.questions = quiz.questions
    target.title = quiz.title
    target.progress = createProgress(quiz.questions)
    target.questionIndex = 0
    target.threads = quiz.questions.map(() => [])
    target.previous.push(...quiz.questions.map((q) => q.prompt))
    $('#guide-input').value = ''
    $('#guide-error').hidden = true
    showingSummary = false
    setConnection('success', target.mode === 'demo' ? '예시 퀴즈 체험 중' : '맞춤 문항 준비 완료')
  } catch (error) {
    if (generationController !== controller || session !== target) return
    generationError = error.message
    setConnection('error', '문항 생성 재시도 필요')
  } finally {
    if (generationController === controller) {
      generationController = null
      renderAll()
      if (!generationError) { focusContent('#question-title'); learningEffects.enter($('#quiz-workspace')) }
    }
  }
}

function renderTrack() {
  $('#stage-track').replaceChildren()
  STAGES.forEach((stage, i) => {
    if (isAssigned && i !== session.stage) return
    const active = session && (generationController ? pendingStage : session.stage) === i
    const completed = session?.history.some((s) => s.stage === i) || (session?.stage === i && stageComplete(session.progress))
    const skipped = session && i < session.settings.startStage
    const item = node('li', [active && 'active', completed && 'complete', skipped && 'skipped'].filter(Boolean).join(' '))
    if (active) item.setAttribute('aria-current', 'step')
    item.append(node('span', 'stage-number', completed ? '✓' : String(i + 1)), node('strong', '', stage.name), node('small', '', skipped ? '선택한 시작 단계 이전' : stage.subtitle))
    $('#stage-track').append(item)
  })
  $('#session-progress').hidden = !session
  $('#session-chip').textContent = session ? session.mode === 'demo' ? '다항식 예시 체험' : `${session.settings.course} 맞춤 퀴즈` : '학습 준비'
  $('#journey-title').textContent = session ? session.settings.unit || '직접 입력한 학습 범위' : '오늘의 수학 퀴즈'
  $('#journey-description').textContent = session ? `성취기준 ${session.settings.standards.length}개, 단계마다 ${session.settings.count}문항. ${STAGES[session.settings.startStage].name}부터 최상위까지 풀어 보세요.` : '배울 단원과 성취기준을 고르고, 나의 속도로 풀어 보세요.'
  if (isAssigned) {
    $('#session-chip').textContent = `참여코드 ${initial.data.assignment.code}`
    $('#journey-title').textContent = initial.data.assignment.title
    $('#journey-description').textContent = `선생님이 준비한 ${STAGES[session.stage].name} ${session.questions.length}문항이에요. 힌트를 보며 끝까지 풀어 보세요.`
  }
  if (!session) return
  const done = session.history.reduce((sum, s) => sum + s.solved, 0) + summarize(session.progress).solved
  const total = isAssigned ? session.questions.length : (STAGES.length - session.settings.startStage) * session.settings.count
  $('#progress-label').textContent = '나의 학습 여정'
  $('#progress-value').textContent = `${done} / ${total}문항 완료`
  $('#total-progress').value = done / total * 100
}
function renderWelcome() {
  const welcome = node('div', 'welcome-card')
  welcome.append(node('h3', '', '모르면, 함께 생각해요.'), node('p', '', '오답에는 힌트가, 막히는 순간에는 생각 길잡이가 있어요. 한 단계의 문제를 모두 풀면 다음 단계로 이어져요.'))
  return welcome
}
function renderAll() {
  guideLayout.beforeRender()
  $('#app').dataset.view = !session ? 'setup' : generationController ? 'loading' : showingSummary ? 'summary' : 'study'
  renderTrack()
  const workspace = $('#quiz-workspace')
  workspace.replaceChildren()
  workspace.setAttribute('aria-busy', String(Boolean(generationController)))
  if (!session) workspace.append(renderWelcome())
  else if (generationController) {
    const loading = node('div', 'loading-card')
    loading.append(node('div', 'loading-indicator'), node('h2', '', '생각이 자라는 문제를 만들고 있어요.'), node('p', '', '선택한 성취기준과 난이도에 맞춰 문항과 힌트를 준비해요.'), node('div', 'skeleton-line'), node('div', 'skeleton-line short'), action('생성 취소', 'text-button', () => { generationController?.abort() }))
    workspace.append(loading)
  } else {
    if (generationError) workspace.append(node('p', 'error-notice', generationError))
    if (!session.questions.length) {
      const empty = node('div', 'loading-card')
      empty.append(node('h2', '', '다시 한번 준비해 볼까요?'), action('같은 설정으로 다시 생성', 'primary-button', () => void loadStage(pendingStage)))
      workspace.append(empty)
    } else if (showingSummary) workspace.append(renderSummary())
    else workspace.append(renderQuestion())
  }
  renderGuide()
  renderPublication()
  guideLayout.place()
  resize()
  scheduleSave()
}
function changeQuestion(index) {
  if (!session || index < 0 || index >= session.questions.length) return
  abortGuide()
  session.questionIndex = index
  showingSummary = false
  $('#guide-input').value = ''
  $('#guide-error').hidden = true
  renderAll()
  focusContent('#question-title')
}
function renderQuestion() {
  const q = currentQuestion(), p = currentProgress()
  const card = node('article', 'question-card')
  const top = node('div', 'question-top')
  const badge = node('span', 'difficulty-badge', `${STAGES[session.stage].name} ${session.questionIndex + 1} / ${session.questions.length}`)
  badge.setAttribute('role', 'status')
  const nav = node('nav', 'question-nav')
  nav.setAttribute('aria-label', '이번 단계 문제 선택')
  session.progress.forEach((progress, index) => {
    const b = action(progress.solved ? '✓' : String(index + 1), `question-dot ${index === session.questionIndex ? 'current' : ''} ${progress.solved ? 'solved' : ''}`, () => changeQuestion(index))
    b.setAttribute('aria-label', `${index + 1}번 문제${progress.solved ? ', 완료' : ''}`)
    if (index === session.questionIndex) b.setAttribute('aria-current', 'true')
    nav.append(b)
  })
  top.append(badge, nav)
  const standard = session.settings.standards.find((s) => s.id === q.standardId)
  const standardLabel = node('p', 'question-standard', `${q.standardId.startsWith('custom-') ? '직접 입력한 성취기준' : q.standardId} / ${standard?.text ?? q.concept}`)
  const title = rich('h2', 'question-title', q.prompt)
  title.id = 'question-title'
  card.setAttribute('aria-labelledby', title.id)
  card.append(top, title)
  if (q.visual) card.append(renderVisual(q.visual))
  const options = node('div', 'answer-options')
  options.setAttribute('role', 'group')
  options.setAttribute('aria-label', '정답을 골라 주세요')
  q.options.forEach((option, index) => {
    const wrong = p.attempts.includes(index) && index !== q.correctIndex
    const correct = p.solved && index === q.correctIndex
    const button = action('', `answer-option ${wrong ? 'is-wrong' : ''} ${correct ? 'is-correct' : ''}`, () => chooseAnswer(index))
    button.dataset.option = index
    button.disabled = p.solved || wrong
    button.append(node('span', 'option-number', String(index + 1)), rich('span', 'option-copy', option))
    if (wrong || correct) button.append(node('span', 'option-state', correct ? '정답' : '다시 생각해요'))
    options.append(button)
  })
  card.append(node('p', 'choice-instruction', '알맞은 보기를 눌러 보세요. 숫자 키 1~5로도 선택할 수 있어요.'), options)
  if (p.solved || p.hintsUsed) {
    const feedback = node('div', `answer-feedback ${p.solved ? 'feedback-success' : 'feedback-hint'}`)
    const label = node('h3', '', p.solved ? '맞았어요! 스스로 한 걸음 나아갔네요.' : p.attempts.length ? '아직 정답은 아니에요. 함께 생각해 볼까요?' : '생각을 여는 작은 힌트')
    label.id = 'feedback-title'
    label.tabIndex = -1
    const message = p.solved ? q.explanation : safeGuidance(q.hints[p.hintsUsed - 1], q, p.hintsUsed - 1)
    feedback.append(label, rich('p', '', message))
    if (!p.solved) feedback.append(node('small', '', `힌트 ${p.hintsUsed} / 3. 다른 보기를 골라 다시 도전해 보세요.`))
    card.append(feedback)
  }
  const bottom = node('div', 'question-bottom')
  const hint = action(`힌트 ${p.hintsUsed ? `${p.hintsUsed}/3` : '보기'}`, 'secondary-button', () => {
    p.hintsUsed = Math.min(3, p.hintsUsed + 1)
    renderAll()
    focusContent('#feedback-title', 'nearest')
  })
  hint.disabled = p.solved || p.hintsUsed >= 3
  const next = action(stageComplete(session.progress) ? '단계 결과 보기' : '다음 문제', 'primary-button', () => {
    if (stageComplete(session.progress)) { showingSummary = true; abortGuide(); renderAll(); focusContent('.summary-card h2'); learningEffects.enter($('.summary-card')); learningEffects.celebrate($('.summary-card h2'), { stage: true }) }
    else {
      const remaining = session.progress.findIndex((progress, index) => index > session.questionIndex && !progress.solved)
      changeQuestion(remaining >= 0 ? remaining : session.progress.findIndex((progress) => !progress.solved))
    }
  })
  next.disabled = !p.solved
  bottom.append(hint, next)
  const guideDisclosure = node('details', 'mobile-guide')
  guideDisclosure.id = 'mobile-guide'
  const guideSummary = node('summary', '', '생각 길잡이에게 질문하기')
  const guideSlot = node('div')
  guideSlot.id = 'mobile-guide-slot'
  guideDisclosure.append(guideSummary, guideSlot)
  card.append(bottom, guideDisclosure, standardLabel)
  return card
}
function chooseAnswer(index) {
  if (!session || generationController || showingSummary) return
  const before = currentProgress()
  const after = answerQuestion(currentQuestion(), before, index)
  if (after === before) return
  abortGuide()
  session.progress[session.questionIndex] = after
  renderAll()
  focusContent('#feedback-title', 'nearest')
  learningEffects.enter($('.answer-feedback'))
  if (after.solved) learningEffects.celebrate($('#feedback-title'))
}
function renderSummary() {
  const result = summarize(session.progress)
  const final = session.stage === STAGES.length - 1
  const card = node('section', 'summary-card')
  card.append(node('h2', '', final ? '최상위까지, 끝까지 해냈어요!' : `${STAGES[session.stage].name} 단계 완료!`), node('p', 'summary-subtitle', final ? '틀린 문제도 다시 생각하며 여기까지 온 과정이 실력이에요.' : '이번에 배운 개념을 가지고, 다음 도전으로 가 볼까요?'))
  const stats = node('div', 'summary-stats')
  ;[[`${result.solved}/${session.questions.length}`, '문제 완료'], [String(result.firstTry), '첫 시도 정답'], [String(result.retried), '다시 생각해 해결']].forEach(([value, label]) => {
    const stat = node('div')
    stat.append(node('strong', '', value), node('span', '', label))
    stats.append(stat)
  })
  card.append(node('h3', 'stats-heading', `${STAGES[session.stage].name} 단계 결과`), stats)
  const review = node('div', 'review-box')
  review.append(node('h3', '', '이번 단계에서 익힌 개념'))
  const concepts = node('div', 'concept-tags')
  ;[...new Set(session.questions.map((q) => q.concept))].forEach((concept) => concepts.append(node('span', '', concept)))
  review.append(concepts)
  card.append(review)
  if (isAssigned) {
    card.querySelector('h2').textContent = '선생님의 퀴즈, 모두 완료!'
    card.querySelector('.summary-subtitle').textContent = '풀이와 힌트 사용 기록을 선생님께 전달해요.'
    card.append(node('p','next-stage-note','새 퀴즈는 선생님이 알려 주신 새 참여코드로 시작해요.'), action('이번 퀴즈 다시 살펴보기','text-button',()=>changeQuestion(0)))
    return card
  }
  if (final) {
    const all = [...session.history, { ...result }]
    card.append(
      node('p', 'completion-total', `총 ${all.reduce((n, s) => n + s.solved, 0)}문항 완료, 첫 시도 정답 ${all.reduce((n, s) => n + s.firstTry, 0)}문항`),
      node('p', 'next-stage-note', '같은 단원에 다시 도전하면 이전과 다른 문제를 만나요.'),
      action('같은 단원 다시 풀기', 'primary-button', () => begin(structuredClone(session.settings), session.mode)),
      action('다른 단원 선택하기', 'text-button', resetSession),
    )
  } else {
    card.append(node('p', 'next-stage-note', `다음 학습: ${STAGES[session.stage + 1].name}, ${STAGES[session.stage + 1].subtitle}`), action(generationError ? '다음 단계 다시 생성' : `${STAGES[session.stage + 1].name} 단계 시작`, 'primary-button', () => void loadStage(session.stage + 1)))
  }
  card.append(action('이번 단계 문제 다시 보기', 'text-button', () => changeQuestion(0)))
  return card
}

function renderGuide() {
  const available = Boolean(currentQuestion()) && !generationController && !showingSummary
  if (!available) $('#guide-error').hidden = true
  $('#guide-form').hidden = !available
  $('#guide-prompts').hidden = !available
  $('.guide-note').hidden = !available
  $('#guide-context').textContent = available ? `지금 함께 보는 개념: ${currentQuestion().concept}` : showingSummary ? '잘 해냈어요. 다음 도전도 함께해요!' : '퀴즈를 시작하면 함께할게요'
  $('#guide-log').replaceChildren()
  const thread = available ? session.threads[session.questionIndex] : []
  if (!thread.length) {
    const message = node('div', 'guide-bubble')
    if (available) {
      message.append(node('strong', '', '함께 생각해 볼까요?'), node('p', '', '어디서부터 풀어야 할지 막막한가요? 헷갈리는 부분을 말해 주세요. 필요한 개념부터 하나씩 살펴볼게요.'))
    } else {
      const messageText = showingSummary && isAssigned ? '선생님이 준비한 퀴즈를 마쳤어요. 수고했어요! 완료한 문항은 다시 살펴볼 수 있어요.' : showingSummary
        ? session.stage === STAGES.length - 1 ? '선택한 학습 과정을 모두 마쳤어요. 같은 단원의 새 문제나 다른 단원으로 다시 도전할 수 있어요.' : '이번 단계를 마쳤어요. 다음 단계를 시작하면 새 문제의 개념도 함께 살펴볼게요.'
        : generationController ? '새 문제를 준비하고 있어요. 준비가 끝나면 헷갈리는 개념부터 함께 살펴봐요.' : '문제가 준비되면 궁금한 부분을 질문할 수 있어요.'
      message.append(node('p', '', messageText))
    }
    $('#guide-log').append(message)
  } else thread.forEach((message) => $('#guide-log').append(rich('div', `guide-bubble ${message.role === 'user' ? 'guide-user' : ''}`, message.content)))
  if (guideController) $('#guide-log').append(node('div', 'guide-thinking', '작은 실마리를 찾고 있어요…'))
  $('#guide-prompts').replaceChildren()
  if (available && !thread.length) ['어떤 개념이 필요한가요?', '어디서부터 시작할까요?'].forEach((text) => {
    const b = action(text, 'guide-prompt', () => { $('#guide-input').value = text; $('#guide-input').focus(); updateGuideComposer() })
    b.disabled = Boolean(guideController)
    $('#guide-prompts').append(b)
  })
  $('#guide-input').disabled = !available || Boolean(guideController)
  updateGuideComposer()
}
function updateGuideComposer() {
  $('#guide-send').disabled = $('#guide-input').disabled || !$('#guide-input').value.trim()
}
async function submitGuide(event) {
  event.preventDefault()
  const text = $('#guide-input').value.trim()
  if (!text || !currentQuestion() || guideController || generationController || showingSummary) return
  const target = session, questionIndex = session.questionIndex, q = currentQuestion()
  const thread = target.threads[questionIndex]
  const history = [...thread]
  const controller = new AbortController()
  guideController = controller
  pendingGuideThread = thread
  thread.push({ role: 'user', content: text })
  $('#guide-input').value = ''
  $('#guide-error').hidden = true
  $('#guide-log').setAttribute('aria-busy', 'true')
  renderGuide()
  try {
    const answer = target.mode === 'demo'
      ? safeGuidance(q.hints[Math.min(2, Math.floor(history.length / 2))], q)
      : await askGuide({ apiKey, settings: target.settings, question: q, history, text, hintIndex: currentProgress().hintsUsed, signal: controller.signal })
    if (guideController !== controller || session !== target || session.questionIndex !== questionIndex) return
    thread.push({ role: 'assistant', content: answer })
  } catch (error) {
    if (guideController !== controller) return
    thread.pop()
    $('#guide-input').value = text
    $('#guide-error').textContent = error.message
    $('#guide-error').hidden = false
  } finally {
    if (guideController === controller) {
      guideController = null
      pendingGuideThread = null
      $('#guide-log').setAttribute('aria-busy', 'false')
      renderGuide()
      $('#guide-input').focus()
      $('#guide-log').scrollTop = $('#guide-log').scrollHeight
      scheduleSave()
    }
  }
}

$('#quizpop-home').addEventListener('click', event => { event.preventDefault(); resetSession() })
$('#course').addEventListener('change', populateUnits)
$('#unit').addEventListener('change', populateStandards)
function startQuiz(event) {
  event.preventDefault()
  if (isAssigned) { focusContent('#quiz-workspace'); return }
  if (session) { focusContent('#quiz-workspace'); return }
  try {
    const settings = readSettings()
    if (!apiKey) throw new Error(unavailableMessage)
    begin(settings, 'ai')
  } catch (error) {
    $('#setup-error').textContent = error.message
    $('#setup-error').hidden = false
    setConnection('error', '학습 설정과 AI 연결을 확인해 주세요')
    resize()
    focusContent('#setup-error', 'nearest')
  }
}
// Handle the actual click as well as keyboard submission inside the embedded
// iframe. Native form submission is not required to start the component RPC.
$('#start-button').addEventListener('click', startQuiz)
$('#settings-form').addEventListener('submit', startQuiz)
$('#reset-button').addEventListener('click', resetSession)
$('#demo-button').addEventListener('click', () => {
  $('#course').value = '공통수학1'
  populateUnits()
  $('#range').value = DEMO_SETTINGS.range
  $('#difficulty').value = '0'
  $('#question-count').value = '3'
  $('#custom-standards').value = ''
  begin(structuredClone(DEMO_SETTINGS), 'demo')
})
$('#guide-input').addEventListener('input', updateGuideComposer)
$('#guide-input').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); $('#guide-form').requestSubmit() }
})
$('#guide-form').addEventListener('submit', submitGuide)
document.addEventListener('keydown', (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing || event.repeat || /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(event.target.tagName) || event.target.isContentEditable || $('#help-dialog').open) return
  if (/^[1-5]$/.test(event.key)) { event.preventDefault(); chooseAnswer(Number(event.key) - 1) }
})
$('#help-button').addEventListener('click', () => $('#help-dialog').showModal())
$('#local-help').addEventListener('click', () => $('#help-dialog').showModal())
$('#close-help').addEventListener('click', () => $('#help-dialog').close())
$('#help-dialog').addEventListener('click', (event) => { if (event.target === $('#help-dialog')) $('#help-dialog').close() })
populateUnits()
if (initial.data.saved?.session) {
  session=initial.data.saved.session
  const chosen=session.settings
  $('#course').value=chosen.course
  populateUnits()
  const unit=UNITS.find(u=>u.course===chosen.course && u.name===chosen.unit)
  $('#unit').value=unit?.id ?? 'custom'
  populateStandards()
  $('#custom-unit').value=unit ? '' : chosen.unit
  $('#range').value=chosen.range
  $('#difficulty').value=String(chosen.startStage)
  $('#question-count').value=String(chosen.count)
  for (const input of document.querySelectorAll('#standards input')) input.checked=chosen.standards.some(s=>s.id===input.value)
  $('#custom-standards').value=chosen.standards.filter(s=>s.id.startsWith('custom-')).map(s=>s.text).join('\n')
  showingSummary=initial.data.saved.showingSummary
  pendingStage=session.stage
  questionHistory.remember(session.settings,session.questions)
  setupLock()
  $('#settings-details').open=false
}
savedJSON=JSON.stringify({session,showingSummary})
if (isAssigned) {
  $('#app').dataset.assigned='true'
  $('.settings-panel').hidden=true
  $('#start-button').hidden=true
  $('#demo-button').hidden=true
  $('#reset-button').hidden=true
  $('#help-dialog ol').innerHTML='<li>선생님의 참여코드로 입장해요.</li><li>보기의 번호나 내용을 눌러 문제를 풀어요.</li><li>틀리면 힌트를 읽고 다른 답을 골라요.</li><li>모르는 부분은 생각 길잡이에게 질문해요.</li><li>모든 문항을 푼 뒤 결과와 저장 상태를 확인해요.</li>'
  $('.local-help').hidden=true
}
saveStatus(initial.data.preview ? '교사 체험 · 학생 기록과 분리' : '학습 기록을 자동으로 반영합니다.')
onContext(renderPublication)
setConnection(isAssigned ? 'ready' : apiKey ? 'ready' : 'missing', isAssigned ? '선생님의 퀴즈 참여 중' : apiKey ? 'AI 퀴즈 설정 준비됨' : '예시 퀴즈 체험 가능')
renderAll()

}
