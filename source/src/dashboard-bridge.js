// A stable component instance keeps the original game UI alive across Streamlit reruns.
const post = (type, extra = {}) => window.parent.postMessage({isStreamlitMessage:true,type,...extra}, '*')
let current, active = null, queue = [], lastHeight = 0, resolveReady
const listeners = new Set()
export const ready = new Promise(resolve => { resolveReady = resolve })
const id = () => globalThis.crypto?.randomUUID?.() ?? `qp-${Date.now()}-${Math.random().toString(16).slice(2)}`
export const getContext = () => current
export function onContext(listener) { listeners.add(listener); return () => listeners.delete(listener) }
export function resize() {
  const app = document.getElementById('app')
  const height = Math.ceil(app?.getBoundingClientRect().height || 200) + 24
  if (height !== lastHeight) { lastHeight = height; post('streamlit:setFrameHeight', {height}) }
}
function pump() {
  if (!current || active || !queue.length) return
  const item = queue.shift()
  if (item.cancelled) { pump(); return }
  active = item
  item.timer = setTimeout(() => {
    if (active !== item) return
    active = null
    item.cleanup()
    item.reject(new Error('응답이 지연되고 있어요. 잠시 뒤 다시 시도해 주세요.'))
    pump()
  }, 180000)
  post('streamlit:setComponentValue', {dataType:'json', value:{id:item.id, action:item.action, payload:item.payload, revision:current.data.revision}})
}
export function request(action, payload, {signal} = {}) {
  return new Promise((resolve,reject) => {
    const item = {id:id(),action,payload,resolve,reject,cancelled:false}
    const abort = () => { item.cancelled=true; reject(new Error('요청이 취소되었어요.')) }
    item.cleanup = () => { clearTimeout(item.timer); signal?.removeEventListener('abort',abort) }
    if (signal?.aborted) { abort(); return }
    signal?.addEventListener('abort',abort,{once:true})
    queue.push(item);pump()
  })
}
window.addEventListener('message',event => {
  if (event.source !== window.parent || event.data?.type !== 'streamlit:render' || !event.data.args?.data) return
  const next = event.data.args
  if (current && current.data.userId !== next.data.userId) { location.reload(); return }
  current = next
  resolveReady(next)
  const reply=next.reply
  if (active && reply?.id===active.id) {
    const item=active;active=null;item.cleanup()
    if (!item.cancelled) reply.ok ? item.resolve(reply.value) : item.reject(new Error(reply.error || '요청을 처리하지 못했어요.'))
  }
  for (const listener of listeners) listener(next)
  pump();resize()
})
new ResizeObserver(resize).observe(document.getElementById('app'))
post('streamlit:componentReady',{apiVersion:1})
resize()
