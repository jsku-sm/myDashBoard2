export async function load(url,context,nextLoad){
 if(url.endsWith('.css'))return {format:'module',shortCircuit:true,source:'export default "";'};
 if(url.endsWith('/math-arcade.js'))return {format:'module',shortCircuit:true,source:`export {GAMES,gameArt} from '${url}?original'; export function createMathArcade(api){globalThis.testArcade=api;globalThis.mounts=(globalThis.mounts||0);return {open(){},html(){return '<div id="math-arcade">GAME</div>'},mount(){globalThis.mounts++},unmount(){},action(){}};}`};
 return nextLoad(url,context);
}
