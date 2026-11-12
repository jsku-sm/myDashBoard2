export function normalizeMathDelimiters(text) {
  // 구분자만 보정합니다. 수식 안의 명령이나 행렬 줄바꿈(\\)은 보존합니다.
  return text.replace(/\$\$[\s\S]*?\$\$|\$[^$\n]+\$|\\+\(([\s\S]*?)\\+\)|\\+\[([\s\S]*?)\\+\]/g, (match, inline, display) => {
    if (inline !== undefined) return `\\(${inline}\\)`
    if (display !== undefined) return `\\[${display}\\]`
    return match
  })
}
