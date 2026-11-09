// Run from any directory: node game_core/function_quiz_source/export-bank.mjs
// These generator files are copied unchanged from the teacher-supplied app.
import { writeFileSync } from 'node:fs';
import { QUIZ_TOPICS } from './quiz-generator.js';
import { QUIZ_LEVELS, createLevelQuiz, levelVariantIds } from './quiz-levels.js';
const questions=[];
for(let level=1;level<=5;level++)for(let topic=0;topic<6;topic++){
  for(const variant of levelVariantIds(topic,level)){
    const q=createLevelQuiz(topic,variant,level,()=>.5);
    if(new Set(q.options).size!==3||!Number.isInteger(q.answer)||q.answer<0||q.answer>2)throw Error('Invalid question');
    questions.push({id:`${level}:${topic}:${variant}`,level,topic,prompt:q.q,options:q.options,answer:q.answer,explanation:q.why});
  }
}
writeFileSync(new URL('../function_quiz_bank.json',import.meta.url),JSON.stringify({version:1,topics:QUIZ_TOPICS,levels:QUIZ_LEVELS,questions},null,2)+'\n');
console.log(`Exported ${questions.length} source questions (6 topics × 5 levels).`);
