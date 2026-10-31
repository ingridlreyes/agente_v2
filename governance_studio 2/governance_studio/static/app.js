'use strict';
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('gs-token') || '', cid = '', theme = {}, isBusy = false, demoMode = false;
let sessions = JSON.parse(sessionStorage.getItem('gs-sessions') || '[]');
const jobs = new Map();
const welcomeTemplate = document.querySelector('.welcome').cloneNode(true);
function toast(error) { $('toast').textContent=String(error.message || error); $('toast').hidden=false; setTimeout(()=>$('toast').hidden=true,6500); }
async function api(path, body) {
  const response = await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const result = await response.json();
  if(!response.ok) throw new Error(result.error || 'No se pudo completar la operación');
  return result;
}
function message(role,text,sources=[]) {
  const welcome = document.querySelector('.welcome'); if(welcome)welcome.remove();
  const article=document.createElement('article');article.className='message '+role;
  const name=document.createElement('div');name.className='role';name.textContent=role==='user'?'TÚ':'GOVERNANCE STUDIO';article.append(name);
  const content=document.createElement('div');content.textContent=text;article.append(content);
  if(sources.length){const refs=document.createElement('div');refs.className='sources';refs.textContent=sources.map(s=>'['+s.id+'] '+s.title+' · '+s.locator).join('\n');article.append(refs);}
  $('messages').append(article);$('messages').scrollTop=$('messages').scrollHeight;
}
function sessionList(){
  $('sessions').replaceChildren();
  for(const s of sessions){const b=document.createElement('button');b.textContent=s.title;b.className=s.id===cid?'active':'';b.addEventListener('click',()=>load(s.id).catch(toast));$('sessions').append(b);}
  sessionStorage.setItem('gs-sessions',JSON.stringify(sessions));
}
async function load(id){
  const data=await api('/api/conversations/'+id);cid=id;theme=data.theme;
  $('client').value=theme.client;$('primary').value=theme.primary;$('accent').value=theme.accent;
  $('messages').replaceChildren();
  if(!data.messages.length)$('messages').append(welcomeTemplate.cloneNode(true));
  for(const m of data.messages)message(m.role,m.content);
  $('memory').textContent=JSON.stringify(data.memory,null,2);sessionList();await artifacts(data.artifacts);
}
async function newConversation(){
  if(isBusy) return;
  const result=await api('/api/conversations',{theme:{client:$('client').value||'Cliente',primary:$('primary').value,accent:$('accent').value,font:'Arial',logo_id:null}});
  sessions.unshift({id:result.conversation_id,title:'Nueva conversación'});await load(result.conversation_id);
}
async function download(aid,version,name){
  const response=await fetch('/api/artifacts/'+aid+'/files/'+name+'?version='+version,{headers:{Authorization:'Bearer '+token}});
  if(!response.ok) throw new Error('No se pudo descargar el archivo');
  const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download='v'+version+'-'+name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
}
async function artifacts(records){
  $('artifacts').replaceChildren();
  if(!records.length){const p=document.createElement('p');p.className='empty';p.textContent='Tus documentos aparecerán aquí.';$('artifacts').append(p);return;}
  for(const record of records){
    const card=document.createElement('article');card.className='artifact';
    const meta=document.createElement('div');meta.className='version';meta.textContent='VERSIÓN '+record.version;card.append(meta);
    const data=await api('/api/artifacts/'+record.artifact+'?version='+record.version);
    const title=document.createElement('h3');title.textContent=data.spec.title;card.append(title);
    const buttons=document.createElement('div');buttons.className='downloads';
    const files=record.formats.map(f=>['entregable.'+f,f.toUpperCase()]);files.push(['paquete.zip','Paquete']);
    for(const [file,label] of files){const b=document.createElement('button');b.textContent=label;b.addEventListener('click',()=>download(record.artifact,record.version,file).catch(toast));buttons.append(b);}
    card.append(buttons);
    const edit=document.createElement('button');edit.textContent='Modificar este entregable';edit.addEventListener('click',()=>{$('message').value='Modifica el entregable '+record.artifact+': ';$('message').dataset.artifact=record.artifact;$('message').focus();});card.append(edit);
    $('artifacts').append(card);
  }
}
async function poll(jid,conversation){
  let box=jobs.get(jid);
  if(!box){box=document.createElement('div');box.className='job';jobs.set(jid,box);$('jobs').prepend(box);}
  try{
    const job=await api('/api/jobs/'+jid);box.textContent=job.stage;
    if(job.status==='completed'){
      box.textContent=(demoMode?'Simulador sin inferencia. ':'')+'Versión '+job.result.version+' disponible para revisión. '+job.result.quality.elapsed_seconds+' s en esta ejecución.';
      if(conversation===cid){const data=await api('/api/conversations/'+cid);await artifacts(data.artifacts);$('memory').textContent=JSON.stringify(data.memory,null,2);}
    }else if(job.status==='failed'){box.textContent='No se generó: '+job.stage;}
    else setTimeout(()=>poll(jid,conversation),1800);
  }catch(e){box.textContent='No se pudo consultar el trabajo. '+e.message;}
}
$('new').addEventListener('click',()=>newConversation().catch(toast));
$('settings').addEventListener('click',()=>{const aside=document.querySelector('aside');const expanded=aside.classList.toggle('show-settings');$('settings').setAttribute('aria-expanded',String(expanded));});
$('connect').addEventListener('click',async()=>{try{token=$('token').value.trim();sessionStorage.setItem('gs-token',token);await newConversation();$('status').textContent='Conectado';}catch(e){toast(e);}});
$('theme').addEventListener('click',async()=>{try{if(!cid)await newConversation();theme={...theme,client:$('client').value,primary:$('primary').value,accent:$('accent').value};await api('/api/conversations/'+cid+'/theme',theme);$('status').textContent='Identidad aplicada';}catch(e){toast(e);}});
async function fileData(file){
  if(file.size>12*1024*1024)throw new Error('Archivo de máximo 12 MB');
  return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
}
$('attachment').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;if(!cid)await newConversation();$('attachment-status').textContent='Incorporando…';const data=await api('/api/conversations/'+cid+'/attachments',{filename:file.name,data_base64:await fileData(file),scope:'conversation'});$('attachment-status').textContent=data.title+' · '+data.chunks+' fragmentos';}catch(e){toast(e);$('attachment-status').textContent='No incorporado';}finally{e.target.value='';}});
$('logo').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;if(!cid)await newConversation();const data=await api('/api/conversations/'+cid+'/logo',{data_base64:await fileData(file)});theme={...theme,logo_id:data.logo_id,primary:data.suggested_primary,accent:data.suggested_accent};$('primary').value=theme.primary;$('accent').value=theme.accent;await api('/api/conversations/'+cid+'/theme',theme);$('status').textContent='Logo y paleta aplicados';}catch(e){toast(e);}finally{e.target.value='';}});
$('chat').addEventListener('submit',async e=>{
  e.preventDefault();if(isBusy)return;
  const text=$('message').value.trim();if(!text)return;
  try{
    if(!cid)await newConversation();isBusy=true;$('send').disabled=true;$('status').textContent='Interpretando petición';
    const current=cid;const artifact=$('message').dataset.artifact||null;delete $('message').dataset.artifact;
    message('user',text);$('message').value='';
    const s=sessions.find(x=>x.id===cid);if(s&&s.title==='Nueva conversación'){s.title=text.slice(0,42);sessionList();}
    const result=await api('/api/conversations/'+current+'/messages',{message:text,artifact_id:artifact});
    if(current===cid)message('assistant',result.text,result.sources||[]);
    if(result.job_id)poll(result.job_id,current);
    $('status').textContent='Disponible';
  }catch(e){toast(e);$('status').textContent='Revisa la solicitud';}finally{isBusy=false;$('send').disabled=false;}
});
$('messages').addEventListener('click',event=>{const b=event.target.closest('[data-prompt]');if(b){$('message').value=b.dataset.prompt;$('message').focus();}});
async function init(){
  const health=await api('/health');demoMode=health.mode==='demo';$('mode').textContent=demoMode?'Simulador local':'Azure configurado';$('demo').hidden=!demoMode;
  if(health.mode==='demo'){const result=await api('/api/demo-session',{});token=result.token;sessionStorage.setItem('gs-token',token);}
  if(token){try{if(sessions.length)await load(sessions[0].id);else await newConversation();$('status').textContent='Disponible';}catch(e){sessions=[];await newConversation();}}
  else $('status').textContent='Introduce tu token de acceso';
}
init().catch(toast);
