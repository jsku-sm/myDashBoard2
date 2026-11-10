const katex = window.katex;
const escapeHTML = text => String(text).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const math = tex => katex.renderToString(tex, { throwOnError: false, trust: false, strict: 'ignore' });

// Parse the controlled algebra notation used by the question generators. Text
// is escaped separately; formulas go through KaTeX with trust disabled.
export function quizMathToTex(source) {
  const normalized = String(source).replace(/⁻¹/g, '^-1').replace(/²/g, '^2').replace(/³/g, '^3').replace(/[−–]/g, '-').replace(/\s+/g, '');
  const tokens = normalized.match(/\d+(?:\.\d+)?|[a-zA-Z]+|[√π∞ℝ∅+\-*/×·^=<>≤≥≠∈∘→⇒↔(),{}\[\]]/g) || [];
  if (tokens.join('') !== normalized || !tokens.length) throw Error('Unsupported quiz formula');
  let index = 0;
  const peek = () => tokens[index];
  const atomStart = token => !!token && (/^(?:\d|[a-zA-Z])/.test(token) || ['√', 'π', '∞', 'ℝ', '∅', '(', '[', '{'].includes(token));
  const unwrap = node => node.group === '(' && node.close === ')' ? node.inner : node.tex;
  function atom() {
    const token = tokens[index++];
    if (['(', '[', '{'].includes(token)) {
      const content = relation(), close = tokens[index++];
      if (![')', ']', '}'].includes(close)) throw Error('Unclosed quiz formula');
      const left = token === '{' ? '\\{' : token, right = close === '}' ? '\\}' : close;
      return { tex: `\\left${left}${content.tex}\\right${right}`, inner: content.tex, group: token, close };
    }
    if (token === '√' || token === 'sqrt') {
      const value = atom(); return { tex: `\\sqrt{${unwrap(value)}}` };
    }
    if (/^\d/.test(token || '') || /^[a-zA-Z]+$/.test(token || '')) return { tex: token };
    const symbols = { π: '\\pi', '∞': '\\infty', 'ℝ': '\\mathbb{R}', '∅': '\\varnothing' };
    if (symbols[token]) return { tex: symbols[token] };
    throw Error('Expected a quiz math term');
  }
  function power() {
    const left = atom();
    if (peek() !== '^') return left;
    index++; const right = unary(); return { tex: `${left.tex}^{${unwrap(right)}}` };
  }
  function unary() {
    if (peek() === '-' || peek() === '+') { const sign = tokens[index++], value = unary(); return { tex: `${sign}${value.tex}` }; }
    return power();
  }
  function product() {
    let left = unary();
    while (['*', '/', '×', '·'].includes(peek()) || atomStart(peek())) {
      const op = peek(); if (['*', '/', '×', '·'].includes(op)) index++;
      const right = unary();
      left = { tex: op === '/' ? `\\frac{${unwrap(left)}}{${unwrap(right)}}` : `${left.tex}${op === '*' || op === '·' ? '\\cdot ' : op === '×' ? '\\times ' : ''}${right.tex}` };
    }
    return left;
  }
  function sum() {
    let left = product();
    while (peek() === '+' || peek() === '-') { const op = tokens[index++], right = product(); left = { tex: `${left.tex}${op}${right.tex}` }; }
    return left;
  }
  function relation() {
    let left = sum();
    const operators = { '=': '=', '<': '<', '>': '>', '≤': '\\le ', '≥': '\\ge ', '≠': '\\ne ', '∈': '\\in ', '∘': '\\circ ', '→': '\\to ', '⇒': '\\Rightarrow ', '↔': '\\leftrightarrow ', ',': ',\\,' };
    while (operators[peek()]) { const op = operators[tokens[index++]], right = sum(); left = { tex: `${left.tex}${op}${right.tex}` }; }
    return left;
  }
  const result = relation();
  if (index !== tokens.length) throw Error('Unexpected quiz math term');
  return result.tex;
}

export function quizTextParts(text) {
  return String(text).split(/([가-힣ㄱ-ㅎㅏ-ㅣ]+)/u).filter(Boolean).map(part => {
    if (/[가-힣ㄱ-ㅎㅏ-ㅣ]/u.test(part) || !/[\dA-Za-z√π∞ℝ∅]/.test(part)) return { text: part };
    const match = part.match(/^([\s.,:;!?]*)(.*?)([\s.,:;!?]*)$/s);
    const [, before, formula, after] = match;
    if (!formula) return { text: part };
    try { return { text: part, before, after, tex: quizMathToTex(formula) }; }
    catch { return { text: part, unsupported: true }; }
  });
}
function renderPlain(text) {
  return quizTextParts(text).map(part => part.tex ? `${escapeHTML(part.before)}<span class="quiz-math">${math(`\\displaystyle ${part.tex}`)}</span>${escapeHTML(part.after)}` : escapeHTML(part.text)).join('');
}

// New common-math items arrive with explicit, server-formatted LaTeX spans.
// Keep the original plain-notation renderer for previously saved function items.
export function renderQuizText(text) {
  return String(text).split(/(\$\$[\s\S]+?\$\$|\$[^$]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])/).map((part,i)=>{
    if(i%2===0)return renderPlain(part);
    const double=part.startsWith('$$')||part.startsWith('\\[');
    const trim=part.startsWith('$$')||part.startsWith('\\')?2:1;
    return '<span class="quiz-math">'+katex.renderToString(part.slice(trim,-trim),{throwOnError:false,trust:false,strict:'ignore',displayMode:double})+'</span>';
  }).join('');
}
