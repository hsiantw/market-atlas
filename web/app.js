const $ = id => document.getElementById(id);
const fmt = (n, digits=2) => n == null ? '\u2014' : Number(n).toLocaleString(undefined,{minimumFractionDigits:digits,maximumFractionDigits:digits});
const pct = n => n == null ? '\u2014' : `${n>=0?'+':''}${fmt(n)}%`;
let saved; try { saved = new Set(JSON.parse(localStorage.getItem('atlas.saved') || '[]')); } catch { saved = new Set(); }
let assets=[], selected=null, filter='All', period='1Y', rows=[], page=0, generation=0, plotted=[];
const escapeHTML = str => String(str ?? '').replace(/[&<>"']/g, x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
async function api(url){if(window.atlasApi)return window.atlasApi(url);const response=await fetch(url);const data=await response.json();if(!response.ok)throw Error(data.error||'Unable to load data');return data;}
function error(message=''){$('error').textContent=message;$('error').hidden=!message;}
function renderAssets(){
  const q=$('search').value.trim().toLowerCase();
  const visible=assets.filter(a=>(filter==='All'||filter===a.kind||filter==='Saved'&&saved.has(a.symbol))&&`${a.symbol} ${a.name}`.toLowerCase().includes(q));
  $('count').textContent=`${visible.length} ASSETS`;
  $('assets').innerHTML=visible.map(a=>`<button class="asset ${a.symbol===selected?.symbol?'active':''}" data-symbol="${escapeHTML(a.symbol)}" aria-pressed="${a.symbol===selected?.symbol}"><span class="mini-icon">${escapeHTML(a.symbol.slice(0,2))}</span><span class="asset-info"><strong>${escapeHTML(a.symbol)}${saved.has(a.symbol)?' \u2605':''}</strong><small>${escapeHTML(a.name)}</small></span><span class="asset-price">${fmt(a.close)}<small class="${a.change>=0?'positive':'negative'}">${pct(a.change)}</small></span></button>`).join('')||'<div class="no-results">No matching assets. Try another search or save an asset to your watchlist.</div>';
}
function updateSaved(){const yes=saved.has(selected.symbol);$('save').textContent=yes?'\u2605 Saved':'\u2606 Save asset';$('save').setAttribute('aria-pressed',yes);}
function setDates(){const end=selected.date;const start=new Date(end+'T12:00:00Z');if(period==='1M')start.setUTCMonth(start.getUTCMonth()-1);if(period==='6M')start.setUTCMonth(start.getUTCMonth()-6);if(period==='1Y')start.setUTCFullYear(start.getUTCFullYear()-1);if(period==='5Y')start.setUTCFullYear(start.getUTCFullYear()-5);$('end').value=end;$('start').value=period==='MAX'?'':start.toISOString().slice(0,10);}
async function select(symbol){
 selected=assets.find(a=>a.symbol===symbol);if(!selected)return;
 $('symbol').textContent=selected.symbol;$('name').textContent=selected.name;$('assetIcon').textContent=selected.symbol.slice(0,2);$('exchange').textContent=selected.exchange||selected.kind;$('price').textContent=fmt(selected.close);$('currency').textContent=selected.currency||'';$('chartCurrency').textContent=selected.currency||'';$('change').textContent=`${pct(selected.change)} vs previous session`;$('change').className='change '+(selected.change>=0?'positive':'negative');$('asof').textContent=`As of ${selected.date} \u00b7 Last completed daily bar \u00b7 Yahoo Finance`;updateSaved();renderAssets();if(period!=='CUSTOM')setDates();await loadHistory();
}
function query(){const q=new URLSearchParams({symbol:selected.symbol});if($('start').value)q.set('start',$('start').value);if($('end').value)q.set('end',$('end').value);return q;}
async function loadHistory(){
 const token=++generation;error();rows=[];render();$('rangeSummary').textContent='Loading daily records...';$('download').disabled=true;
 try{const result=await api('/api/history?'+query());if(token!==generation)return;rows=result;page=0;render();}catch(e){if(token===generation){error(e.message);$('rangeSummary').textContent='Could not load this date range.';}}
}
function render(){
 const key=$('metric').value;plotted=rows.filter(r=>r[key]!=null);const first=plotted[0]?.[key],last=plotted.at(-1)?.[key];const change=first?(last/first-1)*100:null;
 $('return').textContent=pct(change);$('return').className=change==null?'':change>=0?'positive':'negative';$('high').textContent=plotted.length?fmt(Math.max(...plotted.map(r=>r[key]))):'\u2014';$('low').textContent=plotted.length?fmt(Math.min(...plotted.map(r=>r[key]))):'\u2014';$('records').textContent=fmt(rows.length,0);$('rangeSummary').textContent=rows.length?`${rows[0].date} \u2014 ${rows.at(-1).date} \u00b7 ${fmt(rows.length,0)} daily records`:'No records in this range';$('legend').textContent=key==='close'?'Daily close':'Adjusted daily close';$('download').disabled=!rows.length;$('chartEmpty').hidden=!!plotted.length;renderTable();draw();
}
function renderTable(){const total=Math.ceil(rows.length/15);page=Math.max(0,Math.min(page,total-1));const portion=rows.slice().reverse().slice(page*15,page*15+15);$('rows').innerHTML=portion.map(r=>`<tr><td>${r.date}</td>${['open','high','low','close','adjusted_close'].map(k=>`<td>${fmt(r[k])}</td>`).join('')}<td>${fmt(r.volume,0)}</td></tr>`).join('')||'<tr><td colspan="7">No records available.</td></tr>';$('pageInfo').textContent=rows.length?`Showing ${page*15+1}\u2013${Math.min((page+1)*15,rows.length)} of ${fmt(rows.length,0)} records`:'0 records';$('prev').disabled=page===0;$('next').disabled=page+1>=total;}
function draw(hover=-1){
 const canvas=$('chart'),box=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;canvas.width=box.width*dpr;canvas.height=box.height*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);const w=box.width,h=box.height,left=7,right=70,top=15,bottom=28,pw=w-left-right,ph=h-top-bottom;if(!plotted.length||pw<=0)return;
 const key=$('metric').value,vals=plotted.map(r=>r[key]);let min=Math.min(...vals),max=Math.max(...vals);let span=max-min||Math.abs(max)*.02||1;min-=span*.08;max+=span*.08;span=max-min;const x=i=>left+i/Math.max(1,vals.length-1)*pw,y=v=>top+(max-v)/span*ph;
 ctx.font='10px Segoe UI';ctx.lineWidth=1;for(let i=0;i<5;i++){const py=top+i*ph/4;ctx.strokeStyle='#edf1e9';ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(w-right+5,py);ctx.stroke();ctx.fillStyle='#8a968b';ctx.fillText(fmt(max-i*span/4,max>1000?0:2),w-right+12,py+3);}
 const gradient=ctx.createLinearGradient(0,top,0,h-bottom);gradient.addColorStop(0,'rgba(89,153,104,.20)');gradient.addColorStop(1,'rgba(89,153,104,0)');ctx.beginPath();vals.forEach((v,i)=>i?ctx.lineTo(x(i),y(v)):ctx.moveTo(x(i),y(v)));ctx.lineTo(x(vals.length-1),h-bottom);ctx.lineTo(left,h-bottom);ctx.closePath();ctx.fillStyle=gradient;ctx.fill();ctx.beginPath();vals.forEach((v,i)=>i?ctx.lineTo(x(i),y(v)):ctx.moveTo(x(i),y(v)));ctx.strokeStyle='#367e5d';ctx.lineWidth=1.8;ctx.stroke();
 const ticks=w<500?3:5;for(let i=0;i<ticks;i++){const index=Math.round(i*(vals.length-1)/(ticks-1));ctx.fillStyle='#8a968b';ctx.textAlign=i===0?'left':i===ticks-1?'right':'center';ctx.fillText(w<500?plotted[index].date.slice(0,7):plotted[index].date,x(index),h-5);}ctx.textAlign='left';
 if(hover>=0){const px=x(hover),py=y(vals[hover]);ctx.setLineDash([3,4]);ctx.strokeStyle='#aabbb0';ctx.beginPath();ctx.moveTo(px,top);ctx.lineTo(px,h-bottom);ctx.stroke();ctx.setLineDash([]);ctx.beginPath();ctx.arc(px,py,4,0,Math.PI*2);ctx.fillStyle='#237b56';ctx.fill();}
}
$('chart').addEventListener('mousemove',event=>{if(!plotted.length)return;const bounds=$('chart').getBoundingClientRect(),x=event.clientX-bounds.left;const i=Math.max(0,Math.min(plotted.length-1,Math.round((x-7)/(bounds.width-77)*(plotted.length-1))));draw(i);const tip=$('tooltip');tip.textContent=`${plotted[i].date} \u00b7 ${fmt(plotted[i][$('metric').value])} ${selected.currency||''}`;tip.hidden=false;tip.style.left=Math.max(0,Math.min(x+14,bounds.width-tip.offsetWidth-5))+'px';tip.style.top='8px';});
$('chart').addEventListener('mouseleave',()=>{$('tooltip').hidden=true;draw();});new ResizeObserver(()=>draw()).observe($('chart'));
$('assets').addEventListener('click',event=>{const button=event.target.closest('[data-symbol]');if(button)select(button.dataset.symbol);});
$('search').addEventListener('input',renderAssets);
$('filters').addEventListener('click',event=>{if(!event.target.dataset.filter)return;filter=event.target.dataset.filter;[...$('filters').children].forEach(b=>b.classList.toggle('active',b.dataset.filter===filter));renderAssets();});
$('periods').addEventListener('click',event=>{if(!event.target.dataset.period||!selected)return;period=event.target.dataset.period;[...$('periods').children].forEach(b=>b.classList.toggle('active',b.dataset.period===period));setDates();loadHistory();});
$('apply').onclick=()=>{if(!selected)return;if($('start').value&&$('end').value&&$('start').value>$('end').value){error('Start date must be before the end date.');return;}period='CUSTOM';[...$('periods').children].forEach(b=>b.classList.remove('active'));loadHistory();};
$('metric').onchange=render;$('prev').onclick=()=>{page--;renderTable();};$('next').onclick=()=>{page++;renderTable();};
$('save').onclick=()=>{if(!selected)return;saved.has(selected.symbol)?saved.delete(selected.symbol):saved.add(selected.symbol);try{localStorage.setItem('atlas.saved',JSON.stringify([...saved]));}catch{}updateSaved();renderAssets();};
$('download').onclick=()=>{
 if(!selected)return;
 if(!window.ATLAS_STATIC){window.location.href='/api/export?'+query();return;}
 const fields=['symbol','date','open','high','low','close','adjusted_close','volume','dividends','splits'];
 const cell=value=>'"'+String(value??'').replaceAll('"','""')+'"';
 const csv=[fields.join(','),...rows.map(row=>fields.map(key=>cell(key==='symbol'?selected.symbol:row[key])).join(','))].join('\r\n');
 const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=selected.symbol+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
document.addEventListener('keydown',event=>{if(event.key==='/'&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)){event.preventDefault();$('search').focus();}});
async function init(){try{error();$('refresh').disabled=true;assets=await api('/api/symbols');$('libraryCount').textContent=`\u00b7 ${assets.length} assets`;renderAssets();await select(selected?.symbol||'AAPL');}catch(e){error(e.message);}finally{$('refresh').disabled=false;}}
$('refresh').onclick=init;init();

