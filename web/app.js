"use strict";
const DELAY=200; // match-seconds of broadcast delay so the AI room is ready when a moment is shown
const TYPEICON={goal:"⚽",chance:"🎯",shot:"🎯",card:"🟨",stat:"📊",phase:"🔄",tactical:"🧠",period:"⏱",substitution:"🔁",pass:"⚡",player:"⭐"};
const $=id=>document.getElementById(id),cv=$("pitch"),cx=cv.getContext("2d");
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const viewer=localStorage.itgViewer||(localStorage.itgViewer="v"+Math.random().toString(36).slice(2,8));
const opt={mode:"fan",lang:"en",speed:"20",src:"replay"};
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
// ------------------------------------------------------------------ resilient fetch (retries cold starts / transient 5xx)
async function J(url,tries=4){let last;for(let i=0;i<tries;i++){try{const r=await fetch(url);if(r.ok)return await r.json();last=new Error(r.status+" "+url);if(r.status<500&&r.status!==429)break;}catch(e){last=e;}
 netState(true);await new Promise(z=>setTimeout(z,400*2**i));}netState(false,true);throw last;}
function netState(retrying,failed){const b=$("netbar");if(!b)return;b.hidden=!(retrying||failed);b.textContent=failed?"Connection problem: some panels could not load. They retry automatically; press Restart if needed.":"Reconnecting to the server…";if(!retrying&&!failed)b.hidden=true;}
window.addEventListener("unhandledrejection",e=>{console.warn("handled:",e.reason);e.preventDefault();});
window.addEventListener("error",e=>{console.warn("handled:",e.message);});
// ------------------------------------------------------------------ controls & views
document.querySelectorAll(".seg[id]").forEach(s=>s.onclick=e=>{const b=e.target.closest("button");if(!b||!(s.id in opt))return;
 s.querySelectorAll("button").forEach(x=>x.classList.toggle("on",x===b));opt[s.id]=b.dataset.v;if(s.id==="lang")sugg();});
document.querySelectorAll(".views button").forEach(b=>b.onclick=()=>{document.querySelectorAll(".views button").forEach(x=>x.classList.toggle("on",x===b));
 document.querySelectorAll(".view").forEach(v=>v.classList.toggle("on",v.id==="v-"+b.dataset.v));if(b.dataset.v==="league"&&!LG)loadLeague();});
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
function frame(now){const dt=frame.last?Math.min(100,now-frame.last):16;frame.last=now;if(R.on){reelFrame(dt,now);requestAnimationFrame(frame);return;}tick(dt,now);
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
 arrows();drawQ(now);
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
 else if(ev.type==="shot")s=`${ev.player} shoots for ${tm(ev.team).name} — ${ev.outcome.replace("_"," ")}${ev.speed_kmh?` (${Math.round(ev.speed_kmh)} km/h from ${Math.round(ev.distance_m)} m)`:""}.`;
 else if(ev.type==="period_end")s=ev.period===1?`Half-time. ${leadText()}`:`Full-time. ${leadText()}`;
 else if(ev.type==="card")s=`${ev.player} (${tm(ev.team).name}) is booked${ev.card!=="yellow"?" and sent off":""}.`;
 else if(t){const x=S.lastZone??50,zone=x>70?"in the attacking third":x>35?"in midfield":"building from the back";
  s=`${t.short} on the ball ${zone}`;if(presser&&pr[presser]>=3&&presser!==S.poss)s+=` · ${tm(presser).short} pressing high`;s+=` · ${leadText()}`;}
 if(s)$("nowt").textContent=s;}
function leadText(){const h=S.score[H().id]||0,a=S.score[A().id]||0;return h===a?`level ${h}–${a}`:`${(h>a?H():A()).short} lead ${Math.max(h,a)}–${Math.min(h,a)}`;}
// ------------------------------------------------------------------ commentary feed
function caption(ev,title,text,k){const m=/^(\S+)\s+(.*)$/.exec(title),ic=m&&!/[A-Za-z]/.test(m[1])?m[1]:"•",ti=m&&ic!=="•"?m[2]:title;
 const li=feedItem(ev.minute,ic,ti,text,k,false);li.dataset.ev=ev.id;li.onclick=e=>{if(e.target.closest("button"))return shareItem(li);focusEvent(ev.id);};
 $("feed").prepend(li);S.items.set("ev"+ev.id,li);if(k>=(isOn("tts")?2:4)&&ev.type!=="goal")say(`${ev.minute}th minute. ${text}`);if(k>=3)announce(`${ev.minute}'. ${text}`);S.cards++;return li;}
function feedItem(min,ic,ti,text,k,ai){$("feed").querySelector(".empty")?.remove();const li=document.createElement("li");li.className="k"+k;
 li.innerHTML=`<span class="mn">${min}'</span><span class="ic">${ic}</span><div><div class="ti"><span class="tt">${esc(ti)}</span><span class="ai" title="Written by the AI room and fact-checked">${ai?"✦":""}</span><button class="sv" title="Save as image">⬇</button></div><div class="tx">${esc(text)}</div></div>`;return li;}
function upgrade(c){const li=S.items.get(c.id);if(!li)return addCardItem(c);if(c.fav)li.classList.add("fav");const tx=li.querySelector(".tx");tx.textContent=c.text;tx.classList.remove("up");void tx.offsetWidth;tx.classList.add("up");
 li.querySelector(".tt").textContent=c.title;const ai=String(c.source).includes("llm");if(ai){li.querySelector(".ai").textContent="✦";S.llm++;}}
function addCardItem(c){const llm=String(c.source).includes("llm");if(llm)S.llm++;S.cards++;
 const li=feedItem(c.minute,TYPEICON[c.type]||"•",c.title.replace(/^★ /,""),c.text,Math.min(c.priority,4),llm);if(c.fav)li.classList.add("fav");li.onclick=e=>{if(e.target.closest("button"))return shareItem(li);if(c.viz)showViz(c.viz,c.minute);};
 const feed=$("feed"),after=[...feed.children].find(x=>+(x.querySelector(".mn")?.textContent.replace("'",""))<=c.minute);feed.insertBefore(li,after||null);}
function onCards(d){S.batches++;if(d.replay)S.replay=true;d.cards.forEach(c=>{const m=/^ev(\d+)$/.exec(c.id);
  if(m){if(S.applied.has(+m[1])||S.items.has(c.id)){if(S.items.has(c.id))upgrade(c);else addCardItem(c);}else S.pending.set(c.id,c);}
  else if(elapsedMin(c.facts?.period||1,c.minute)<=S.elapsed&&(c.facts?.period||1)<=S.period)addCardItem(c);else S.pendMin.push(c);});
 d.trace.forEach(t=>{S.lat+=t.ms||0;if(Array.isArray(t.factcheck_rejected))S.rejected+=t.factcheck_rejected.length;});
 S.usage=d.usage;S.control=d.index;if(!(S.chaosPin&&performance.now()<S.chaosPin))animatePipe(d.trace);handoffs(d);traceLog(d);kpis();
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
const HAND=[["ingest","Ingest","events"],["interpret","Interpret","insights"],["salience","Salience","candidates"],["explain","Explain","explained"],["render","Render","cards"],["personalise","Personalise","cards"]];
function handoffs(d){const el=$("handoff");if(!el)return;if(d.chaos)S.chaosPin=performance.now()+20000;else if(S.chaosPin&&performance.now()<S.chaosPin)return;const by={};(d.trace||[]).forEach(t=>by[t.agent]=t);
 const cell=([k,n,what])=>{const t=by[k];if(!t)return`<div class="ho idle"><b>${n}</b><span>—</span></div>`;const o=t.out?t.out[what]:null;
  const st=t.recovery?(t.recovery==="skipped"?"dead":"fault"):"ok";return`<div class="ho ${st}" title="${esc(t.fault||"")}"><b>${n}</b><span>${o==null?`${t.ms} ms`:`${o} ${what}`}</span>${t.recovery?`<i>💥 → ${t.recovery} (${t.attempts}×)</i>`:""}</div>`;};
 el.innerHTML=`<div class="hrow">${cell(HAND[0])}<em>→</em><div class="par">${cell(HAND[1])}${cell(HAND[2])}</div><em>→</em>${cell(HAND[3])}<em>→</em>${cell(HAND[4])}<em>→</em>${cell(HAND[5])}</div>
 <p class="cap">${d.chaos?`💥 Fault injected in <b>${esc(d.chaos)}</b> at ${d.minute}'. The orchestrator ${Object.values(by).some(t=>t.recovery==="skipped")?"skipped it and the batch still reached the viewer":"recovered and the batch still reached the viewer"}: ${(d.cards||[]).length} card(s) delivered.`:`Batch at ${d.minute}': what each agent handed to the next.`}</p>`;}
async function chaos(){const agent=$("chaosag").value,severity=$("chaossev").value,b=$("chaosbtn");b.disabled=true;
 try{const live=S.running&&!S.ended&&!S.replay&&opt.src==="live";const r=await fetch("/api/chaos",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({agent,severity,seed,minute:Math.max(5,Math.min(90,S.clockMin||30)),mode:opt.mode,lang:opt.lang,sid:live?S.sid:null})}).then(r=>r.json());
  if(r.live){$("chaosmsg").textContent=`Armed: ${agent} will fail on the next live batch. Watch the trace.`;}
  else{const d={trace:r.trace,minute:r.minute,report:(r.trace.find(t=>t.agent==="ingest")||{}).report||{},cards:r.cards,chaos:agent};animatePipe(r.trace);handoffs(d);traceLog(d);
   $("chaosmsg").textContent=`Sandbox room (rules mode, no model cost) replayed up to ${r.minute}' and broke ${agent} (${severity}).`;}}
 catch(e){$("chaosmsg").textContent="Chaos request failed: "+e;}finally{b.disabled=false;}}
function pipe(){$("pipe").innerHTML=AG.map(([k,i,n,d])=>`<div class="node" id="n-${k}"><div style="font-size:26px">${i}</div><div class="n">${n}</div><div class="d">${d}</div><div class="s" id="s-${k}">waiting</div></div>`).join("");}
function animatePipe(tr){let delay=0;AG.forEach(([k])=>{const t=tr.filter(x=>x.agent===k||(k==="interpret"&&x.agent==="salience"));if(!t.length)return;
 const ms=t.reduce((a,b)=>a+(b.ms||0),0),ti=t.reduce((a,b)=>a+(b.tokens_in||0),0),to=t.reduce((a,b)=>a+(b.tokens_out||0),0);
 const f=t.find(x=>x.recovery);setTimeout(()=>{const n=$("n-"+k);n.classList.remove("fault","dead");if(f)n.classList.add(f.recovery==="skipped"?"dead":"fault");n.classList.add("run");$("s-"+k).innerHTML=f?`💥 failed → ${f.recovery==="retry"?"retried ✓":f.recovery==="skipped"?"skipped":f.recovery==="restart"?"restarted ✓":"rules fallback ✓"}<br>${ms} ms`:`${ms} ms<br>${ti?`${ti}→${to} tokens`:"rules (no LLM)"}`;setTimeout(()=>$("n-"+k)?.classList.remove("run"),450);},delay);delay+=280;});}
function traceLog(d){const r=d.report||{},div=document.createElement("div");div.textContent=`${d.chaos?"💥 CHAOS · ":""}${d.minute}' · ${r.accepted??0}/${r.received??0} events · `+d.trace.map(t=>`${t.agent} ${t.ms}ms${t.tokens_in?` ${t.tokens_in}→${t.tokens_out}tok`:""}${t.recovery?` [fault → ${t.recovery}, ${t.attempts} attempts]`:""}`).join(" | ");
 $("trace").prepend(div);while($("trace").children.length>40)$("trace").lastChild.remove();}
function kpis(){const u=S.usage||{calls:0,input_tokens:0,output_tokens:0,usd:0};const proj=S.elapsed?u.usd/S.elapsed*90:0;
 $("kpis").innerHTML=[[`$${(+u.usd).toFixed(4)}`,"LLM cost so far"],[`$${proj.toFixed(3)}`,"projected for the match"],[u.calls,"LLM calls"],[(u.input_tokens+u.output_tokens).toLocaleString(),"tokens used"],
 [S.cards,"commentary lines"],[S.llm,"upgraded by AI"],[S.rejected,"AI rewrites rejected by checks"],[S.batches?Math.round(S.lat/S.batches)+" ms":"–","AI room latency per batch"]].map(([b,s])=>`<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join("")+(S.replay?`<div class="kpi"><b>0</b><span>live LLM calls now (replay of precomputed, checked AI commentary)</span></div>`:"");}
// ------------------------------------------------------------------ data panels
function refresh(force){if(!meta)return;S.lastRep=S.elapsed;const m=S.running?Math.max(0,S.period===1?Math.min(S.clockMin,45):S.clockMin):200;
 J(`/api/formation?seed=${seed}&minute=${S.running?Math.max(m,10):200}`).then(f=>{S.dots=[];Object.entries(f.teams).forEach(([tid,t])=>t.players.forEach(p=>{const[x,y]=p.avg||p.slot;S.dots.push({id:p.id,team:tid,x,y,n:p.number});}));});
 J(`/api/report?seed=${seed}&minute=${m}`).then(r=>{S.report=r;renderStats(r);renderHL(r);drawMomentum(r);if($("p-compare").classList.contains("on"))loadCompare();});drawWin();}
function renderStats(r){const h=r.home,a=r.away,th=r.teams[h.id],ta=r.teams[a.id];
 const rows=[["Goals","goals"],["Shots","shots"],["Shots on target","on_target"],["Chance quality (xG)","xg"],["Threat from passes (xT)","xt"],["Passes","passes"],["Pass completion %","pass_completion_pct"],["Forward passes (10 m+)","progressive_passes"],["Pressures","pressures"],["Fouls","fouls"],["Yellow cards","yellow_cards"],["Red cards","red_cards"]];
 $("tstats").innerHTML=`<div class="sbar"><div class="l"><b style="color:${h.color}">${esc(h.name)}</b><span>${r.finished?"Full-time":"up to "+r.minute+"'"}</span><b style="color:${a.color}">${esc(a.name)}</b></div></div>`+rows.map(([l,k])=>{const x=+th[k],y=+ta[k],s=Math.abs(x)+Math.abs(y)||1;
  return `<div class="sbar"><div class="l"><b>${x}</b><span>${l}</span><b>${y}</b></div><div class="t"><div style="width:${100*Math.abs(x)/s}%;background:${h.color}"></div><div style="width:${100*Math.abs(y)/s}%;background:${a.color}"></div></div></div>`;}).join("");
 const B=r.ball;if(B&&B.teams){const bh=B.teams[h.id],ba=B.teams[a.id],br=[["Avg pass difficulty (0–1)","avg_pass_difficulty"],["Hard passes (difficulty ≥ 0.6)","hard_passes"],["Hard-pass completion %","hard_pass_completion_pct"],["Avg pass speed (km/h)","avg_pass_speed_kmh"],["Avg shot speed (km/h)","avg_shot_speed_kmh"],["Ball travel by passes (km)","ball_travel_km"]];
  const who=x=>x?`${esc(x.player)} ${x.minute}'`:"—";
  $("tstats").innerHTML+=`<h3 style="margin:8px 0 2px">Ball &amp; pass intelligence</h3>`+br.map(([l,k])=>{const x=+bh[k],y=+ba[k],s=x+y||1;return `<div class="sbar"><div class="l"><b>${x}</b><span>${l}</span><b>${y}</b></div><div class="t"><div style="width:${100*x/s}%;background:${h.color}"></div><div style="width:${100*y/s}%;background:${a.color}"></div></div></div>`;}).join("")+
  `<p class="cap" id="ballrec">⚡ Fastest shot: <b>${B.fastest_shot?B.fastest_shot.value+" km/h":"—"}</b> ${who(B.fastest_shot)} · Fastest pass: <b>${B.fastest_pass?B.fastest_pass.value+" km/h":"—"}</b> ${who(B.fastest_pass)} · Hardest completed pass: ${[bh,ba].map(t=>t.hardest_completed_pass?`<b>${t.hardest_completed_pass.value}</b> ${who(t.hardest_completed_pass)}`:"—").join(" / ")}<br><span title="${esc(B.method)}">Computed from synthetic x/y coordinates and timestamps.</span></p>`;}
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
async function drawWin(){if(!meta)return;if(!S.wp||S.wp.seed!==seed)S.wp={seed,series:(await J(`/api/winprob?seed=${seed}`)).series};
 const ser=S.wp.series,upto=S.running?S.elapsed:(S.ended?999:0),pts=ser.filter(p=>p.final?upto>=999||(!S.running&&S.ended):p.minute<=upto);const cur=pts[pts.length-1]||ser[0];
 const h=H(),a=A();$("wpmini").innerHTML=`<div style="width:${cur.home*100}%;background:${h.color}"></div><div style="width:${cur.draw*100}%;background:#5b6577"></div><div style="width:${cur.away*100}%;background:${a.color}"></div>`;$("wpl").textContent=`Win ${h.short} ${Math.round(cur.home*100)}% · D ${Math.round(cur.draw*100)}% · ${a.short} ${Math.round(cur.away*100)}%`;$("probbar").innerHTML=[[h.short+" win",cur.home,h.color],["Draw",cur.draw,"#4b5568"],[a.short+" win",cur.away,a.color]].map(([l,p,c])=>`<div style="width:${p*100}%;background:${c}">${p>.08?`${l} ${Math.round(p*100)}%`:""}</div>`).join("");
 const c=$("wpc"),g=c.getContext("2d"),W=c.width,Hh=c.height;g.clearRect(0,0,W,Hh);g.strokeStyle="#ffffff25";g.font="16px system-ui";g.fillStyle="#9fb0c8";
 [0,.5,1].forEach(v=>{const y=Hh-20-(Hh-40)*v;g.beginPath();g.moveTo(50,y);g.lineTo(W,y);g.stroke();g.fillText(Math.round(v*100)+"%",4,y+5);});
 [0,15,30,45,60,75,90].forEach(m=>g.fillText(m+"'",50+(W-60)*m/91,Hh-2));
 [["home",h.color],["draw","#9fb0c8"],["away",a.color]].forEach(([k,cl])=>{g.strokeStyle=cl;g.lineWidth=4;g.beginPath();pts.filter(p=>!p.final).forEach((p,i)=>{const x=50+(W-60)*p.minute/91,y=Hh-20-(Hh-40)*p[k];i?g.lineTo(x,y):g.moveTo(x,y);});g.stroke();});}
let tacTeam=null;async function loadTactics(){if(!meta)return;tacTeam=tacTeam&&tm(tacTeam)?.id===tacTeam?tacTeam:H().id;
 $("tteam").innerHTML=[H(),A()].map(t=>`<button data-v="${t.id}" class="${t.id===tacTeam?"on":""}">${esc(t.name)}</button>`).join("");$("tteam").onclick=e=>{const b=e.target.closest("button");if(b){tacTeam=b.dataset.v;loadTactics();}};
 const f=await J(`/api/formation?seed=${seed}&minute=${S.running?S.clockMin:200}`),c=$("tac").getContext("2d"),t=tm(tacTeam);drawPitch(c);
 f.teams[tacTeam].players.forEach(p=>{const[sx,sy]=[p.slot[0]*10,p.slot[1]*10];c.strokeStyle="#ffffff90";c.lineWidth=3;c.setLineDash([6,6]);c.beginPath();c.arc(sx,sy,24,0,7);c.stroke();c.setLineDash([]);
  if(p.avg){const[ax,ay]=[p.avg[0]*10,p.avg[1]*10];c.strokeStyle="#ffffff60";c.beginPath();c.moveTo(sx,sy);c.lineTo(ax,ay);c.stroke();c.fillStyle=t.color;c.strokeStyle="#fff";c.beginPath();c.arc(ax,ay,22,0,7);c.fill();c.stroke();
   c.fillStyle="#fff";c.font="800 22px system-ui";c.textAlign="center";c.fillText(p.number,ax,ay+8);c.textAlign="start";}});
 // labels last, with collision avoidance: try below / above / right / left of the dot, skip if every spot overlaps
 const boxes=[],dots=f.teams[tacTeam].players.filter(p=>p.avg).map(p=>[p.avg[0]*10,p.avg[1]*10]);c.font="700 30px system-ui";
 const hit=(a,b)=>a.x<b.x+b.w&&b.x<a.x+a.w&&a.y<b.y+b.h&&b.y<a.y+a.h;
 f.teams[tacTeam].players.filter(p=>p.avg).forEach(p=>{const[ax,ay]=[p.avg[0]*10,p.avg[1]*10],txt=p.name.split(" ").slice(-1)[0],w=c.measureText(txt).width+12,h=36;
  const spots=[[ax-w/2,ay+26],[ax-w/2,ay-26-h],[ax+26,ay-h/2],[ax-26-w,ay-h/2]];
  for(const[x,y]of spots){const bx={x,y,w,h};if(x<0||x+w>1050||y<0||y+h>680)continue;if(boxes.some(o=>hit(o,bx))||dots.some(([dx,dy])=>hit(bx,{x:dx-22,y:dy-22,w:44,h:44})))continue;
   boxes.push(bx);c.fillStyle="#0b1220cc";c.beginPath();c.roundRect(x,y,w,h,8);c.fill();c.fillStyle="#fff";c.fillText(txt,x+6,y+27);break;}});}
async function loadCompare(){if(!meta)return;const pl=[...H().players.slice(0,11).map(p=>[p,H()]),...A().players.slice(0,11).map(p=>[p,A()])];
 if($("pa").options.length!==pl.length){[$("pa"),$("pb")].forEach((s,j)=>{s.innerHTML=pl.map(([p,t])=>`<option value="${p.id}">${esc(p.name)} (${t.short}, ${p.position})</option>`).join("");});$("pa").value=H().players[9].id;$("pb").value=A().players[9].id;$("pa").onchange=$("pb").onchange=loadCompare;}
 const r=await J(`/api/compare?seed=${seed}&a=${$("pa").value}&b=${$("pb").value}&minute=${S.running?S.clockMin:200}`);const x=r.a||{},y=r.b||{};
 const rows=[["Impact (goals+xG+xT)","impact"],["Goals","goals"],["Shots","shots"],["Chance quality (xG)","xg"],["Threat from passes (xT)","xt"],["Passes","passes"],["Pass completion %","pass_completion_pct"],["Fouls","fouls"]];
 $("cmp").innerHTML=`<div class="sbar"><div class="l"><b>${esc($("pa").selectedOptions[0].text)}</b><b>${esc($("pb").selectedOptions[0].text)}</b></div></div>`+rows.map(([l,k])=>{const a=+(x[k]||0),b=+(y[k]||0),s=Math.abs(a)+Math.abs(b)||1;
  return `<div class="sbar"><div class="l"><b>${a}</b><span>${l}</span><b>${b}</b></div><div class="t"><div style="width:${100*Math.abs(a)/s}%;background:var(--acc)"></div><div style="width:${100*Math.abs(b)/s}%;background:var(--acc2)"></div></div></div>`;}).join("")+(!r.a&&!r.b?'<p class="cap">No actions yet for these players.</p>':"");}
// ------------------------------------------------------------------ ask the analyst
function sugg(){const nine=meta&&(meta.home.players.find(p=>p.number===9)||meta.home.players[0]),tl=meta?[`Show me all shots by ${nine.name}`,"Compare teams in the 2nd half",`Hard passes by ${meta.away.name}`]:[];$("sugg").innerHTML=[...tl,...SUGG[opt.lang]].map(s=>`<button type="button">${esc(s)}</button>`).join("");$("sugg").querySelectorAll("button").forEach(b=>b.onclick=()=>{$("q").value=b.textContent;ask();});}
async function ask(){const q=$("q").value.trim();if(!q)return;$("q").value="";const ch=$("chat");ch.insertAdjacentHTML("beforeend",`<div class="msg me">${esc(q)}</div>`);
 const m=document.createElement("div");m.className="msg";m.setAttribute("aria-live","polite");m.textContent="Planning tool calls…";ch.appendChild(m);$("p-ask").scrollTop=1e6;
 const minute=S.running?(S.period===1?Math.min(S.clockMin,45):S.clockMin):200,upto=minute>=200?"full-time":minute+"'";
 try{const r=await fetch("/api/agent",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({seed,question:q,minute})}).then(r=>{if(!r.ok)throw r;return r.json();});
  const tools=r.trace.filter(t=>t.step==="tool"),plan=r.trace.find(t=>t.step==="plan")||{};
  const tr=`<details class="trace"><summary>🛠 ${tools.length} tool call${tools.length===1?"":"s"} · planned by ${plan.by==="llm"?"AI planner (gpt-4.1-mini)":"rules router"} · ${r.ms} ms</summary>${r.trace.map(t=>t.step==="plan"?`<div class="tc"><b>plan</b> ${t.by==="llm"?"AI planner chose the tools below":"intent matched by the deterministic router (AI planner runs when Live AI is on)"}</div>`:`<div class="tc"><b>${esc(t.tool)}</b>(${esc(Object.entries(t.args||{}).map(([k,v])=>k+"="+v).join(", "))}) <span class="muted">${t.ms} ms · ${t.highlights||0} on pitch</span><pre>${esc(JSON.stringify(t.result).slice(0,400))}</pre></div>`).join("")}</details>`;
  let txt=r.text,extra="";
  if(tools.every(t=>t.tool==="key_moments")&&!/moment|highlight/i.test(q)){try{const a=await fetch("/api/ask",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({seed,question:q,minute,lang:opt.lang})}).then(r=>r.json());txt=a.text;extra=a.source==="llm"?'<span class="chip ok">AI answer ✓ passed checks</span> ':"";}catch(e){}}
  m.innerHTML=`${esc(txt)}<small>${extra}<span class="chip ok">grounded in event data</span> · up to ${upto}${r.highlights.length?` · <a href="#" class="showq">show ${r.highlights.length} on pitch</a>`:""}</small>${tr}`;
  const show=()=>{S.qhl={items:r.highlights,q,until:performance.now()+14000};document.querySelector("#v-live").scrollIntoView?.({block:"start"});};if(r.highlights.length)show();
  m.querySelector(".showq")?.addEventListener("click",e=>{e.preventDefault();show();});say(txt);announce(txt);$("p-ask").scrollTop=1e6;}
 catch(e){m.textContent="The analyst desk is unavailable right now.";}}
$("askf").onsubmit=e=>{e.preventDefault();ask();};
// ------------------------------------------------------------------ league view
// ------------------------------------------------------------------ match lifecycle
function setMeta(m){meta=m;[m.home,m.away].forEach(t=>t.players.forEach(p=>NUMS[p.id]=p.number));const h=m.home,a=m.away;$("hn").textContent=h.name;$("an").textContent=a.name;$("hc").src=crest(h.id);$("ac").src=crest(a.id);
 ORIG={h:h.color,a:a.color};document.documentElement.style.setProperty("--home",h.color);document.documentElement.style.setProperty("--away",a.color);if(isOn("cvd"))applyPalette();
 const cl=$("club");cl.length=1;loadPreview;[h,a].forEach(t=>cl.add(new Option(t.name,t.id)));
 const fp=$("fplayer");fp.length=1;[h,a].forEach(t=>t.players.forEach(p=>fp.add(new Option(`${p.name} (${t.short})`,p.id))));}
function resetUI(){$("feed").innerHTML='<li class="empty">Commentary starts at kick-off.</li>';$("trace").innerHTML="";$("timeline").querySelectorAll(".tl").forEach(x=>x.remove());
 $("prog").style.width="0";$("head").style.left="0";$("score").textContent="0 – 0";$("clock").textContent="0'";$("period").textContent="Pre-match";$("live").hidden=true;pipe();kpis();}
async function loadMatch(){if(es)es.close();S=fresh();resetUI();const j=await J(`/api/match?seed=${seed}&meta_only=true`);setMeta(j.events[0].meta);
 S.score={[meta.home.id]:0,[meta.away.id]:0};loadPreview();sugg();refresh();$("nowt").textContent=`${meta.home.name} v ${meta.away.name} at ${j.events[0].meta.venue}. Press Kick off to start.`;}
function kick(){if(es)es.close();const keep=meta;S=fresh();resetUI();S.score={[keep.home.id]:0,[keep.away.id]:0};S.running=true;$("live").hidden=false;$("go").innerHTML='↻<span class="bl"> Restart</span>';$("pause").disabled=false;$("pause").innerHTML='⏸<span class="bl"> Pause</span>';
 tab("feed");$("buffer").classList.add("on");const q=new URLSearchParams({seed,speed:+opt.speed*1.6,batch_s:150,mode:opt.mode,lang:opt.lang,club:$("club").value,player:$("fplayer").value,replay:opt.src==="replay"?"true":"false",viewer,sid:(S.sid=viewer+"-"+Date.now().toString(36))});
 es=new EventSource("/api/stream?"+q);
 es.addEventListener("tick",m=>{const ev=JSON.parse(m.data).event;S.buf.push(ev);S.lastRecv=ev.t;if(ev.type==="match_end")S.ended=true;});
 es.addEventListener("cards",m=>onCards(JSON.parse(m.data)));
 es.addEventListener("end",()=>{es.close();S.ended=true;});
 es.onerror=()=>{if(es.readyState===2){S.ended=true;if(!S.buf.length&&!S.applied.size)netState(false,true);}};}
function finish(){$("live").hidden=true;$("pause").disabled=true;S.pending.forEach(c=>addCardItem(c));S.pendMin.forEach(addCardItem);S.pending.clear();S.pendMin=[];refresh(true);drawWin();fullTime();}
$("pause").onclick=()=>{S.paused=!S.paused;$("pause").innerHTML=S.paused?'▶<span class="bl"> Resume</span>':'⏸<span class="bl"> Pause</span>';};
$("go").onclick=kick;
$("match").onchange=()=>{seed=+$("match").value;S.wp=null;loadMatch();};
async function fullTime(){$("ftbody").innerHTML="<p>The agents are writing the full-time report…</p>";$("ft").classList.add("on");
 const r=await J(`/api/report?seed=${seed}&recap=true&lang=${opt.lang}`),h=r.home,a=r.away;
 $("dl").href=`/api/report?seed=${seed}&format=md&recap=true&lang=${opt.lang}`;
 $("ftbody").innerHTML=`<span class="chip">Full-time report · synthetic match</span><h2 style="font-size:2em;margin:12px 0">${esc(h.name)} ${r.score[h.id]} – ${r.score[a.id]} ${esc(a.name)}</h2>
 <p style="font-size:1.1em">${esc(r.recap.text)}</p><p><span class="chip ${r.recap.source==="llm"?"ok":""}">${r.recap.source==="llm"?"AI recap ✓ passed numbers, claims and player checks":"rules recap"}</span></p>
 <div style="display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 4px"><button class="btn" onclick="$('ft').classList.remove('on');reel('full')">▶ Watch the condensed match (~60 s)</button><button class="btn ghost" onclick="recapCard()">⬇ Shareable recap card</button><button class="btn ghost" onclick="$('ft').classList.remove('on');perspectives()">👥 3 viewers, 1 moment</button></div><h3>Key moments</h3>${r.key_moments.filter(k=>k.importance>=4).map(k=>`<div class="hl"><span class="ic">${ICON[k.kind]||"•"}</span><div>${esc(k.label)}</div><span class="mm">${k.minute}'</span></div>`).join("")}`;}
J("/api/matches").then(j=>{fixtures=j.matches;const groups={};fixtures.forEach(f=>{const g=f.matchday?`Matchday ${f.matchday}`:"Showcase friendlies";(groups[g]=groups[g]||[]).push(f);});
 $("match").innerHTML=Object.entries(groups).map(([g,fs])=>`<optgroup label="${g}">${fs.map(f=>`<option value="${f.seed}">${esc(f.home)} v ${esc(f.away)}</option>`).join("")}</optgroup>`).join("");$("match").value="7";seed=7;loadMatch();});
// ------------------------------------------------------------------ pre-match comparison (league matches before this fixture)
async function loadPreview(){const s0=seed;const p=await J(`/api/preview?seed=${seed}`);if(s0!==seed||!meta||!p||!p.home)return;const h=H(),a=A(),hs=p.home,as=p.away,pr=p.pre_match_probability;
 const ord=n=>n+(["th","st","nd","rd"][(n%100>10&&n%100<14)||n%10>3?0:n%10]);
 $("hr").textContent=hs.table?`${ord(hs.table.position)} · ${hs.table.points} pts`:"";$("ar").textContent=as.table?`${ord(as.table.position)} · ${as.table.points} pts`:"";
 const form=t=>t.table?`<span class="form">${t.table.form.map(f=>`<b class="${f}">${f}</b>`).join("")}</span>`:"–";
 const v=(t,f)=>t.season?f(t.season):"–",pm=k=>t=>t.per_match[k];
 const rows=[["Position",t=>t.table?ord(t.table.position):"–",t=>t.table?-t.table.position:null],["Points",t=>t.table?.points??"–",t=>t.table?.points],
  ["Record (W-D-L)",t=>t.table?`${t.table.won}-${t.table.drawn}-${t.table.lost}`:"–",null],["Form (last 5)",form,null],
  ["Goals for / match",t=>v(t,pm("goals_for")),t=>t.season?.per_match.goals_for],["Goals against / match",t=>v(t,pm("goals_against")),t=>t.season&&-t.season.per_match.goals_against],
  ["xG for / match",t=>v(t,pm("xg_for")),t=>t.season?.per_match.xg_for],["xG against / match",t=>v(t,pm("xg_against")),t=>t.season&&-t.season.per_match.xg_against],
  ["Shots / match",t=>v(t,pm("shots")),t=>t.season?.per_match.shots],["Shots against / match",t=>v(t,pm("shots_against")),t=>t.season&&-t.season.per_match.shots_against],
  ["Possession* %",t=>v(t,pm("possession_pass_share_pct")),t=>t.season?.per_match.possession_pass_share_pct],["Pass completion %",t=>v(t,pm("pass_completion_pct")),t=>t.season?.per_match.pass_completion_pct],
  ["Clean sheets",t=>v(t,s=>s.totals.clean_sheets),t=>t.season?.totals.clean_sheets],["Top scorer",t=>t.season?.top_scorer?`${esc(t.season.top_scorer.name)} (${t.season.top_scorer.goals})`:"–",null]];
 const cmp=rows.map(([l,f,k])=>{const x=k&&k(hs),y=k&&k(as),bh=k&&x!=null&&y!=null&&x>y,ba=k&&x!=null&&y!=null&&y>x;
  return `<tr><td style="text-align:left;${bh?"color:var(--acc);font-weight:700":""}">${f(hs)}</td><td class="muted" style="text-align:center;font-size:.85em">${l}</td><td style="${ba?"color:var(--acc);font-weight:700":""}">${f(as)}</td></tr>`;}).join("");
 const mt=p.meetings.length?p.meetings.map(m=>`<div class="fx"><span>MD ${m.matchday}</span><img src="/api/crest/${m.home}.svg" alt=""><span>${esc(tm(m.home).short)}</span><span class="sc">${m.score[m.home]} – ${m.score[m.away]}</span><span>${esc(tm(m.away).short)}</span><img src="/api/crest/${m.away}.svg" alt=""><button class="btn ghost" data-s="${m.seed}" style="padding:2px 8px">Watch</button></div>`).join(""):'<p class="muted">First meeting this season.</p>';
 $("prev").innerHTML=`<p class="cap">${p.matchday?`Matchday ${p.matchday} · stats from the ${p.standings_after_matchday} league matchdays played before this fixture`:`Showcase friendly · stats from the full season (${p.standings_after_matchday} matchdays)`}${!hs.season?" · season opener: no matches yet":""}</p>
 <table><tr><th style="text-align:left;color:${h.color}">${esc(h.short)}</th><th style="text-align:center"></th><th style="color:${a.color}">${esc(a.short)}</th></tr>${cmp}</table>
 <p class="cap" style="margin-top:4px">*Possession = share of passes. Green = better.</p>
 <h3>Previous meetings this season</h3>${mt}
 <h3>Pre-match odds <span class="muted" style="font-weight:400">from team ratings</span></h3><div class="probbar">${[[h.short,pr.home,h.color],["Draw",pr.draw,"#5b6577"],[a.short,pr.away,a.color]].map(([l,x,c])=>`<div style="width:${x*100}%;background:${c}">${l} ${Math.round(x*100)}%</div>`).join("")}</div>
 <h3>Line-ups (4-3-3)</h3><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:.85em">${[h,a].map(t=>`<div>${p.lineups[t.id].map(pl=>`<div><span class="muted">${pl.number}</span> ${esc(pl.name)}</div>`).join("")}</div>`).join("")}</div>`;
 $("prev").querySelectorAll("button[data-s]").forEach(b=>b.onclick=()=>watch(b.dataset.s));}
function watch(s){$("match").value=s;$("match").onchange();document.querySelector('.views button[data-v="live"]').click();$("teamdrawer").classList.remove("on");}
// ------------------------------------------------------------------ league
let LG=null,lgDay=30,selTeam=null;
async function loadLeague(){LG=await J(`/api/league?day=${lgDay}`);$("lgname").textContent=LG.name;$("lgday").max=LG.days;$("lgday").value=lgDay;$("lgdayl").textContent=`after matchday ${lgDay}`;
 const mv=m=>m>0?`<span style="color:#3fb950">▲${m}</span>`:m<0?`<span style="color:#f07489">▼${-m}</span>`:'<span class="muted">–</span>';
 $("ltable").innerHTML="<tr><th>#</th><th>Club</th><th></th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th><th>Form</th></tr>"+LG.table.map(r=>
  `<tr class="trow" data-t="${r.id}" style="cursor:pointer${r.position<=1?";box-shadow:inset 3px 0 var(--acc)":r.position>=15?";box-shadow:inset 3px 0 var(--bad)":""}"><td>${r.position}</td><td><img src="${r.crest}" alt="">${esc(r.name)}</td><td>${mv(r.move)}</td><td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td><td>${r.gf}</td><td>${r.ga}</td><td>${r.gd>0?"+":""}${r.gd}</td><td><b>${r.points}</b></td><td class="form">${r.form.map(f=>`<b class="${f}">${f}</b>`).join("")}</td></tr>`).join("");
 $("ltable").querySelectorAll(".trow").forEach(tr=>{tr.onclick=()=>teamPage(tr.dataset.t);tr.onmouseenter=()=>{selTeam=tr.dataset.t;drawPos();};});
 const lead=(k,lbl,f)=>`<div><h3>${lbl}</h3><table>${LG.leaders[k].slice(0,5).map((p,i)=>{const c=LG.clubs.find(x=>x.id===p.team);return `<tr><td>${i+1}</td><td><img src="${c.crest}" alt="">${esc(p.name)}</td><td><b>${f(p)}</b></td></tr>`;}).join("")}</table></div>`;
 $("leaders").innerHTML=lead("goals","Top scorers",p=>p.goals)+lead("assists","Assists",p=>p.assists)+lead("xg","Expected goals (xG)",p=>p.xg)+lead("xt","Threat from passes (xT)",p=>p.xt);
 if(!$("md").options.length){$("md").innerHTML=Array.from({length:LG.days},(_,i)=>`<option value="${i+1}">Matchday ${i+1}</option>`).join("")+'<option value="0">Showcase friendlies</option>';$("md").onchange=$("spoil").onchange=fx;$("md").value=lgDay;}
 fx();drawPos();}
function fx(){const d=+$("md").value,sp=$("spoil").checked;$("fixtures").innerHTML=LG.fixtures.filter(f=>f.matchday===d).map(f=>`<div class="fx"><img src="/api/crest/${f.home_id}.svg" alt=""><span style="flex:1">${esc(f.home)}</span><span class="sc">${sp&&f.score&&d<=lgDay?`${f.score[f.home_id]} – ${f.score[f.away_id]}`:"v"}</span><span style="flex:1;text-align:right">${esc(f.away)}</span><img src="/api/crest/${f.away_id}.svg" alt=""><button class="btn ghost" data-s="${f.seed}" style="padding:2px 8px">Watch</button></div>`).join("");
 $("fixtures").querySelectorAll("button").forEach(b=>b.onclick=()=>watch(b.dataset.s));}
function drawPos(){if(!LG)return;const c=$("poschart"),g=c.getContext("2d"),W=c.width,Hh=c.height,n=lgDay;g.clearRect(0,0,W,Hh);g.font="12px system-ui";g.fillStyle="#8d9ab0";
 const X=d=>36+(W-50)*(d-1)/Math.max(1,LG.days-1),Y=p=>10+(Hh-30)*(p-1)/15;[1,4,8,12,16].forEach(p=>g.fillText(p,6,Y(p)+4));[1,10,20,LG.days].forEach(d=>{g.textAlign=d===LG.days?"right":d===1?"left":"center";g.fillText("MD"+d,X(d)+(d===LG.days?4:0),Hh-4);});g.textAlign="start";
 const order=Object.keys(LG.positions).sort(a=>a===selTeam?1:-1);order.forEach(t=>{const c2=LG.clubs.find(x=>x.id===t),on=t===selTeam;g.strokeStyle=on?c2.color:"#ffffff22";g.lineWidth=on?3:1;g.beginPath();
  LG.positions[t].forEach((p,i)=>{i?g.lineTo(X(i+1),Y(p)):g.moveTo(X(i+1),Y(p));});g.stroke();});
 $("poscap").textContent=selTeam?`${LG.clubs.find(x=>x.id===selTeam).name}: position after each matchday`:"Hover a club in the table to trace its season.";}
async function teamPage(id){const t=await J(`/api/team/${id}?day=${lgDay}`),c=t.club,s=t.season,st=t.standing,pm=s.per_match,to=s.totals;selTeam=id;drawPos();
 const name=x=>LG.clubs.find(k=>k.id===x)?.short||x;
 $("teambody").innerHTML=`<div style="display:flex;gap:12px;align-items:center"><img src="${c.crest}" style="width:48px;height:58px" alt=""><div><h2 style="font-size:1.3em">${esc(c.name)}</h2><div class="muted">${esc(c.stadium)} · ${st.position}${["th","st","nd","rd"][st.position%10>3||[11,12,13].includes(st.position)?0:st.position%10]} after matchday ${lgDay} · ${st.points} pts · ${st.won}-${st.drawn}-${st.lost}</div></div></div>
 <div class="kpis" style="grid-template-columns:repeat(4,1fr)">${[[to.goals_for,"goals for"],[to.goals_against,"goals against"],[to.xg_for,"xG for"],[to.xg_against,"xG against"],[pm.shots,"shots / match"],[pm.possession_pass_share_pct+"%","possession (pass share)"],[pm.pass_completion_pct+"%","pass completion"],[to.clean_sheets,"clean sheets"]].map(([b,l])=>`<div class="kpi"><b>${b}</b><span>${l}</span></div>`).join("")}</div>
 <h3>Squad · season stats</h3><table><tr><th>Player</th><th></th><th>Apps</th><th>G</th><th>A</th><th>Shots</th><th>xG</th><th>xT</th><th>Passes</th></tr>${s.squad.map(p=>`<tr><td>${esc(p.name)}</td><td></td><td>${p.apps}</td><td><b>${p.goals}</b></td><td>${p.assists}</td><td>${p.shots}</td><td>${p.xg}</td><td>${p.xt}</td><td>${p.passes}</td></tr>`).join("")}</table>
 <h3>Results & fixtures</h3>${t.matches.map(m=>{const home=m.home===id,o=home?m.away:m.home,res=m.score?(m.score[id]>m.score[o]?"W":m.score[id]<m.score[o]?"L":"D"):null;
  return `<div class="fx"><span class="muted" style="min-width:42px">MD ${m.matchday}</span><span>${home?"vs":"at"}</span><img src="/api/crest/${o}.svg" alt=""><span style="flex:1">${esc(name(o))}</span>${res?`<span class="form"><b class="${res}">${res}</b></span><span class="sc">${m.score[m.home]} – ${m.score[m.away]}</span>`:'<span class="muted sc">upcoming</span>'}<button class="btn ghost" data-s="${m.seed}" style="padding:2px 8px">Watch</button></div>`;}).join("")}`;
 $("teambody").querySelectorAll("button[data-s]").forEach(b=>b.onclick=()=>watch(b.dataset.s));$("teamdrawer").classList.add("on");}
$("lgday").oninput=()=>{lgDay=+$("lgday").value;$("lgdayl").textContent=`after matchday ${lgDay}`;};$("lgday").onchange=()=>{$("md").value=lgDay;loadLeague();};
pipe();kpis();sugg();requestAnimationFrame(frame);$("chaosbtn").onclick=chaos;
// ------------------------------------------------------------------ v12: highlight reel ("best moments" / condensed match)
const R={on:false,clips:[],ci:0,sched:[],k:0,clk:0,paused:false,trail:[],shots:[],ball:[52.5,34],from:[52.5,34],bt:0,bd:1,title:"",kind:"best"};
async function reel(kind){const was=S.running&&!S.paused;if(was){S.paused=true;$("pause").innerHTML='▶<span class="bl"> Resume</span>';}R.resume=was;
 $("reelui").hidden=false;$("reelst").textContent="Loading the best moments…";
 try{const d=await J(`/api/reel?seed=${seed}&mode=${opt.mode}&lang=${opt.lang}`);if(!d.clips.length){$("reelst").textContent="No key moments in this match yet.";return;}
  R.data=d;R.kind=kind||"best";R.clips=kind==="full"?d.clips:d.clips.slice().sort((a,b)=>b.moment.importance-a.moment.importance||a.moment.event_id-b.moment.event_id);
  R.on=true;R.paused=false;startClip(0);$("pitch").focus();announce(`Highlights: ${R.clips.length} moments. Press right arrow for next, Escape to exit.`);}
 catch(e){$("reelst").textContent="Highlights unavailable right now.";}}
function startClip(i){R.ci=Math.max(0,Math.min(i,R.clips.length-1));const c=R.clips[R.ci];R.trail=[];R.shots=[];R.clk=0;R.k=0;R.sched=[];let at=1.1;
 c.events.forEach(e=>{R.sched.push({at,e});at+=e.type==="pass"?.75:e.type==="foul"?1.0:e.type==="shot"?1.3:e.type==="goal"?2.4:.8;});R.end=at+3.2;R.cap=null;
 const st=c.events.find(e=>e.x!=null);if(st){const[x,y]=P(st.team,st.x,st.y);R.ball=[x/10,y/10];R.from=R.ball.slice();}
 $("reelst").textContent=`${R.kind==="full"?"Condensed match":"Best moments"} · ${R.ci+1}/${R.clips.length} · ${c.moment.minute}'`;
 say(`${c.moment.minute}th minute. ${c.title}`);}
function reelStep(e){const tc=col(e.team),now=performance.now();
 if(e.type==="pass"){const a=P(e.team,e.x,e.y),b=P(e.team,e.end_x,e.end_y);R.trail.push({a,b,c:tc,ok:e.success});R.from=R.ball.slice();R.ball=[b[0]/10,b[1]/10];R.bt=now;R.bd=600;}
 else if(e.type==="shot"){const[x,y]=P(e.team,e.x,e.y),g=P(e.team,104.5,34+(e.y-34)*.15);R.shots.push({x,y,xg:e.xg,c:tc,goal:e.outcome==="goal"});R.from=[x/10,y/10];R.ball=[g[0]/10,g[1]/10];R.bt=now;R.bd=350;act(e.outcome==="goal"?"GOAL!":`Shot · ${e.outcome.replace("_"," ")} · xG ${e.xg}`,e.outcome==="goal"?"#f5c542":"#fff",1500);}
 else if(e.type==="goal"){R.shots.forEach(s=>s.goal=true);const[gx,gy]=P(e.team,103,34);for(let i=0;i<120;i++)confetti.push({x:gx,y:gy,vx:(Math.random()-.5)*16,vy:-Math.random()*14,life:90,c:i%2?tc:"#ffc83d"});cheer();act(`GOAL! ${e.player}`,"#f5c542",2200);}
 else if(e.type==="foul"){act(`Foul · ${e.player||""}`,"#f07489",1200);}
 else if(e.type==="card"){act(`${e.card==="yellow"?"🟨":"🟥"} ${e.player}`,e.card==="yellow"?"#f5c542":"#ef4560",2200);}}
function reelFrame(dt,now){if(!R.paused)R.clk+=dt/1000;const c=R.clips[R.ci];
 while(R.k<R.sched.length&&R.sched[R.k].at<=R.clk){reelStep(R.sched[R.k].e);R.k++;}
 if(R.k>=R.sched.length&&!R.cap){R.cap=true;announce(`${c.moment.minute}'. ${c.caption}`);say(c.caption);}
 if(R.clk>=R.end){if(R.ci<R.clips.length-1)startClip(R.ci+1);else{R.paused=true;R.clk=R.end;$("reelst").textContent=`End of highlights · ${R.clips.length} moments`;}}
 drawPitch(cx);R.trail.forEach((p,i)=>{cx.globalAlpha=.35+.6*(i+1)/R.trail.length;cx.strokeStyle=p.c;cx.lineWidth=5;cx.setLineDash(p.ok?[]:[10,10]);cx.beginPath();cx.moveTo(...p.a);cx.lineTo(...p.b);cx.stroke();});cx.setLineDash([]);cx.globalAlpha=1;
 R.shots.forEach(s=>{cx.lineWidth=5;cx.strokeStyle=s.goal?"#fff":s.c;cx.fillStyle=s.c;if(s.goal)star(cx,s.x,s.y,24);else{cx.beginPath();cx.arc(s.x,s.y,10+60*s.xg,0,7);cx.stroke();}});
 const k=Math.min(1,(now-R.bt)/R.bd),e=1-Math.pow(1-k,3),bx=(R.from[0]+(R.ball[0]-R.from[0])*e)*10,by=(R.from[1]+(R.ball[1]-R.from[1])*e)*10;
 cx.fillStyle="#fff";cx.strokeStyle="#000";cx.lineWidth=4;cx.beginPath();cx.arc(bx,by,12,0,7);cx.fill();cx.stroke();
 if(S.action&&S.action.until>now){cx.font="700 24px system-ui";const t=S.action.text,w=cx.measureText(t).width,lx=Math.min(Math.max(bx-w/2,10),1040-w-12),ly=by>90?by-34:by+52;cx.fillStyle="#0a0e16e6";cx.beginPath();cx.roundRect(lx-8,ly-24,w+16,34,8);cx.fill();cx.fillStyle=S.action.c||"#fff";cx.fillText(t,lx,ly);}
 confetti=confetti.filter(p=>p.life>0);confetti.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.vy+=.25;p.life--;cx.fillStyle=p.c;cx.fillRect(p.x,p.y,8,12);});
 // header + progress + caption
 const tot=R.clips.length,prog=(R.ci+Math.min(1,R.clk/R.end))/tot;cx.fillStyle="#0008";cx.fillRect(5,5,1040,8);cx.fillStyle="#2dd4a7";cx.fillRect(5,5,1040*prog,8);
 cx.font="800 22px system-ui";const hd=`${R.kind==="full"?"CONDENSED MATCH":"BEST MOMENTS"}  ${R.ci+1}/${tot}  ·  ${c.moment.minute}'`,hw=cx.measureText(hd).width;cx.fillStyle="#0a0e16d0";cx.beginPath();cx.roundRect(16,22,hw+24,38,8);cx.fill();cx.fillStyle="#2dd4a7";cx.fillText(hd,28,49);
 cx.font="800 26px system-ui";const ti=c.title+(c.ai?"  ✦":"");cx.font="500 24px system-ui";const lines=wrapLines(cx,c.caption,960).slice(0,3);const bh=58+lines.length*30;
 cx.fillStyle="#0a0e16e0";cx.beginPath();cx.roundRect(20,670-bh-10,1010,bh,10);cx.fill();cx.fillStyle=col(c.moment.team);cx.fillRect(20,670-bh-10,6,bh);
 cx.font="800 26px system-ui";cx.fillStyle="#f5c542";cx.fillText(ti,40,670-bh+24);cx.font="500 24px system-ui";cx.fillStyle="#fff";lines.forEach((l,i)=>cx.fillText(l,40,670-bh+58+i*30));}
function wrapLines(g,t,w){const out=[];let line="";String(t).split(" ").forEach(word=>{if(g.measureText(line+word).width>w&&line){out.push(line.trim());line="";}line+=word+" ";});if(line.trim())out.push(line.trim());return out;}
function reelExit(){R.on=false;$("reelui").hidden=true;confetti=[];if(R.resume){S.paused=false;$("pause").innerHTML='⏸<span class="bl"> Pause</span>';}speechSynthesis?.cancel?.();}
// ------------------------------------------------------------------ v12: shareable recap card
async function recapCard(){const r=await J(`/api/report?seed=${seed}`),h=r.home,a=r.away,c=$("share"),g=c.getContext("2d");
 g.fillStyle="#0b1220";g.fillRect(0,0,1200,630);const gr=g.createLinearGradient(0,0,1200,0);gr.addColorStop(0,col(h.id));gr.addColorStop(1,col(a.id));g.fillStyle=gr;g.fillRect(0,0,1200,14);
 g.fillStyle="#9fb0c8";g.font="600 26px system-ui";g.fillText(r.finished?"FULL-TIME · synthetic match":`UP TO ${r.minute}' · synthetic match`,60,72);
 const img=src=>new Promise(ok=>{const i=new Image();i.onload=()=>ok(i);i.onerror=()=>ok(null);i.src=src;});const[ih,ia]=await Promise.all([img(crest(h.id)),img(crest(a.id))]);
 if(ih)g.drawImage(ih,60,100,90,108);if(ia)g.drawImage(ia,1050,100,90,108);
 g.fillStyle="#fff";g.font="800 44px system-ui";g.fillText(h.name,170,150);g.textAlign="right";g.fillText(a.name,1030,150);g.textAlign="center";g.font="900 96px system-ui";g.fillText(`${r.score[h.id]} – ${r.score[a.id]}`,600,250);g.textAlign="start";
 const goals=r.key_moments.filter(k=>k.kind==="goal");g.font="500 26px system-ui";g.fillStyle="#e9eef6";
 [h,a].forEach((t,j)=>{const gl=goals.filter(k=>k.team===t.id).map(k=>`⚽ ${k.player} ${k.minute}'`);g.textAlign=j?"right":"left";gl.slice(0,4).forEach((s,i)=>g.fillText(s,j?1140:60,300+i*34));});g.textAlign="start";
 const th=r.teams[h.id],ta=r.teams[a.id],rows=[["Shots",th.shots,ta.shots],["Chance quality (xG)",th.xg,ta.xg],["Threat from passes (xT)",th.xt,ta.xt],["Pass completion %",th.pass_completion_pct,ta.pass_completion_pct]];
 rows.forEach(([l,x,y],i)=>{const Y=440+i*36,s=(+x)+(+y)||1;g.fillStyle="#9fb0c8";g.font="500 20px system-ui";g.textAlign="center";g.fillText(l,600,Y);g.textAlign="start";g.fillStyle="#fff";g.font="700 22px system-ui";g.fillText(x,330,Y);g.textAlign="right";g.fillText(y,870,Y);g.textAlign="start";
  g.fillStyle=col(h.id);g.fillRect(380,Y+6,220*x/s,6);g.fillStyle=col(a.id);g.fillRect(600,Y+6,220*y/s,6);});
 const p=r.players[0];if(p){g.fillStyle="#f5c542";g.font="700 24px system-ui";g.fillText(`★ Player of the match: ${p.name} (impact ${p.impact})`,60,415);}
 g.fillStyle="#2dd4a7";g.font="700 22px system-ui";g.fillText("Inside the Game · five-agent AI room · fictional clubs and players",60,604);
 const l=document.createElement("a");l.download=`recap-${h.short}-${a.short}.png`;l.href=c.toDataURL("image/png");l.click();toast("Recap card saved (1200×630 PNG)");}
// ------------------------------------------------------------------ v12: same moment, three viewers (Personalise agent)
async function perspectives(minute){const m=minute??(S.running||S.ended?Math.max(1,S.clockMin):200);$("pvbody").innerHTML='<p class="muted">Asking the Personalise agent for three viewers…</p>';$("pv").classList.add("on");$("pvclose").focus();
 try{const d=await J(`/api/perspectives?seed=${seed}&minute=${m}&lang=${opt.lang}`);if(!d.event){$("pvbody").innerHTML='<p class="muted">No key moment yet. Try after the first big chance.</p>';return;}
  const e=d.event,W={fan:["🔥","Fan","emotion first, no jargon"],neutral:["⚖️","Neutral","balanced, plain facts"],analyst:["📐","Analyst","numbers & tactics"]};
  const traits=t=>{const n=(t.match(/\d+(\.\d+)?/g)||[]).length,x=/!/.test(t),j=/\bx[GT]\b|xG|xT|index|phase/i.test(t);return[`${t.split(/\s+/).length} words`,`${n} number${n===1?"":"s"}`,j?"uses metrics":"no jargon",x?"exclamatory":"calm"];};
  $("pvbody").innerHTML=`<h2>Same moment, three viewers</h2><p class="cap">${e.minute}' · ${esc(e.type)}${e.player?" · "+esc(e.player):""}. One event, one set of verified facts; the Personalise agent writes it for each viewer.</p>
  <div class="pvg">${Object.entries(W).map(([k,[ic,n,dd]])=>{const c=d0(d.modes[k]);return `<div class="pvc${k===opt.mode?" me":""}"><div class="pvh">${ic} <b>${n}</b> <span class="muted">${dd}</span></div><div class="pvt">${esc(c.title)}</div><p>${esc(c.text)}</p><div class="pvtr">${traits(c.text||"").map(t=>`<span class="chip">${t}</span>`).join("")}</div><small class="muted">${esc(c.source)}</small></div>`;}).join("")}</div>`;}
 catch(e){$("pvbody").innerHTML='<p class="muted">Could not load the three views right now.</p>';}}
const d0=x=>x||{title:"—",text:"",source:"not available"};
// ------------------------------------------------------------------ v12: ask with tools (visible tool calls + pitch highlights)
function drawQ(now){if(!S.qhl||S.qhl.until<now)return;const a=Math.min(1,(S.qhl.until-now)/1500);cx.globalAlpha=a;
 S.qhl.items.forEach(h=>{const[x,y]=P(h.team,h.x,h.y),c=col(h.team);
  if(h.kind==="pass"&&h.end_x!=null){const b=P(h.team,h.end_x,h.end_y);cx.strokeStyle=c;cx.lineWidth=3;cx.setLineDash(h.ok?[]:[8,8]);cx.beginPath();cx.moveTo(x,y);cx.lineTo(...b);cx.stroke();cx.setLineDash([]);cx.fillStyle=c;cx.beginPath();cx.arc(b[0],b[1],5,0,7);cx.fill();}
  else if(h.kind==="shot"){cx.lineWidth=4;cx.strokeStyle="#ffc83d";cx.fillStyle=c+"99";if(h.goal){cx.fillStyle="#ffc83d";star(cx,x,y,22);}else{cx.beginPath();cx.arc(x,y,10+60*(h.xg||0),0,7);cx.fill();cx.stroke();}}
  else{cx.strokeStyle="#ffc83d";cx.lineWidth=5;cx.beginPath();cx.arc(x,y,22,0,7);cx.stroke();}
  if(h.label&&S.qhl.items.length<=12){cx.font="700 18px system-ui";const w=cx.measureText(h.label).width,lx=Math.min(Math.max(x-w/2,8),1040-w-8),ly=y>60?y-28:y+44;cx.fillStyle="#0a0e16d8";cx.fillRect(lx-5,ly-17,w+10,24);cx.fillStyle="#ffc83d";cx.fillText(h.label,lx,ly);}});
 cx.globalAlpha=1;cx.font="800 20px system-ui";const t=`🔎 ${S.qhl.q}`.slice(0,70),w=cx.measureText(t).width;cx.fillStyle="#0a0e16d8";cx.beginPath();cx.roundRect(1040-w-24,60,w+16,32,8);cx.fill();cx.fillStyle="#ffc83d";cx.fillText(t,1040-w-16,83);}
// ------------------------------------------------------------------ v12: accessibility (colour-blind palette, keyboard, announcements)
const CB={home:"#0072B2",away:"#E69F00"};let ORIG=null;
function applyPalette(){if(!meta)return;if(!ORIG)ORIG={h:meta.home.color,a:meta.away.color};const on=isOn("cvd");meta.home.color=on?CB.home:ORIG.h;meta.away.color=on?CB.away:ORIG.a;
 document.documentElement.style.setProperty("--home",meta.home.color);document.documentElement.style.setProperty("--away",meta.away.color);document.body.classList.toggle("cvd",on);
 if(S.report){renderStats(S.report);drawMomentum(S.report);}drawWin();if($("p-tactics").classList.contains("on"))loadTactics();}
function announce(t){const r=$("sr");r.textContent="";setTimeout(()=>r.textContent=t,30);}
function describeNow(){const t=`${$("clock").textContent} ${$("period").textContent}. ${meta?scoreline(S.score):""}. ${$("nowt").textContent}`;announce(t);if("speechSynthesis" in window){speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(t);u.lang={en:"en-GB",es:"es-ES",fr:"fr-FR"}[opt.lang];speechSynthesis.speak(u);}}
document.addEventListener("keydown",e=>{const tag=(e.target.tagName||"").toLowerCase();if(["input","select","textarea"].includes(tag))return;
 if(e.key==="Escape"){if(R.on)reelExit();$("pv").classList.remove("on");$("ft").classList.remove("on");$("help").classList.remove("on");tourEnd();return;}
 if(R.on){if(e.key==="ArrowRight"){startClip(R.ci+1);e.preventDefault();}else if(e.key==="ArrowLeft"){startClip(R.ci-1);e.preventDefault();}else if(e.key===" "){R.paused=!R.paused;e.preventDefault();}return;}
 if(e.ctrlKey||e.metaKey||e.altKey)return;
 const k=e.key.toLowerCase();if(k===" "&&tag!=="button"){if(!$("pause").disabled)$("pause").click();e.preventDefault();}
 else if(k==="b")reel("best");else if(k==="k")$("go").click();else if(k==="d")describeNow();else if(k==="v")perspectives();else if(k==="?")$("help").classList.add("on");else if(k==="c"){$("cvd").click();}
 else if(k==="/"){tab("ask");$("q").focus();e.preventDefault();}});
// tabs: ARIA + arrow keys
(function(){const tl=$("tabs");tl.setAttribute("role","tablist");tl.setAttribute("aria-label","Match panels");tl.querySelectorAll("button").forEach(b=>{b.setAttribute("role","tab");b.setAttribute("aria-controls","p-"+b.dataset.p);b.id="t-"+b.dataset.p;});
 document.querySelectorAll(".pane").forEach(p=>{p.setAttribute("role","tabpanel");p.setAttribute("aria-labelledby","t-"+p.id.slice(2));p.tabIndex=0;});
 tl.addEventListener("keydown",e=>{if(!["ArrowRight","ArrowLeft","Home","End"].includes(e.key))return;const bs=[...tl.querySelectorAll("button")],i=bs.indexOf(document.activeElement);if(i<0)return;
  const j=e.key==="Home"?0:e.key==="End"?bs.length-1:(i+(e.key==="ArrowRight"?1:-1)+bs.length)%bs.length;bs[j].focus();tab(bs[j].dataset.p);e.preventDefault();});})();
// ------------------------------------------------------------------ v12: 30-second guided tour
const TOUR=[["#match","Pick a match","240 synthetic league matches plus 5 showcase friendlies. Every club and player is fictional."],
 ["#mode","Who is watching?","Fan, neutral or analyst. The Personalise agent rewrites every line for that viewer. Press 👥 to compare all three on the same moment."],
 ["#best","Short on time?","Best moments plays the goals and big chances on the pitch with AI captions, in about a minute."],
 ["#go","Or watch the whole match","Pitch, score, timeline and commentary all run on one clock. The AI room upgrades lines as they pass its checks (✦)."],
 ['#tabs [data-p="ask"]',"Ask with tools","Type “show me all shots by …”. An agent plans tool calls, runs them on the event data and highlights the answer on the pitch."],
 ['#tabs [data-p="agents"]',"Inside the AI room","Five agents hand work to each other. Press 💥 Break it to crash one and watch the orchestrator recover."]];
let TI=-1;
function tour(){TI=0;tourShow();}
function tourShow(){const[sel,ti,tx]=TOUR[TI],el=document.querySelector(sel);if(!el){return tourNext();}const r=el.getBoundingClientRect(),hl=$("tourhl"),tip=$("tourtip");
 hl.style.cssText=`display:block;left:${r.left-5}px;top:${r.top-5}px;width:${r.width+10}px;height:${r.height+10}px`;
 tip.innerHTML=`<div class="muted" style="font-size:.8em">${TI+1} / ${TOUR.length}</div><b>${ti}</b><p>${tx}</p><div style="display:flex;gap:6px;justify-content:flex-end"><button class="btn ghost" id="tskip">Skip</button>${TI===2?'<button class="btn ghost" id="ttry">✨ Try it</button>':""}<button class="btn" id="tnext">${TI===TOUR.length-1?"Done":"Next →"}</button></div>`;
 tip.style.display="block";const tw=Math.min(320,innerWidth-20);tip.style.width=tw+"px";tip.style.left=Math.max(10,Math.min(r.left,innerWidth-tw-10))+"px";tip.style.top=(r.bottom+14+200>innerHeight?Math.max(10,r.top-tip.offsetHeight-14):r.bottom+14)+"px";
 $("tnext").onclick=tourNext;$("tskip").onclick=tourEnd;if($("ttry"))$("ttry").onclick=()=>{tourEnd();reel("best");};$("tnext").focus();announce(`${ti}. ${tx}`);}
function tourNext(){TI++;if(TI>=TOUR.length)return tourEnd();tourShow();}
function tourEnd(){TI=-1;$("tourhl").style.display="none";$("tourtip").style.display="none";localStorage.itgTour="done";}
addEventListener("resize",()=>{if(TI>=0)tourShow();});
// wiring
$("best").onclick=()=>reel("best");$("tourbtn").onclick=tour;$("pvbtn").onclick=()=>perspectives();$("pvclose").onclick=()=>$("pv").classList.remove("on");
$("reelx").onclick=reelExit;$("reelprev").onclick=()=>startClip(R.ci-1);$("reelnext").onclick=()=>startClip(R.ci+1);$("reelpp").onclick=()=>{R.paused=!R.paused;$("reelpp").textContent=R.paused?"▶":"⏸";};$("reelcard").onclick=recapCard;
tog("cvd",0,()=>{applyPalette();localStorage.itgCvd=isOn("cvd")?"1":"";});$("helpbtn").onclick=()=>$("help").classList.add("on");
if(localStorage.itgCvd){$("cvd").classList.add("on");document.body.classList.add("cvd");}
if(!localStorage.itgTour&&!/notour/.test(location.search)){let tw=0;const tt=()=>{if(TI>=0||R.on||localStorage.itgTour)return;if(meta)tour();else if((tw+=400)<20000)setTimeout(tt,400);};setTimeout(tt,1200);}
