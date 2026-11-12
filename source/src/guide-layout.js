// 화면 크기에 따라 같은 질문 패널을 옮깁니다. 폼과 이벤트 연결은 그대로 유지합니다.
export function createGuideLayout(root = document, view = window) {
  const guide = root.querySelector('.guide-panel')
  const home = root.querySelector('.app-layout')
  const media = view.matchMedia?.('(max-width: 60rem)')
  let open = root.querySelector('#mobile-guide')?.open ?? false

  function place() {
    const disclosure = root.querySelector('#mobile-guide')
    const slot = root.querySelector('#mobile-guide-slot')
    if (media?.matches && disclosure && slot) {
      if (guide.parentElement !== slot) {
        slot.append(guide)
        disclosure.open = open
      }
    } else if (guide.parentElement !== home) {
      open = disclosure?.open ?? open
      home.append(guide)
    }
  }

  media?.addEventListener('change', place)
  return {
    beforeRender() {
      open = root.querySelector('#mobile-guide')?.open ?? open
      if (guide.parentElement !== home) home.append(guide)
    },
    place,
  }
}
