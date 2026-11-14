'use strict';
const el = id => document.getElementById(id);
let token = '', loading = false, selected = null;
const node = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
function notice(text) { el('notice').textContent = text; }
async function post(path, body) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json','X-MG-Token':token}, body:JSON.stringify(body)});
  const result = await response.json(); if (!response.ok) throw new Error(result.error || '请求失败'); return result;
}
function detail(item) {
  selected = [item.vhost,item.app,item.stream].join('/');
  el('detail').replaceChildren(node('b', `${item.app} / ${item.stream}`), node('p', `vhost：${item.vhost}`), node('p','媒体已注册 · 播放尚未验证'));
  if (!item.tracks.length) el('detail').append(node('p','暂无轨道数据'));
  for (const track of item.tracks) el('detail').append(node('pre', JSON.stringify(track, null, 2)));
}
function render(state) {
  if (observedTask) {
    const item=(state.media || []).find(m=>m.vhost==='__defaultVhost__' && m.app==='mgui' && m.stream==='ui_'+observedTask);
    record('readers', {task:observedTask, value:state.connected && item ? item.totalReaders : null});
  }
  el('connection').textContent = state.connected ? '● 网关 API 已连接' : '● 网关不可达';
  el('online').textContent = state.connected ? state.media.length : '—';
  el('taskCount').textContent = state.tasks.length;
  el('updated').textContent = `采集时间 ${new Date().toLocaleTimeString()}`;
  el('streams').replaceChildren();
  if (!state.connected || !state.media.length) {
    const row = node('tr'), cell = node('td', state.connected ? '暂无在线流。可以从右侧创建 RTSP 拉流任务。' : '网关不可达，当前流状态未知；不会显示为零路在线。'); cell.colSpan=4; row.append(cell); el('streams').append(row);
    el('detail').textContent = state.connected ? '暂无在线媒体。媒体注册与浏览器播放是独立状态。' : '连接已中断，轨道详情暂不可用。';
  }
  for (const item of state.media || []) {
    const row=node('tr'); row.append(node('td',`${item.app} / ${item.stream}`)); const protocols=node('td');
    item.protocols.forEach(p => protocols.append(node('span',p,'badge'))); row.append(protocols,node('td',item.totalReaders ?? '暂不可用'));
    const cell=node('td'), button=node('button','查看','link'); button.onclick=()=>detail(item); cell.append(button); row.append(cell); el('streams').append(row);
  }
  if (selected) {
    const current=(state.media || []).find(m=>[m.vhost,m.app,m.stream].join('/')===selected);
    if (current) detail(current); else {selected=null;el('detail').textContent='所选流已下线或状态不可用。';}
  }
  el('tasks').replaceChildren();
  if (!state.tasks.length) el('tasks').append(node('p','还没有管理任务。已有外部流会显示在上方，不能在这里删除。','hint'));
  for (const task of state.tasks) {
    const row=node('div',undefined,'task'), info=node('div');
    const online=(state.media || []).some(m=>m.vhost==='__defaultVhost__' && m.app===task.app && m.stream===task.stream);
    info.append(node('b',task.name),node('small',`${state.connected ? (online ? '媒体已注册' : '未发现注册媒体') : '状态未知'} · ${task.state}`),node('small',`${task.app}/${task.stream}`));
    const del=node('button','删除','delete'); del.disabled=task.state==='提交中'; del.onclick=async()=>{
      if (!confirm(`删除“${task.name}”的拉流任务？会中断该任务的播放。`)) return;
      del.disabled=true; try {await post('/api/tasks/delete',{id:task.id}); if(activeTask===task.id) stopPlayer(); notice('任务已删除'); await refresh();} catch(e){notice(e.message);del.disabled=false;}
    }; const play=node('button','播放','link'); play.disabled=!online; play.onclick=()=>startPlayer(task); row.append(info,play,del); el('tasks').append(row);
  }
}
async function refresh() {
  if(loading) return; loading=true;
  try {const response=await fetch('/api/state'); if(!response.ok) throw new Error('管理服务返回错误'); const state=await response.json(); token=state.token; render(state);}
  catch(e){el('connection').textContent='● 管理服务不可达';el('online').textContent='—';el('streams').replaceChildren();el('tasks').textContent='采集失败，任务状态未知';el('detail').textContent='采集失败，旧数据已失效';notice(e.message);}
  finally{loading=false;}
}
el('refresh').onclick=refresh;
el('add').onsubmit=async event=>{event.preventDefault();el('submit').disabled=true;notice('正在提交拉流请求，最多等待约 15 秒…');try{const result=await post('/api/tasks',{name:el('name').value,url:el('url').value.trim()});el('url').value='';notice(result.task.state);await refresh();}catch(e){notice(e.message);}finally{el('submit').disabled=false;}};
const video=el('video');
let player=null, generation=0, activeTask=null, observedTask=null, readyTimer=null, frameCallback=null, libraryPromise=null;
const events=[];
function record(event, data={}) {events.push({time:new Date().toISOString(),event,...data});if(events.length>600) events.shift();}
function playerState(message) {el('playerState').textContent=message;record('state',{message,task:activeTask});}
function stopPlayer(message='已停止播放；等待网关读者会话过期') {
  generation++;clearTimeout(readyTimer);
  if(frameCallback!==null && video.cancelVideoFrameCallback) video.cancelVideoFrameCallback(frameCallback);
  frameCallback=null;
  if(player){player.destroy();player=null;}
  video.onplaying=video.onwaiting=video.onerror=null;
  video.pause();video.removeAttribute('src');video.load();activeTask=null;playerState(message);
}
function loadLibrary() {
  if(window.Hls) return Promise.resolve(window.Hls);
  if(libraryPromise) return libraryPromise;
  libraryPromise=new Promise((resolve,reject)=>{
    const script=document.createElement('script');script.src='https://cdn.jsdelivr.net/npm/hls.js@1.6.13/dist/hls.min.js';
    const timer=setTimeout(()=>{script.remove();reject(new Error('播放器依赖加载超时，请检查 Windows 到 CDN 的网络后重试'));},12000);
    script.onload=()=>{clearTimeout(timer);window.Hls ? resolve(window.Hls) : reject(new Error('播放器依赖无效'));};
    script.onerror=()=>{clearTimeout(timer);script.remove();reject(new Error('播放器依赖加载失败，请检查 CDN 网络'));};document.head.append(script);
  }).catch(e=>{libraryPromise=null;throw e;});return libraryPromise;
}
async function startPlayer(task) {
  stopPlayer('准备播放…');activeTask=task.id;observedTask=task.id;el('playerName').textContent=task.name;
  const current=generation;
  const url=`/media/${task.id}/${crypto.randomUUID().replaceAll('-','')}/hls.m3u8`;
  record('start',{task:task.id});playerState('正在加载 HLS，等待切片与解码…');
  const fail=message=>{if(current===generation)stopPlayer(message);};
  readyTimer=setTimeout(()=>fail('等待画面超过 45 秒，已停止；检查测试源和服务端日志后重试'),45000);
  const displayed=()=>{if(current!==generation)return;clearTimeout(readyTimer);playerState(`浏览器已显示视频帧 · ${video.videoWidth}×${video.videoHeight}`);};
  if(video.requestVideoFrameCallback)frameCallback=video.requestVideoFrameCallback(displayed);
  video.onplaying=()=>{if(current!==generation)return;if(!video.requestVideoFrameCallback){clearTimeout(readyTimer);playerState('浏览器报告正在播放，请确认可见画面');}};
  video.onwaiting=()=>{if(current===generation)playerState('正在缓冲，等待媒体数据…');};
  video.onerror=()=>fail(`浏览器媒体错误 ${video.error?.code ?? ''}，已停止`);
  try {
    video.muted=true;
    if(video.canPlayType('application/vnd.apple.mpegurl')) {video.src=url;await video.play();}
    else {
      const Hls=await loadLibrary();if(current!==generation)return;
      if(!Hls.isSupported())throw new Error('浏览器不支持此 HLS 播放方式');
      player=new Hls({enableWorker:false});
      player.on(Hls.Events.ERROR,(_,data)=>{record('hls-error',{details:data.details,fatal:data.fatal});if(data.fatal)fail('HLS 播放失败：'+data.details);});
      player.on(Hls.Events.MANIFEST_PARSED,()=>{if(current===generation)video.play().catch(()=>fail('浏览器拒绝开始播放，请重试'));});
      player.loadSource(url);player.attachMedia(video);
    }
  } catch(e){fail(e.message);}
}
el('stopPlay').onclick=()=>stopPlayer();
el('exportPlay').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({version:'0.2',userAgent:navigator.userAgent,events},null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download='mediagateway-playback-'+Date.now()+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
window.addEventListener('pagehide',()=>stopPlayer());
refresh();setInterval(refresh,3000);
