"""Display-only LaTeX for the bank's plain-text notation; never edits answers.

Keep Korean prose outside math and preserve teacher-authored math delimiters.
This is a notation formatter, not an algebra parser or a source of new values.
"""
import re

SUP = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺ⁿ', '0123456789-+n')
SUB = str.maketrans('₀₁₂₃₄₅₆₇₈₉₋₊', '0123456789-+')
SYMBOLS = {'−':'-', '×':r'\times ', '÷':r'\div ', '≤':r'\le ', '≥':r'\ge ',
           '≠':r'\ne ', '∪':r'\cup ', '∩':r'\cap ', '∈':r'\in ', '∉':r'\notin ',
           '⊂':r'\subset ', '⊆':r'\subseteq ', '⇒':r'\Rightarrow ', '⇔':r'\Leftrightarrow ',
           '→':r'\to ', '∘':r'\circ ', '∞':r'\infty ', 'π':r'\pi ', '±':r'\pm '}
CHUNK = re.compile(r'[A-Za-z0-9⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺ⁿ₀₁₂₃₄₅₆₇₈₉₋₊+−\-*/^_=<>≤≥≠×÷√∪∩∈∉⊂⊆⇒⇔→∘∞π±()\[\]{},.:|! \t]+')
EXPLICIT = re.compile(r'(\$\$[\s\S]+?\$\$|(?<!\\)\$[^\n$]+?(?<!\\)\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])')
TOKENS = re.compile(r'\d+(?:\.\d+)?|[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺ⁿ]+|[₀₁₂₃₄₅₆₇₈₉₋₊]+|\.{3}|[^\s]')


class _Notation:
    def __init__(self, text):
        self.tokens = TOKENS.findall(text)
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else ''

    def take(self):
        value = self.peek(); self.i += 1
        return value

    def atom(self):
        token = self.take()
        if token == '√':
            _, inner = self.atom()
            value = r'\sqrt{' + inner + '}'
            bare = value
        elif token in ('(', '[', '{', '|'):
            closer = {'(':')', '[':']', '{':'}', '|':'|'}[token]
            # The bank writes matrices as [[a,b],[c,d]]. Preserve every cell.
            if token == '[' and self.peek() == '[':
                row_parts = []
                while self.peek() == '[':
                    self.take(); row = self.sequence(']', matrix_row=True)
                    if self.peek() != ']': raise ValueError('unclosed matrix')
                    self.take(); row_parts.append(row)
                    if self.peek() == ',': self.take()
                if self.peek() != ']': raise ValueError('unclosed matrix')
                self.take()
                value = r'\begin{bmatrix}' + r' \\ '.join(row_parts) + r'\end{bmatrix}'
                bare = value
            else:
                inside = self.sequence(closer)
                if self.peek() == closer:
                    self.take()
                    left, right = (r'\{', r'\}') if token == '{' else (token, closer)
                    if token == '|': left, right = r'\lvert ', r'\rvert '
                    value = left + inside + right
                    bare = inside if token in ('(', '[') else value
                else:
                    # Prose may interrupt a parenthesis (e.g. n(A의 여집합)).
                    value = (r'\{' if token == '{' else token) + inside
                    bare = value
        else:
            value = SYMBOLS.get(token, r'\ldots ' if token == '...' else r'\}' if token == '}' else token)
            bare = value
        while self.peek() and (self.peek()[0] in '⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺ⁿ₀₁₂₃₄₅₆₇₈₉₋₊' or self.peek() in ('^','_')):
            power = self.take()
            if power[0] in '⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺ⁿ': suffix = '^{'+power.translate(SUP)+'}'
            elif power[0] in '₀₁₂₃₄₅₆₇₈₉₋₊': suffix = '_{'+power.translate(SUB)+'}'
            else:
                sign = self.take() if self.peek() in ('-','−','+') else ''
                if not self.peek(): raise ValueError('missing exponent')
                _, exponent = self.atom()
                suffix = power+'{'+sign.replace('−','-')+exponent+'}'
            value += suffix; bare = value
        return value, bare

    def sequence(self, stop='', matrix_row=False):
        parts = []
        while self.peek() and (not stop or self.peek() != stop):
            if self.peek() == '/' and parts:
                self.take()
                sign = self.take() if self.peek() in ('-','−','+') else ''
                if not self.peek(): raise ValueError('missing denominator')
                _, denominator = self.atom()
                _, numerator = parts.pop()
                value = r'\frac{'+numerator+'}{'+sign.replace('−','-')+denominator+'}'
                parts.append((value, value))
            elif matrix_row and self.peek() == ',':
                self.take(); parts.append((' & ', ' & '))
            elif self.peek().isdigit() and self.i+2 < len(self.tokens) and self.tokens[self.i+1] in ('C','P') and self.tokens[self.i+2].isdigit():
                n, kind, r = self.take(), self.take(), self.take()
                value = '{}_{'+n+r'}\mathrm{'+kind+'}_{'+r+'}'
                parts.append((value, value))
            else: parts.append(self.atom())
        return ''.join(value for value, _ in parts)


def latex(expression):
    """Translate notation only. Existing explicit LaTeX bypasses this function."""
    return _Notation(expression).sequence()


def _plain(text):
    def convert(match):
        raw = match.group()
        # Leave English words, punctuation and non-mathematical captions alone.
        if re.search(r'[A-Za-z]{3,}', raw) or not re.search(r'[A-Za-z0-9∞π]', raw): return raw
        core = raw.strip(' \t,.:')
        if not core: return raw
        start = raw.index(core)
        before, after = raw[:start], raw[start+len(core):]
        try: value = latex(core)
        except (ValueError, RecursionError): return raw
        return before+'$'+value+'$'+after
    return CHUNK.sub(convert, text)


def markdown(text):
    """Return Streamlit Markdown with safe, native KaTeX math spans."""
    parts = EXPLICIT.split(str(text))
    for i, part in enumerate(parts):
        if i % 2:
            if part.startswith(r'\('): parts[i] = '$'+part[2:-2]+'$'
            elif part.startswith(r'\['): parts[i] = '\n\n$$\n'+part[2:-2]+'\n$$\n\n'
        else: parts[i] = _plain(part)
    return ''.join(parts)
