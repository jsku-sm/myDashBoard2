export function createLearningEffects(root = document, view = window) {
  const preference = view.matchMedia?.('(prefers-reduced-motion: reduce)')
  const active = new Set()
  let layer = null

  function clear() {
    for (const animation of active) animation.cancel()
    active.clear()
    layer?.remove()
    layer = null
  }

  function track(animation, done = () => {}) {
    active.add(animation)
    animation.finished.catch(() => {}).then(() => {
      active.delete(animation)
      done()
    })
  }

  function enter(element) {
    if (!element || preference?.matches || typeof element.animate !== 'function') return
    track(element.animate([
      { opacity: 0.65, transform: 'translateY(8px)' },
      { opacity: 1, transform: 'translateY(0)' },
    ], { duration: 220, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' }))
  }

  function celebrate(element, { stage = false } = {}) {
    if (preference?.matches || typeof root.documentElement.animate !== 'function') return
    if (active.size > 64) clear()
    if (!layer) {
      layer = root.createElement('div')
      layer.className = 'celebration-layer'
      layer.setAttribute('aria-hidden', 'true')
      root.body.append(layer)
    }
    const box = element?.getBoundingClientRect()
    const x = Math.max(24, Math.min(view.innerWidth - 24, box ? box.left + box.width / 2 : view.innerWidth / 2))
    const y = Math.max(64, Math.min(view.innerHeight - 48, box ? box.top + box.height / 2 : view.innerHeight / 2))
    const currentLayer = layer
    for (let i = 0; i < (stage ? 28 : 14); i++) {
      const piece = root.createElement('span')
      piece.className = `celebration-piece celebration-color-${i % 4}${i % 3 === 0 ? ' celebration-round' : ''}`
      piece.style.setProperty('--burst-x', `${x}px`)
      piece.style.setProperty('--burst-y', `${y}px`)
      currentLayer.append(piece)
      const spread = stage ? 230 : 140
      const dx = (Math.random() - 0.5) * spread * 2
      const rise = 40 + Math.random() * (stage ? 180 : 90)
      const rotation = (Math.random() - 0.5) * 480
      const animation = piece.animate([
        { opacity: 1, transform: 'translate(-50%, -50%) scale(0.7) rotate(0deg)' },
        { opacity: 1, transform: `translate(${dx * 0.6}px, ${-rise}px) rotate(${rotation * 0.5}deg)`, offset: 0.45 },
        { opacity: 0, transform: `translate(${dx}px, ${rise * 0.35}px) rotate(${rotation}deg)` },
      ], { duration: (stage ? 750 : 500) + Math.random() * 140, easing: 'cubic-bezier(0.2, 0.6, 0.4, 1)' })
      track(animation, () => {
        piece.remove()
        if (!currentLayer.childElementCount) {
          currentLayer.remove()
          if (layer === currentLayer) layer = null
        }
      })
    }
  }

  preference?.addEventListener('change', () => { if (preference.matches) clear() })
  root.addEventListener('visibilitychange', () => { if (root.hidden) clear() })
  return { enter, celebrate, clear }
}
