import {createArcadeAudio} from '../../../play_lab_source/src/arcade-audio.js';

// Reuse the local synthesizer, with separate preferences from the concept games.
// These effects never download audio or send additional requests to the server.
export const REWARD_AUDIO_KEY='goodssaem-reward-audio-v1';
const themes={jump:'shot',kart:'territory',space:'invaders',blocks:'bubble',maze:'maze',quiz:'memory'};
const cues={jump:'launch',lane:'tune',boost:'roll',shoot:'shoot',bounce:'bump',step:'step',collect:'collect',hit:'hit',damage:'damage',key:'capture',stage:'stage',combo:'match',countdown:'tune',start:'start',finish:'win',correct:'match',wrong:'miss'};

export function createRewardAudio({scope=globalThis,storage,contextFactory,onChange}={}){
  try{storage??=scope.localStorage;}catch{}
  const ownStorage={
    getItem(){
      let saved={};
      try{saved=JSON.parse(storage?.getItem(REWARD_AUDIO_KEY))||{};}catch{}
      return JSON.stringify({...saved,music:false});
    },
    setItem(_,value){
      const {effects,volume}=JSON.parse(value);
      storage?.setItem(REWARD_AUDIO_KEY,JSON.stringify({effects,volume}));
    }
  };
  const audio=createArcadeAudio({scope,storage:ownStorage,contextFactory,onChange});
  let scene='quiz',stopped=false;
  audio.setScene(themes[scene],'effects');
  return {
    setScene(id){scene=id in themes?id:'quiz';if(!stopped)audio.setScene(themes[scene],'effects');},
    async unlock(){
      if(scope.document?.hidden)return false;
      stopped=false;audio.setScene(themes[scene],'effects');
      return audio.unlock();
    },
    cue(name){if(!stopped&&cues[name])audio.cue(cues[name]);},
    stop(){stopped=true;audio.stop();},
    updateSettings(patch){audio.updateSettings({effects:patch.effects,volume:patch.volume,music:false});},
    get settings(){const {effects,volume}=audio.settings;return {effects,volume};},
    get status(){return audio.status;}
  };
}

// Only observe state; the deterministic simulation and server replay are unchanged.
export function soundSnapshot(s){
  return {game:s.game,t:s.t,x:s.x,y:s.y,grounded:s.grounded,lane:s.lane,
    boost:s.boost,bvy:s.bvy,vx:s.vx,hits:s.hits,combo:s.combo,key:s.key,level:s.level};
}
export function stepSounds(before,s){
  const result=[];
  const damaged=s.hits>before.hits,earned=s.combo>before.combo,stage=s.level>before.level;
  if(damaged)result.push('damage');
  if(stage)result.push('stage');
  else if(s.game==='maze'&&s.key&&!before.key)result.push('key');
  else if(s.game==='kart'&&s.boost>before.boost)result.push('boost');
  else if(earned)result.push(s.game==='space'||s.game==='blocks'?'hit':'collect');
  if(earned&&Math.floor(s.combo/5)>Math.floor(before.combo/5))result.push('combo');
  if(s.game==='jump'&&before.grounded&&!s.grounded&&s.vy<0)result.push('jump');
  if(s.game==='kart'&&s.lane!==before.lane)result.push('lane');
  if(s.game==='space'&&s.t%5===0)result.push('shoot');
  if(s.game==='blocks'&&!earned&&!damaged&&(s.bvy!==before.bvy||s.vx!==before.vx))result.push('bounce');
  if(s.game==='maze'&&!damaged&&!stage&&(s.x!==before.x||s.y!==before.y))result.push('step');
  return result;
}

// A long catch-up after a background tab or reconnect must not replay old sounds.
export function liveSoundWindow(currentTick,targetTick,hidden){return !hidden&&targetTick-currentTick<=4;}
export function clockSounds(clock,seconds){
  const left=Math.max(0,Math.ceil(seconds)),result=[];
  if(left>0&&left<=5&&clock.previous===left+1)result.push('countdown');
  if(left===0&&!clock.finished){clock.finished=true;result.push('finish');}
  clock.previous=left;
  return result;
}
