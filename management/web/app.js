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
      del.disabled=true; try {await post('/api/tasks/delete',{id:task.id}); notice('任务已删除'); await refresh();} catch(e){notice(e.message);del.disabled=false;}
    }; row.append(info,del); el('tasks').append(row);
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
refresh();setInterval(refresh,3000);
