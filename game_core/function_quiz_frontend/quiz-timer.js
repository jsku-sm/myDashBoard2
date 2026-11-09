export function createQuizTimer(now = () => performance.now()) {
  let accumulated = 0, started = null;
  return {
    start() { accumulated = 0; started = now(); },
    pause() { if (started !== null) { accumulated += Math.max(0, now() - started); started = null; } },
    resume() { if (started === null) started = now(); },
    reset() { accumulated = 0; started = null; },
    get seconds() { return (accumulated + (started === null ? 0 : Math.max(0, now() - started))) / 1000; },
    get running() { return started !== null; }
  };
}
export function quizTimeLabel(seconds) {
  const total = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}
