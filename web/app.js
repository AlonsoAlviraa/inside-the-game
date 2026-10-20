"use strict";
const DELAY=200; // match-seconds of broadcast delay so the AI room is ready when a moment is shown
const TYPEICON={goal:"⚽",chance:"🎯",shot:"🎯",card:"🟨",stat:"📊",phase:"🔄",tactical:"🧠",period:"⏱",substitution:"🔁",pass:"⚡",player:"⭐"};
const $=id=>document.getElementById(id),cv=$("pitch"),cx=cv.getContext("2d");
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const viewer=localStorage.itgViewer||(localStorage.itgViewer="v"+Math.random().toString(36).slice(2,8));
const opt={mode:"fan",lang:"en",speed:"20"};
const AG=[["ingest","📥","Ingest","validates & de-duplicates"],["interpret","🧠","Interpret","xG, xT, control via MCP"],["explain","✍️","Explain","writes grounded lines"],["render","🎨","Render","builds overlay cards"],["personalise","🎯","Personalise","persona & language"]];
const ICON={goal:"⚽",big_chance:"🎯",yellow_card:"🟨",red_card:"🟥",second_yellow_card:"🟥",threat_pass:"⚡"};
const SUGG={en:["Who deserved to win on chances?","Who scored?","Best player so far?","Shots comparison","Any cards?"],
 es:["¿Quién mereció ganar por ocasiones?","¿Quién marcó?","¿Mejor jugador?","Comparativa de tiros","¿Tarjetas?"],
 fr:["Qui méritait de gagner aux occasions ?","Qui a marqué ?","Meilleur joueur ?","Comparaison des tirs","Des cartons ?"]};
const L={en:{goal:"GOAL!",scores:"scores for",save:"saved",blocked:"blocked",off_target:"off target",shot:"shoots",big:"Big chance",yellow:"Yellow card",red:"Red card",sub:"Substitution",on:"on",off:"off",ko:"Kick-off",ht:"Half-time",ft:"Full-time",second:"Second half under way"},
 es:{goal:"¡GOL!",scores:"marca para",save:"parada",blocked:"bloqueado",off_target:"fuera",shot:"dispara",big:"Ocasión clara",yellow:"Tarjeta amarilla",red:"Tarjeta roja",sub:"Cambio",on:"entra",off:"sale",ko:"Comienza el partido",ht:"Descanso",ft:"Final",second:"Arranca la segunda parte"},
 fr:{goal:"BUT !",scores:"marque pour",save:"arrêté",blocked:"contré",off_target:"non cadré",shot:"frappe",big:"Grosse occasion",yellow:"Carton jaune",red:"Carton rouge",sub:"Changement",on:"entre",off:"sort",ko:"Coup d'envoi",ht:"Mi-temps",ft:"Fin du match",second:"Début de la seconde période"}};
// ------------------------------------------------------------------ state
let es=null,meta=null,seed=7,fixtures=[],clubs={},S;
function fresh(){return{buf:[],T:0,lastRecv:0,applied:new Map(),score:{},clockMin:0,period:1,elapsed:0,paused:false,hold:0,running:false,ended:false,
 trail:[],shots:[],marks:[],items:new Map(),pending:new Map(),pendMin:[],poss:null,ballX:52.5,ballY:34,fx:52.5,fy:34,tx:52.5,ty:34,t0:0,dur:1,
 recentPress:[],control:null,cards:0,llm:0,rejected:0,batches:0,lat:0,usage:null,lastRep:-9,wp:null,report:null};}
S=fresh();
// ------------------------------------------------------------------ controls & views
document.querySelectorAll(".seg[id]").forEach(s=>s.onclick=e=>{const b=e.target.closest("button");if(!b||!(s.id in opt))return;
 s.querySelectorAll("button").forEach(x=>x.classList.toggle("on",x===b));opt[s.id]=b.dataset.v;if(s.id==="lang")sugg();});
document.querySelectorAll(".views button").forEach(b=>b.onclick=()=>{document.querySelectorAll(".views button").forEach(x=>x.classList.toggle("on",x===b));
 document.querySelectorAll(".view").forEach(v=>v.classList.toggle("on",v.id==="v-"+b.dataset.v));if(b.dataset.v==="league")loadLeague();});
document.querySelectorAll("#tabs button").forEach(b=>b.onclick=()=>tab(b.dataset.p));
function tab(p){document.querySelectorAll("#tabs button").forEach(x=>x.classList.toggle("on",x.dataset.p===p));document.querySelectorAll(".pane").forEach(x=>x.classList.toggle("on",x.id==="p-"+p));
 if(p==="tactics")loadTactics();if(p==="compare")loadCompare();if(p==="win")drawWin();if(p==="mom"&&S.report)drawMomentum(S.report);}
const tog=(id,cls,fn)=>{$(id).onclick=()=>{const on=!$(id).classList.contains("on");$(id).classList.toggle("on",on);fn&&fn(on);};};
tog("big",0,on=>{document.body.classList.toggle("large",on);document.body.classList.toggle("contrast",on);});
tog("snd");tog("tts",0,on=>{if(!on)speechSynthesis?.cancel();});
tog("ntf",0,on=>{if(on&&"Notification" in window&&Notification.permission==="default")Notification.requestPermission();});
const isOn=id=>$(id).classList.contains("on");
function say(t){if(!isOn("tts")||!("speechSynthesis" in window))return;const u=new SpeechSynthesisUtterance(t);u.lang={en:"en-GB",es:"es-ES",fr:"fr-FR"}[opt.lang];speechSynthesis.speak(u);}
function toast(t){const d=document.createElement("div");d.textContent=t;$("toast").appendChild(d);setTimeout(()=>d.remove(),5000);
 if(isOn("ntf")&&document.hidden&&"Notification" in window&&Notification.permission==="granted")new Notification("Inside the Game",{body:t});}
function cheer(){if(!isOn("snd"))return;try{const a=new AudioContext(),n=a.createBufferSource(),b=a.createBuffer(1,a.sampleRate*2.2,a.sampleRate),d=b.getChannelData(0);
 for(let i=0;i<d.length;i++)d[i]=(Math.random()*2-1)*Math.sin(Math.PI*i/d.length)*.35;n.buffer=b;const f=a.createBiquadFilter();f.type="bandpass";f.frequency.value=900;
 n.connect(f).connect(a.destination);n.start();const o=a.createOscillator(),g=a.createGain();o.frequency.value=880;g.gain.value=.08;o.connect(g).connect(a.destination);o.start();o.stop(a.currentTime+.25);}catch(e){}}
// ------------------------------------------------------------------ helpers
const H=()=>meta.home,A=()=>meta.away,tm=id=>meta&&(id===meta.home.id?meta.home:meta.away),col=id=>tm(id)?.color||"#fff";
function P(team,x,y){return(!meta||team===meta.home.id)?[x*10,y*10]:[(105-x)*10,(68-y)*10];}
function tlPos(period,minute){return period===1?Math.min(minute,48)/48*49:51+(Math.min(Math.max(minute,45),95)-45)/50*49;}
const elapsedMin=(p,m)=>p===1?Math.min(m,45):Math.min(m,90);
function crest(id){return `/api/crest/${id}.svg`;}
// ------------------------------------------------------------------ pitch drawing
function drawPitch(c){for(let i=0;i<10;i++){c.fillStyle=i%2?"#13692f":"#0f5f2b";c.fillRect(i*105,0,105,680);}
 c.strokeStyle="#ffffffc0";c.lineWidth=3;c.strokeRect(5,5,1040,670);c.beginPath();c.moveTo(525,5);c.lineTo(525,675);c.stroke();c.beginPath();c.arc(525,340,91,0,7);c.stroke();
 c.strokeRect(5,138,165,404);c.strokeRect(880,138,165,404);c.strokeRect(5,248,55,184);c.strokeRect(990,248,55,184);
 c.fillStyle="#fff";[[110,340],[940,340],[525,340]].forEach(([x,y])=>{c.beginPath();c.arc(x,y,4,0,7);c.fill();});
 c.beginPath();c.arc(110,340,91,-.93,.93);c.stroke();c.beginPath();c.arc(940,340,91,Math.PI-.93,Math.PI+.93);c.stroke();
 c.fillStyle="#ffffff40";c.fillRect(0,300,5,80);c.fillRect(1045,300,5,80);}
function star(c,x,y,r){c.beginPath();for(let i=0;i<10;i++){const a=i*Math.PI/5-Math.PI/2,rr=i%2?r/2.3:r;c.lineTo(x+rr*Math.cos(a),y+rr*Math.sin(a));}c.closePath();c.fill();c.stroke();}
let confetti=[];
function frame(now){const dt=frame.last?Math.min(100,now-frame.last):16;frame.last=now;tick(dt,now);
 drawPitch(cx);
 S.trail.forEach((p,i)=>{cx.globalAlpha=.25+.65*(i+1)/S.trail.length;cx.strokeStyle=p.c;cx.lineWidth=4;cx.setLineDash(p.ok?[]:[10,10]);cx.beginPath();cx.moveTo(...p.a);cx.lineTo(...p.b);cx.stroke();});
 cx.setLineDash([]);cx.globalAlpha=1;
 S.shots.forEach(s=>{const[x,y]=P(s.team,s.x,s.y),age=(S.T-s.t)/600;cx.globalAlpha=Math.max(.25,1-age);cx.lineWidth=4;cx.strokeStyle=col(s.team);cx.fillStyle=col(s.team);
  if(s.goal){cx.strokeStyle="#fff";star(cx,x,y,22);}else{cx.beginPath();cx.arc(x,y,9+60*s.xg,0,7);cx.stroke();}});cx.globalAlpha=1;
 S.marks=S.marks.filter(m=>m.until>now);S.marks.forEach(m=>{const[x,y]=P(m.team,m.x,m.y),r=26+8*Math.sin(now/150);cx.strokeStyle="#ffc83d";cx.lineWidth=6;cx.beginPath();cx.arc(x,y,r,0,7);cx.stroke();
  if(m.ex!=null){const b=P(m.team,m.ex,m.ey);cx.beginPath();cx.moveTo(x,y);cx.lineTo(...b);cx.stroke();}
  cx.fillStyle="#000c";const w=cx.measureText(m.label).width;cx.font="700 26px system-ui";const tw=cx.measureText(m.label).width;const lx=Math.min(Math.max(x-tw/2,12),1038-tw-16),ly=y>120?y-48:y+70;
  cx.fillRect(lx-8,ly-28,tw+16,38);cx.fillStyle="#ffc83d";cx.fillText(m.label,lx,ly);});
 const k=Math.min(1,(now-S.t0)/S.dur),e=1-Math.pow(1-k,3);S.ballX=S.fx+(S.tx-S.fx)*e;S.ballY=S.fy+(S.ty-S.fy)*e;
 const bx=S.ballX*10,by=S.ballY*10,g=cx.createRadialGradient(bx,by,0,bx,by,30);g.addColorStop(0,"#ffffffb0");g.addColorStop(1,"#fff0");cx.fillStyle=g;cx.beginPath();cx.arc(bx,by,30,0,7);cx.fill();
 cx.fillStyle="#fff";cx.strokeStyle=S.poss?col(S.poss):"#000";cx.lineWidth=4;cx.beginPath();cx.arc(bx,by,11,0,7);cx.fill();cx.stroke();
 S.dots&&S.dots.forEach(d=>{const on=d.id===S.carrier,[x,y]=on?[S.ballX*10+16,S.ballY*10-16]:P(d.team,d.x,d.y);cx.globalAlpha=on?1:.55;cx.fillStyle=col(d.team);cx.strokeStyle=on?"#fff":"#0008";cx.lineWidth=on?4:2;
  cx.beginPath();cx.arc(x,y,on?17:13,0,7);cx.fill();cx.stroke();cx.fillStyle="#fff";cx.font=`700 ${on?17:13}px system-ui`;cx.textAlign="center";cx.fillText(d.n,x,y+5);cx.textAlign="start";});cx.globalAlpha=1;
 arrows();
 if(S.action&&S.action.until>now){cx.font="700 22px system-ui";const t=S.action.text,w=cx.measureText(t).width,lx=Math.min(Math.max(bx-w/2,10),1040-w-12),ly=by>90?by-34:by+52;
  cx.fillStyle="#0a0e16e6";cx.beginPath();cx.roundRect(lx-8,ly-22,w+16,32,8);cx.fill();cx.fillStyle=S.action.c||"#fff";cx.fillText(t,lx,ly);}
 confetti=confetti.filter(p=>p.life>0);confetti.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.vy+=.25;p.life--;cx.fillStyle=p.c;cx.fillRect(p.x,p.y,8,12);});
 requestAnimationFrame(frame);}
function arrows(){if(!meta)return;cx.font="700 16px system-ui";cx.globalAlpha=.8;cx.fillStyle=meta.home.color;cx.fillText(meta.home.short+" →",16,28);
 cx.fillStyle=meta.away.color;const t="← "+meta.away.short;cx.fillText(t,1034-cx.measureText(t).width,28);cx.globalAlpha=1;}
function act(text,c,ms){S.action={text,c,until:performance.now()+(ms||1600)};}
const NUMS={};const num=id=>NUMS[id]??"";
function moveBall(team,x,y,ms){const[px,py]=P(team,x,y);S.fx=S.ballX;S.fy=S.ballY;S.tx=px/10;S.ty=py/10;S.t0=performance.now();S.dur=Math.max(80,ms);}
function centre(){S.fx=S.tx=S.ballX=52.5;S.fy=S.ty=S.ballY=34;}
// ------------------------------------------------------------------ playback clock (single source of truth)
function tick(dt,now){if(!S.running||S.paused)return;if(S.hold>now)return;
 if(S.buf.length&&S.buf[0].type==="period_start"&&S.T<S.buf[0].t)S.T=S.buf[0].t; // skip the interval
 const target=S.T+dt/1000*(+opt.speed);
 // never run ahead of what the server has sent
 S.T=Math.min(target,S.ended?S.lastRecv:S.lastRecv-DELAY);if(S.T>0)$("buffer").classList.remove("on");
 while(S.buf.length&&S.buf[0].t<=S.T){apply(S.buf.shift());if(S.hold>now)break;}
 if(S.ended&&!S.buf.length){S.running=false;finish();}}
function apply(ev){S.applied.set(ev.id,ev);S.clockMin=ev.minute;S.period=ev.period;S.elapsed=elapsedMin(ev.period,ev.minute);
 $("clock").textContent=ev.minute+"'";const pos=tlPos(ev.period,ev.minute);$("prog").style.width=pos+"%";$("head").style.left=pos+"%";
 const T=L[opt.lang],ms=ev.duration_s?ev.duration_s*1000/(+opt.speed):300;
 switch(ev.type){
 case "match_start":centre();$("period").textContent="1st half";caption(ev,"⏱ "+T.ko,`${H().name} v ${A().name}`,2);break;
 case "period_start":centre();$("period").textContent="2nd half";caption(ev,"⏱ "+T.second,"",2);break;
 case "period_end":centre();$("period").textContent=ev.period===1?"Half-time":"Full-time";caption(ev,"⏱ "+(ev.period===1?T.ht:T.ft),scoreline(ev.score),3);if(ev.period===1)S.hold=performance.now()+2500;refresh(true);break;
 case "possession_start":S.poss=ev.team;break;
 case "pass":S.poss=ev.team;S.carrier=ev.receiver_id||ev.player_id;act(ev.success?`Pass → #${num(ev.receiver_id)} ${(ev.receiver||"").split(" ")[1]||""}`:`Pass lost`,ev.success?"#fff":"#f07489",Math.min(1800,ms+700));moveBall(ev.team,ev.end_x,ev.end_y,Math.min(ms,1500));S.trail.push({a:P(ev.team,ev.x,ev.y),b:P(ev.team,ev.end_x,ev.end_y),c:col(ev.team),ok:ev.success});if(S.trail.length>8)S.trail.shift();
  S.lastZone=ev.team===S.poss?ev.end_x:null;break;
 case "turnover":S.poss=ev.team;act(`${tm(ev.team).short} win it back`,col(ev.team));break;
 case "pressure":S.recentPress.push({team:ev.team,t:ev.t});break;
 case "shot":{S.carrier=ev.player_id;act(ev.outcome==="goal"?"GOAL!":`Shot! ${ev.outcome==="saved"?"Saved":ev.outcome==="blocked"?"Blocked":"Wide"}`,ev.outcome==="goal"?"#f5c542":"#fff",2200);moveBall(ev.team,104,34+(ev.y-34)*.15,250);S.shots.push({team:ev.team,x:ev.x,y:ev.y,xg:ev.xg,t:ev.t,goal:ev.outcome==="goal"});
  if(ev.outcome!=="goal"&&(ev.xg>=.12||ev.outcome==="saved")){const big=ev.xg>=.2;tlMark(ev,big?"🎯":"•",`${ev.player} ${T[ev.outcome==="saved"?"save":ev.outcome]}`);
   caption(ev,`${big?"🎯 "+T.big:"🥅"} · ${ev.player}`,`${ev.player} (${tm(ev.team).short}) ${T.shot} — ${T[ev.outcome==="saved"?"save":ev.outcome]}`+(opt.mode!=="fan"?` (xG ${ev.xg})`:""),big?4:3);}break;}
 case "goal":goal(ev);break;
 case "card":{act(ev.card==="yellow"?`Yellow card #${num(ev.player_id)}`:`Red card #${num(ev.player_id)}`,ev.card==="yellow"?"#f5c542":"#ef4560",2500);const red=ev.card!=="yellow";tlMark(ev,red?"🟥":"🟨",ev.player);caption(ev,`${red?"🟥 "+T.red:"🟨 "+T.yellow}`,`${ev.player} (${tm(ev.team).short})`,red?4:3);if(red)toast(`🟥 ${ev.minute}' ${ev.player}`);break;}
 case "substitution":tlMark(ev,"🔁",ev.player_on);caption(ev,"🔁 "+T.sub,`${ev.player_on} ${T.on}, ${ev.player_off} ${T.off} (${tm(ev.team).short})`,2);break;
 case "match_end":$("period").textContent="Full-time";$("live").hidden=true;caption(ev,"⏱ "+T.ft,scoreline(ev.score),4);break;}
 // release LLM cards that were waiting for this moment
 const pend=S.pending.get("ev"+ev.id);if(pend){S.pending.delete("ev"+ev.id);upgrade(pend);}
 S.pendMin=S.pendMin.filter(c=>{if(elapsedMin(c.facts?.period||S.period,c.minute)<=S.elapsed&&(c.facts?.period||1)<=S.period){addCardItem(c);return false;}return true;});
 if(ev.type!=="pass"&&ev.type!=="pressure"||Math.random()<.08)nowLine(ev);
 if(S.elapsed-S.lastRep>=3)refresh();}
function scoreline(sc){return `${H().short} ${sc[H().id]??0} – ${sc[A().id]??0} ${A().short}`;}
function goal(ev){const T=L[opt.lang],t=tm(ev.team);S.score=ev.score;S.shots.forEach(s=>{if(Math.abs(s.t-ev.t)<1)s.goal=true;});
 $("score").textContent=`${ev.score[H().id]} – ${ev.score[A().id]}`;$("score").classList.remove("pop");void $("score").offsetWidth;$("score").classList.add("pop");
 tlMark(ev,"⚽",`${ev.player}`);const it=caption(ev,`⚽ ${T.goal} ${scoreline(ev.score)}`,`${ev.player} ${T.scores} ${t.name}! ${scoreline(ev.score)}`,5);S.items.set("ev"+(ev.id-1),it);
 $("gcrest").src=crest(t.id);$("gscorer").textContent=`${ev.player} · ${ev.minute}'`;$("gscore").textContent=scoreline(ev.score);
 $("goal").style.setProperty("--gc",t.color);$("goal").classList.add("on");S.hold=performance.now()+2500;setTimeout(()=>$("goal").classList.remove("on"),2500);
 const[gx,gy]=P(ev.team,103,34);for(let i=0;i<120;i++)confetti.push({x:gx,y:gy,vx:(Math.random()-.5)*16,vy:-Math.random()*14,life:90,c:i%2?t.color:"#ffc83d"});
 centre();cheer();say(`${T.goal} ${ev.player}. ${scoreline(ev.score)}`);toast(`⚽ ${ev.minute}' ${ev.player} — ${scoreline(ev.score)}`);refresh(true);}
function tlMark(ev,ic,title){const d=document.createElement("span");d.className="tl";d.textContent=ic;d.style.left=tlPos(ev.period,ev.minute)+"%";d.title=`${ev.minute}' ${title}`;d.dataset.ev=ev.id;
 d.onclick=()=>focusEvent(ev.id);$("timeline").appendChild(d);}
// ------------------------------------------------------------------ "what's happening now"
function nowLine(ev){if(!meta)return;const t=S.poss&&tm(S.poss);let s="";
 const recent=S.recentPress.filter(p=>S.T-p.t<90);S.recentPress=recent;const pr={};recent.forEach(p=>pr[p.team]=(pr[p.team]||0)+1);
 const presser=Object.keys(pr).sort((a,b)=>pr[b]-pr[a])[0];
 if(["goal"].includes(ev.type))s=`${ev.player} has just scored for ${tm(ev.team).name}. ${leadText()}`;
 else if(ev.type==="shot")s=`${ev.player} shoots for ${tm(ev.team).name} — ${ev.outcome.replace("_"," ")}.`;
 else if(ev.type==="period_end")s=ev.period===1?`Half-time. ${leadText()}`:`Full-time. ${leadText()}`;
 else if(ev.type==="card")s=`${ev.player} (${tm(ev.team).name}) is booked${ev.card!=="yellow"?" and sent off":""}.`;
 else if(t){const x=S.lastZone??50,zone=x>70?"in the attacking third":x>35?"in midfield":"building from the back";
  s=`${t.short} on the ball ${zone}`;if(presser&&pr[presser]>=3&&presser!==S.poss)s+=` · ${tm(presser).short} pressing high`;s+=` · ${leadText()}`;}
 if(s)$("nowt").textContent=s;}
function leadText(){const h=S.score[H().id]||0,a=S.score[A().id]||0;return h===a?`level ${h}–${a}`:`${(h>a?H():A()).short} lead ${Math.max(h,a)}–${Math.min(h,a)}`;}
// ------------------------------------------------------------------ commentary feed
function caption(ev,title,text,k){const m=/^(\S+)\s+(.*)$/.exec(title),ic=m&&!/[A-Za-z]/.test(m[1])?m[1]:"•",ti=m&&ic!=="•"?m[2]:title;
 const li=feedItem(ev.minute,ic,ti,text,k,false);li.dataset.ev=ev.id;li.onclick=e=>{if(e.target.closest("button"))return shareItem(li);focusEvent(ev.id);};
 $("feed").prepend(li);S.items.set("ev"+ev.id,li);if(k>=4&&ev.type!=="goal")say(text);S.cards++;return li;}
function feedItem(min,ic,ti,text,k,ai){$("feed").querySelector(".empty")?.remove();const li=document.createElement("li");li.className="k"+k;
 li.innerHTML=`<span class="mn">${min}'</span><span class="ic">${ic}</span><div><div class="ti"><span class="tt">${esc(ti)}</span><span class="ai" title="Written by the AI room and fact-checked">${ai?"✦":""}</span><button class="sv" title="Save as image">⬇</button></div><div class="tx">${esc(text)}</div></div>`;return li;}
function upgrade(c){const li=S.items.get(c.id);if(!li)return addCardItem(c);const tx=li.querySelector(".tx");tx.textContent=c.text;tx.classList.remove("up");void tx.offsetWidth;tx.classList.add("up");
 li.querySelector(".tt").textContent=c.title;const ai=String(c.source).includes("llm");if(ai){li.querySelector(".ai").textContent="✦";S.llm++;}}
function addCardItem(c){const llm=String(c.source).includes("llm");if(llm)S.llm++;S.cards++;
 const li=feedItem(c.minute,TYPEICON[c.type]||"•",c.title,c.text,Math.min(c.priority,4),llm);li.onclick=e=>{if(e.target.closest("button"))return shareItem(li);if(c.viz)showViz(c.viz,c.minute);};
 const feed=$("feed"),after=[...feed.children].find(x=>+(x.querySelector(".mn")?.textContent.replace("'",""))<=c.minute);feed.insertBefore(li,after||null);}
function onCards(d){S.batches++;d.cards.forEach(c=>{const m=/^ev(\d+)$/.exec(c.id);
  if(m){if(S.applied.has(+m[1])||S.items.has(c.id)){if(S.items.has(c.id))upgrade(c);else addCardItem(c);}else S.pending.set(c.id,c);}
  else if(elapsedMin(c.facts?.period||1,c.minute)<=S.elapsed&&(c.facts?.period||1)<=S.period)addCardItem(c);else S.pendMin.push(c);});
 d.trace.forEach(t=>{S.lat+=t.ms||0;if(Array.isArray(t.factcheck_rejected))S.rejected+=t.factcheck_rejected.length;});
 S.usage=d.usage;S.control=d.index;animatePipe(d.trace);traceLog(d);kpis();
 if(d.index?.control&&meta){const h=d.index.control[H().id],a=d.index.control[A().id],w=100*h/((h+a)||1);$("ctrl").style.width=w+"%";
  $("ctrlcap").textContent=Math.abs(w-50)<6?"Control: even":`Control: ${(w>50?H():A()).short} on top`;}}
function pitchCap(){}
function focusEvent(id){const ev=S.applied.get(+id);document.querySelectorAll("#feed li").forEach(x=>x.classList.toggle("sel",x.dataset.ev==id));
 document.querySelectorAll(`.tl[data-ev="${id}"]`).forEach(x=>{x.classList.remove("pulse");void x.offsetWidth;x.classList.add("pulse");});
 if(ev&&ev.x!=null){S.marks.push({team:ev.team,x:ev.x,y:ev.y,ex:ev.end_x,ey:ev.end_y,label:`${ev.minute}' ${ev.player||""}`.trim(),until:performance.now()+4500});}
 else if(ev&&ev.type==="goal"){const s=S.applied.get(ev.id-1);if(s)S.marks.push({team:s.team,x:s.x,y:s.y,label:`${ev.minute}' ⚽ ${ev.player}`,until:performance.now()+4500});}
 }
function showViz(v,minute){if(v&&v.x!=null)S.marks.push({team:v.team,x:v.x,y:v.y,ex:v.end_x,ey:v.end_y,label:`${minute}'`,until:performance.now()+4500});}
// ------------------------------------------------------------------ share images
function shareItem(li){const c=$("share"),g=c.getContext("2d"),h=H(),a=A();g.fillStyle="#0d1422";g.fillRect(0,0,1200,630);
 const gr=g.createLinearGradient(0,0,1200,0);gr.addColorStop(0,h.color);gr.addColorStop(1,a.color);g.fillStyle=gr;g.fillRect(0,0,1200,16);
 g.fillStyle="#9fb0c8";g.font="600 30px system-ui";g.fillText(`${h.name} v ${a.name} · ${li.querySelector(".mn").textContent}`,60,90);
 g.fillStyle="#fff";g.font="800 56px system-ui";wrap(g,li.querySelector(".tt").textContent,60,180,1080,64);g.font="500 40px system-ui";wrap(g,li.querySelector(".tx").textContent,60,300,1080,54);
 g.fillStyle="#00e0a4";g.font="700 26px system-ui";g.fillText("Inside the Game · synthetic match · fact-checked by a five-agent AI room",60,590);
 const l=document.createElement("a");l.download=`moment-${li.dataset.ev||"card"}.png`;l.href=c.toDataURL("image/png");l.click();}
function wrap(g,t,x,y,w,lh){let line="";t.split(" ").forEach(word=>{if(g.measureText(line+word).width>w){g.fillText(line,x,y);y+=lh;line="";}line+=word+" ";});g.fillText(line,x,y);}
// ------------------------------------------------------------------ AI room panel
function pipe(){$("pipe").innerHTML=AG.map(([k,i,n,d])=>`<div class="node" id="n-${k}"><div style="font-size:26px">${i}</div><div class="n">${n}</div><div class="d">${d}</div><div class="s" id="s-${k}">waiting</div></div>`).join("");}
function animatePipe(tr){let delay=0;AG.forEach(([k])=>{const t=tr.filter(x=>x.agent===k||(k==="interpret"&&x.agent==="salience"));if(!t.length)return;
 const ms=t.reduce((a,b)=>a+(b.ms||0),0),ti=t.reduce((a,b)=>a+(b.tokens_in||0),0),to=t.reduce((a,b)=>a+(b.tokens_out||0),0);
 setTimeout(()=>{$("n-"+k).classList.add("run");$("s-"+k).innerHTML=`${ms} ms<br>${ti?`${ti}→${to} tokens`:"rules (no LLM)"}`;setTimeout(()=>$("n-"+k)?.classList.remove("run"),450);},delay);delay+=280;});}
function traceLog(d){const r=d.report||{},div=document.createElement("div");div.textContent=`${d.minute}' · ${r.accepted??0}/${r.received??0} events · `+d.trace.map(t=>`${t.agent} ${t.ms}ms${t.tokens_in?` ${t.tokens_in}→${t.tokens_out}tok`:""}`).join(" | ");
 $("trace").prepend(div);while($("trace").children.length>40)$("trace").lastChild.remove();}
function kpis(){const u=S.usage||{calls:0,input_tokens:0,output_tokens:0,usd:0};const proj=S.elapsed?u.usd/S.elapsed*90:0;
 $("kpis").innerHTML=[[`$${(+u.usd).toFixed(4)}`,"LLM cost so far"],[`$${proj.toFixed(3)}`,"projected for the match"],[u.calls,"LLM calls"],[(u.input_tokens+u.output_tokens).toLocaleString(),"tokens used"],
 [S.cards,"commentary lines"],[S.llm,"upgraded by AI"],[S.rejected,"AI rewrites rejected by checks"],[S.batches?Math.round(S.lat/S.batches)+" ms":"–","AI room latency per batch"]].map(([b,s])=>`<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join("");}
// ------------------------------------------------------------------ data panels
function refresh(force){if(!meta)return;S.lastRep=S.elapsed;const m=S.running?Math.max(0,S.period===1?Math.min(S.clockMin,45):S.clockMin):200;
 fetch(`/api/formation?seed=${seed}&minute=${S.running?Math.max(m,10):200}`).then(r=>r.json()).then(f=>{S.dots=[];Object.entries(f.teams).forEach(([tid,t])=>t.players.forEach(p=>{const[x,y]=p.avg||p.slot;S.dots.push({id:p.id,team:tid,x,y,n:p.number});}));});
 fetch(`/api/report?seed=${seed}&minute=${m}`).then(r=>r.json()).then(r=>{S.report=r;renderStats(r);renderHL(r);drawMomentum(r);if($("p-compare").classList.contains("on"))loadCompare();});drawWin();}
function renderStats(r){const h=r.home,a=r.away,th=r.teams[h.id],ta=r.teams[a.id];
 const rows=[["Goals","goals"],["Shots","shots"],["Shots on target","on_target"],["Chance quality (xG)","xg"],["Threat from passes (xT)","xt"],["Passes","passes"],["Pass completion %","pass_completion_pct"],["Forward passes (10 m+)","progressive_passes"],["Pressures","pressures"],["Fouls","fouls"],["Yellow cards","yellow_cards"],["Red cards","red_cards"]];
 $("tstats").innerHTML=`<div class="sbar"><div class="l"><b style="color:${h.color}">${esc(h.name)}</b><span>${r.finished?"Full-time":"up to "+r.minute+"'"}</span><b style="color:${a.color}">${esc(a.name)}</b></div></div>`+rows.map(([l,k])=>{const x=+th[k],y=+ta[k],s=Math.abs(x)+Math.abs(y)||1;
  return `<div class="sbar"><div class="l"><b>${x}</b><span>${l}</span><b>${y}</b></div><div class="t"><div style="width:${100*Math.abs(x)/s}%;background:${h.color}"></div><div style="width:${100*Math.abs(y)/s}%;background:${a.color}"></div></div></div>`;}).join("");
 $("pstats").innerHTML=`<table><tr><th>Player</th><th>Team</th><th>Impact</th><th>Goals</th><th>xG</th><th>xT</th><th>Pass %</th></tr>`+r.players.slice(0,12).map(p=>{const t=p.team===h.id?h:a;
  return `<tr><td>${esc(p.name)}</td><td><span style="color:${t.color}">●</span> ${esc(t.short)}</td><td><b>${p.impact}</b></td><td>${p.goals}</td><td>${p.xg}</td><td>${p.xt}</td><td>${p.pass_completion_pct}</td></tr>`;}).join("")+"</table>";}
function renderHL(r){const km=r.key_moments;if(!km.length){$("hls").className="empty";$("hls").textContent="No highlights yet.";return;}$("hls").className="";
 $("hls").innerHTML=km.slice().reverse().map((m,i)=>`<div class="hl" data-i="${km.length-1-i}"><span class="ic">${ICON[m.kind]||"•"}</span><div>${esc(m.label)}</div><span class="mm">${m.minute}'</span></div>`).join("");
 $("hls").querySelectorAll(".hl").forEach(el=>el.onclick=()=>{const m=km[+el.dataset.i];if(m.x!=null)S.marks.push({team:m.team,x:m.x,y:m.y,ex:m.end_x,ey:m.end_y,label:`${m.minute}' ${m.player}`,until:performance.now()+5000});
  else focusEvent(m.event_id);$("pitchbox").scrollIntoView({behavior:"smooth",block:"center"});});}
function drawMomentum(r){const c=$("mom"),g=c.getContext("2d"),W=c.width,Hh=c.height,mid=Hh/2,ms=r.momentum,h=r.home,a=r.away;g.clearRect(0,0,W,Hh);
 const mx=Math.max(.05,...ms.map(m=>Math.max(m[h.id],m[a.id]))),bw=(W-80)/21;g.strokeStyle="#ffffff40";g.beginPath();g.moveTo(60,mid);g.lineTo(W,mid);g.stroke();
 g.font="700 20px system-ui";g.fillStyle=h.color;g.fillText(h.short,4,30);g.fillStyle=a.color;g.fillText(a.short,4,Hh-10);
 ms.forEach((m,i)=>{const x=60+i*bw,u=(mid-26)*m[h.id]/mx,d=(mid-26)*m[a.id]/mx;g.fillStyle=h.color;g.fillRect(x,mid-u,bw-6,u);g.fillStyle=a.color;g.fillRect(x,mid,bw-6,d);
  if(i%3===0){g.fillStyle="#9fb0c8";g.font="16px system-ui";g.fillText(m.from_minute+"'",x,mid+(d>0?-6:-6)-u);}});
 r.key_moments.filter(k=>k.kind==="goal").forEach(k=>{const i=Math.max(0,ms.findIndex((m,j)=>j===ms.length-1||ms[j+1].from_minute>k.minute));g.font="24px system-ui";g.fillText("⚽",60+i*bw,k.team===h.id?24:Hh-4);});
 const last=ms.slice(-2),sh=last.reduce((s,m)=>s+m[h.id],0),sa=last.reduce((s,m)=>s+m[a.id],0);
 $("momcap").textContent=!last.length?"—":sh+sa<.03?"Quiet spell: neither side is creating much danger.":sh>sa*1.6?`${h.name} on top: they are creating most of the danger right now.`:sa>sh*1.6?`${a.name} on top: they are creating most of the danger right now.`:"End-to-end: both sides are creating danger.";}
async function drawWin(){if(!meta)return;if(!S.wp||S.wp.seed!==seed)S.wp={seed,series:(await fetch(`/api/winprob?seed=${seed}`).then(r=>r.json())).series};
 const ser=S.wp.series,upto=S.running?S.elapsed:(S.ended?999:0),pts=ser.filter(p=>p.final?upto>=999||(!S.running&&S.ended):p.minute<=upto);const cur=pts[pts.length-1]||ser[0];
 const h=H(),a=A();$("wpmini").innerHTML=`<div style="width:${cur.home*100}%;background:${h.color}"></div><div style="width:${cur.draw*100}%;background:#5b6577"></div><div style="width:${cur.away*100}%;background:${a.color}"></div>`;$("wpl").textContent=`Win ${h.short} ${Math.round(cur.home*100)}% · D ${Math.round(cur.draw*100)}% · ${a.short} ${Math.round(cur.away*100)}%`;$("probbar").innerHTML=[[h.short+" win",cur.home,h.color],["Draw",cur.draw,"#4b5568"],[a.short+" win",cur.away,a.color]].map(([l,p,c])=>`<div style="width:${p*100}%;background:${c}">${p>.08?`${l} ${Math.round(p*100)}%`:""}</div>`).join("");
 const c=$("wpc"),g=c.getContext("2d"),W=c.width,Hh=c.height;g.clearRect(0,0,W,Hh);g.strokeStyle="#ffffff25";g.font="16px system-ui";g.fillStyle="#9fb0c8";
 [0,.5,1].forEach(v=>{const y=Hh-20-(Hh-40)*v;g.beginPath();g.moveTo(50,y);g.lineTo(W,y);g.stroke();g.fillText(Math.round(v*100)+"%",4,y+5);});
 [0,15,30,45,60,75,90].forEach(m=>g.fillText(m+"'",50+(W-60)*m/91,Hh-2));
 [["home",h.color],["draw","#9fb0c8"],["away",a.color]].forEach(([k,cl])=>{g.strokeStyle=cl;g.lineWidth=4;g.beginPath();pts.filter(p=>!p.final).forEach((p,i)=>{const x=50+(W-60)*p.minute/91,y=Hh-20-(Hh-40)*p[k];i?g.lineTo(x,y):g.moveTo(x,y);});g.stroke();});}
async function loadPreview(){const p=await fetch(`/api/preview?seed=${seed}`).then(r=>r.json());const h=H(),a=A(),pr=p.pre_match_probability,rec=p.head_to_head_record;
 const form=t=>t?.table?`<span class="form">${t.table.form.map(f=>`<b class="${f}">${f}</b>`).join("")||"—"}</span>`:"—";
 const pos=t=>t?.table&&t.table.played?`${t.table.position}${["th","st","nd","rd"][t.table.position%10>3||[11,12,13].includes(t.table.position)?0:t.table.position%10]} · ${t.table.points} pts`:"Season opener";
 $("hr").textContent=p.home.table&&p.home.table.played?pos(p.home):"";$("ar").textContent=p.away.table&&p.away.table.played?pos(p.away):"";
 $("prev").innerHTML=`<div class="g3"><div><h3>Pre-match odds</h3><p class="cap">From team ratings (${p.home.rating} v ${p.away.rating}) with a small home advantage.</p><div class="probbar">${[[h.short,pr.home,h.color],["Draw",pr.draw,"#4b5568"],[a.short,pr.away,a.color]].map(([l,v,c])=>`<div style="width:${v*100}%;background:${c}">${l} ${Math.round(v*100)}%</div>`).join("")}</div></div>
 <div><h3>League position & form</h3><p class="cap">${p.matchday?`Before matchday ${p.matchday}`:"After 6 matchdays (showcase friendly)"}</p><table><tr><td style="color:${h.color}">${esc(h.name)}</td><td>${pos(p.home)}</td><td>${form(p.home)}</td></tr><tr><td style="color:${a.color}">${esc(a.name)}</td><td>${pos(p.away)}</td><td>${form(p.away)}</td></tr></table></div>
 <div><h3>Head-to-head (synthetic archive)</h3><p class="cap">${h.short} ${rec.home_wins} wins · ${rec.draws} draws · ${a.short} ${rec.away_wins} wins</p>${p.head_to_head.map(m=>`<div>${esc(tm(m.home).short)} ${m.score[m.home]} – ${m.score[m.away]} ${esc(tm(m.away).short)} <span class="muted">${esc(m.label)}</span></div>`).join("")}</div></div>
 <div class="g2" style="margin-top:18px">${[h,a].map(t=>`<div><h3 style="color:${t.color}">${esc(t.name)} · 4-3-3</h3><table>${p.lineups[t.id].map(pl=>`<tr><td>${pl.number}</td><td>${esc(pl.name)}</td><td>${pl.position}</td></tr>`).join("")}</table></div>`).join("")}</div>`;}
let tacTeam=null;async function loadTactics(){if(!meta)return;tacTeam=tacTeam&&tm(tacTeam)?.id===tacTeam?tacTeam:H().id;
 $("tteam").innerHTML=[H(),A()].map(t=>`<button data-v="${t.id}" class="${t.id===tacTeam?"on":""}">${esc(t.name)}</button>`).join("");$("tteam").onclick=e=>{const b=e.target.closest("button");if(b){tacTeam=b.dataset.v;loadTactics();}};
 const f=await fetch(`/api/formation?seed=${seed}&minute=${S.running?S.clockMin:200}`).then(r=>r.json()),c=$("tac").getContext("2d"),t=tm(tacTeam);drawPitch(c);
 f.teams[tacTeam].players.forEach(p=>{const[sx,sy]=[p.slot[0]*10,p.slot[1]*10];c.strokeStyle="#ffffff90";c.lineWidth=3;c.setLineDash([6,6]);c.beginPath();c.arc(sx,sy,24,0,7);c.stroke();c.setLineDash([]);
  if(p.avg){const[ax,ay]=[p.avg[0]*10,p.avg[1]*10];c.strokeStyle="#ffffff60";c.beginPath();c.moveTo(sx,sy);c.lineTo(ax,ay);c.stroke();c.fillStyle=t.color;c.strokeStyle="#fff";c.beginPath();c.arc(ax,ay,22,0,7);c.fill();c.stroke();
   c.fillStyle="#fff";c.font="800 20px system-ui";c.textAlign="center";c.fillText(p.number,ax,ay+7);c.font="600 17px system-ui";c.fillText(p.name.split(" ")[1]||p.name,ax,ay+44);c.textAlign="start";}});}
async function loadCompare(){if(!meta)return;const pl=[...H().players.slice(0,11).map(p=>[p,H()]),...A().players.slice(0,11).map(p=>[p,A()])];
 if($("pa").options.length!==pl.length){[$("pa"),$("pb")].forEach((s,j)=>{s.innerHTML=pl.map(([p,t])=>`<option value="${p.id}">${esc(p.name)} (${t.short}, ${p.position})</option>`).join("");});$("pa").value=H().players[9].id;$("pb").value=A().players[9].id;$("pa").onchange=$("pb").onchange=loadCompare;}
 const r=await fetch(`/api/compare?seed=${seed}&a=${$("pa").value}&b=${$("pb").value}&minute=${S.running?S.clockMin:200}`).then(r=>r.json());const x=r.a||{},y=r.b||{};
 const rows=[["Impact (goals+xG+xT)","impact"],["Goals","goals"],["Shots","shots"],["Chance quality (xG)","xg"],["Threat from passes (xT)","xt"],["Passes","passes"],["Pass completion %","pass_completion_pct"],["Fouls","fouls"]];
 $("cmp").innerHTML=`<div class="sbar"><div class="l"><b>${esc($("pa").selectedOptions[0].text)}</b><b>${esc($("pb").selectedOptions[0].text)}</b></div></div>`+rows.map(([l,k])=>{const a=+(x[k]||0),b=+(y[k]||0),s=Math.abs(a)+Math.abs(b)||1;
  return `<div class="sbar"><div class="l"><b>${a}</b><span>${l}</span><b>${b}</b></div><div class="t"><div style="width:${100*Math.abs(a)/s}%;background:var(--acc)"></div><div style="width:${100*Math.abs(b)/s}%;background:var(--acc2)"></div></div></div>`;}).join("")+(!r.a&&!r.b?'<p class="cap">No actions yet for these players.</p>':"");}
// ------------------------------------------------------------------ ask the analyst
function sugg(){$("sugg").innerHTML=SUGG[opt.lang].map(s=>`<button type="button">${esc(s)}</button>`).join("");$("sugg").querySelectorAll("button").forEach(b=>b.onclick=()=>{$("q").value=b.textContent;ask();});}
async function ask(){const q=$("q").value.trim();if(!q)return;$("q").value="";const ch=$("chat");ch.insertAdjacentHTML("beforeend",`<div class="msg me">${esc(q)}</div>`);
 const m=document.createElement("div");m.className="msg";m.textContent="Checking the data…";ch.appendChild(m);ch.scrollTop=1e6;
 try{const minute=S.running?(S.period===1?Math.min(S.clockMin,45):S.clockMin):200;const r=await fetch("/api/ask",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({seed,question:q,minute,lang:opt.lang})}).then(r=>r.json());
  m.innerHTML=`${esc(r.text)}<small>${r.source==="llm"?'<span class="chip ok">AI answer ✓ passed checks</span>':'<span class="chip">rules answer'+(r.rejected?" · AI draft rejected":"")+"</span>"} · data up to ${minute>=200?"full-time":minute+"'"}</small>`;say(r.text);ch.scrollTop=1e6;}
 catch(e){m.textContent="The analyst desk is unavailable right now.";}}
$("askf").onsubmit=e=>{e.preventDefault();ask();};
// ------------------------------------------------------------------ league view
let league=null;async function loadLeague(){if(!league)league=await fetch("/api/league").then(r=>r.json());$("lgname").textContent=league.name;
 $("ltable").innerHTML="<tr><th>#</th><th>Club</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GD</th><th>Pts</th><th>Form</th></tr>"+league.table.map(r=>`<tr><td>${r.position}</td><td><img src="${r.crest}" alt="">${esc(r.name)}</td><td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td><td>${r.gd>0?"+":""}${r.gd}</td><td><b>${r.points}</b></td><td class="form">${r.form.map(f=>`<b class="${f}">${f}</b>`).join("")}</td></tr>`).join("");
 if(!$("md").options.length){$("md").innerHTML=[1,2,3,4,5,6].map(d=>`<option value="${d}">Matchday ${d}</option>`).join("")+'<option value="0">Showcase friendlies</option>';$("md").onchange=$("spoil").onchange=fx;}fx();}
function fx(){const d=+$("md").value,sp=$("spoil").checked;$("fixtures").innerHTML=league.fixtures.filter(f=>f.matchday===d).map(f=>`<div class="fx"><img src="/api/crest/${f.home_id}.svg" alt=""><span>${esc(f.home)}</span><span class="sc">${sp&&f.score?`${f.score[f.home_id]} – ${f.score[f.away_id]}`:"v"}</span><span>${esc(f.away)}</span><img src="/api/crest/${f.away_id}.svg" alt=""><button class="btn ghost" data-s="${f.seed}" style="padding:6px 12px">Watch</button></div>`).join("");
 $("fixtures").querySelectorAll("button").forEach(b=>b.onclick=()=>{$("match").value=b.dataset.s;$("match").onchange();document.querySelector('.views button[data-v="live"]').click();});}
// ------------------------------------------------------------------ match lifecycle
function setMeta(m){meta=m;[m.home,m.away].forEach(t=>t.players.forEach(p=>NUMS[p.id]=p.number));const h=m.home,a=m.away;$("hn").textContent=h.name;$("an").textContent=a.name;$("hc").src=crest(h.id);$("ac").src=crest(a.id);
 document.documentElement.style.setProperty("--home",h.color);document.documentElement.style.setProperty("--away",a.color);
 const cl=$("club");cl.length=1;loadPreview;[h,a].forEach(t=>cl.add(new Option(t.name,t.id)));}
function resetUI(){$("feed").innerHTML='<li class="empty">Commentary starts at kick-off.</li>';$("trace").innerHTML="";$("timeline").querySelectorAll(".tl").forEach(x=>x.remove());
 $("prog").style.width="0";$("head").style.left="0";$("score").textContent="0 – 0";$("clock").textContent="0'";$("period").textContent="Pre-match";$("live").hidden=true;pipe();kpis();}
async function loadMatch(){if(es)es.close();S=fresh();resetUI();const j=await fetch(`/api/match?seed=${seed}&meta_only=true`).then(r=>r.json());setMeta(j.events[0].meta);
 S.score={[meta.home.id]:0,[meta.away.id]:0};loadPreview();refresh();$("nowt").textContent=`${meta.home.name} v ${meta.away.name} at ${j.events[0].meta.venue}. Press Kick off to start.`;}
function kick(){if(es)es.close();const keep=meta;S=fresh();resetUI();S.score={[keep.home.id]:0,[keep.away.id]:0};S.running=true;$("live").hidden=false;$("go").textContent="↻ Restart";$("pause").disabled=false;$("pause").textContent="⏸ Pause";
 tab("feed");$("buffer").classList.add("on");const q=new URLSearchParams({seed,speed:+opt.speed*1.6,batch_s:150,mode:opt.mode,lang:opt.lang,club:$("club").value,viewer});
 es=new EventSource("/api/stream?"+q);
 es.addEventListener("tick",m=>{const ev=JSON.parse(m.data).event;S.buf.push(ev);S.lastRecv=ev.t;if(ev.type==="match_end")S.ended=true;});
 es.addEventListener("cards",m=>onCards(JSON.parse(m.data)));
 es.addEventListener("end",()=>{es.close();S.ended=true;});
 es.onerror=()=>{if(es.readyState===2)S.ended=true;};}
function finish(){$("live").hidden=true;$("pause").disabled=true;S.pending.forEach(c=>addCardItem(c));S.pendMin.forEach(addCardItem);S.pending.clear();S.pendMin=[];refresh(true);drawWin();fullTime();}
$("pause").onclick=()=>{S.paused=!S.paused;$("pause").textContent=S.paused?"▶ Resume":"⏸ Pause";};
$("go").onclick=kick;
$("match").onchange=()=>{seed=+$("match").value;S.wp=null;loadMatch();};
async function fullTime(){$("ftbody").innerHTML="<p>The agents are writing the full-time report…</p>";$("ft").classList.add("on");
 const r=await fetch(`/api/report?seed=${seed}&recap=true&lang=${opt.lang}`).then(r=>r.json()),h=r.home,a=r.away;
 $("dl").href=`/api/report?seed=${seed}&format=md&recap=true&lang=${opt.lang}`;
 $("ftbody").innerHTML=`<span class="chip">Full-time report · synthetic match</span><h2 style="font-size:2em;margin:12px 0">${esc(h.name)} ${r.score[h.id]} – ${r.score[a.id]} ${esc(a.name)}</h2>
 <p style="font-size:1.1em">${esc(r.recap.text)}</p><p><span class="chip ${r.recap.source==="llm"?"ok":""}">${r.recap.source==="llm"?"AI recap ✓ passed numbers, claims and player checks":"rules recap"}</span></p>
 <h3>Key moments</h3>${r.key_moments.filter(k=>k.importance>=4).map(k=>`<div class="hl"><span class="ic">${ICON[k.kind]||"•"}</span><div>${esc(k.label)}</div><span class="mm">${k.minute}'</span></div>`).join("")}`;}
fetch("/api/matches").then(r=>r.json()).then(j=>{fixtures=j.matches;const groups={};fixtures.forEach(f=>{const g=f.matchday?`Matchday ${f.matchday}`:"Showcase friendlies";(groups[g]=groups[g]||[]).push(f);});
 $("match").innerHTML=Object.entries(groups).map(([g,fs])=>`<optgroup label="${g}">${fs.map(f=>`<option value="${f.seed}">${esc(f.home)} v ${esc(f.away)}</option>`).join("")}</optgroup>`).join("");$("match").value="7";seed=7;loadMatch();});
pipe();kpis();sugg();requestAnimationFrame(frame);
