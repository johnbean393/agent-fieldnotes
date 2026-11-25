'use strict';

if (document.documentElement.classList.contains('layout-compact')) {
  const sections = [...document.querySelectorAll('main > section[id]')];
  const links = [...document.querySelectorAll('header nav a')];
  function showSection() {
    const target = document.getElementById(location.hash.slice(1));
    const section = target?.closest('main > section[id]') || sections[0];
    for (const el of sections) el.hidden = el !== section;
    for (const link of links) {
      if (link.hash === '#' + section.id) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
    for (let parent=target?.parentElement; parent; parent=parent.parentElement) {
      if (parent.tagName==='DETAILS') parent.open=true;
    }
    window.dispatchEvent(new Event('resize'));
    if (!target || target === section) window.scrollTo(0, 0);
    else target.scrollIntoView();
  }
  addEventListener('hashchange', showSection);
  showSection();
}

function node(tag, text, cls) {
  const element = document.createElement(tag);
  if (text != null) element.textContent = text;
  if (cls) element.className = cls;
  return element;
}
const formatValue = (v, digits=1) => new Intl.NumberFormat('en-US', {maximumFractionDigits:digits}).format(v);
const paint = ['var(--accent)','var(--claude)','var(--cursor)','var(--zcode)'];
const seriesColor = i => paint[i] ?? ['#ad6b30','#6654a4','#1e7967','#8f4d83'][i % 4];

function renderBars(target, rows, maximum) {
  const view = node('div', null, 'native-bars');
  for (const {label, segments, value} of rows) {
    const row = node('div', null, 'native-bar-row');
    const track = node('div', null, 'native-track');
    for (const [i, portion] of segments.entries()) {
      const fill = node('div', null, 'native-fill');
      fill.style.width = 100 * portion / maximum + '%';
      fill.style.background = seriesColor(i);
      track.append(fill);
    }
    row.append(node('span', label), track, node('span', value, 'tabular'));
    view.append(row);
  }
  target.append(view);
}

function renderGraph(target, labels, series, suffix='', waterfall=false) {
  const box = node('div', null, 'chart chart-inline');
  target.append(box);
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns,'svg');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Chart. Exact values are in Sources and data.');
  box.append(svg);
  function item(tag,attrs,text) {
    const element=document.createElementNS(ns, tag);
    for (const [k,v] of Object.entries(attrs)) element.setAttribute(k,v);
    if (text != null) element.textContent=text;
    svg.append(element);
    return element;
  }
  const draw = () => {
    const w = box.clientWidth;
    if (w < 120) return;
    svg.replaceChildren();
    const h=200, left=40, top=12, right=12, bottom=27;
    const stacked = !waterfall && series.every(s=>!s.line);
    const bounds = stacked ? labels.map((_,i)=>series.reduce((sum,s)=>sum+(s.values[i]||0),0)) :
      series.flatMap(s=>s.values.filter(v=>v!=null));
    const rawMax = Math.max(1, ...bounds);
    const max = Math.ceil(rawMax/4)*4;
    const x = i => left + (w-left-right)*(i+.5)/labels.length;
    const y = v => h-bottom - v*(h-top-bottom)/max;
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    for(let i=0;i<=4;i++){
      const v=max*i/4;
      item('line',{x1:left,x2:w-right,y1:y(v),y2:y(v)});
      item('text',{x:left-6,y:y(v)+4,'text-anchor':'end'},formatValue(v)+(i===4?suffix:''));
    }
    labels.forEach((label,i)=>{
      if (labels.length>6 && w<480 && i%2 && i!==labels.length-1) return;
      item('text',{x:x(i),y:h-7,'text-anchor':'middle'},label);
    });
    if (waterfall) {
      let previous=0;
      for (const [i,value] of series[0].values.entries()) {
        const end = i===0||i===labels.length-1 ? value : previous+value;
        const start = i===0||i===labels.length-1 ? 0 : previous;
        const width=Math.min(64,(w-left-right)/labels.length*.65);
        const rect=item('rect',{x:x(i)-width/2,y:y(Math.max(start,end)),width,height:Math.abs(y(start)-y(end)),fill:i===0||i===labels.length-1?seriesColor(0):seriesColor(1),rx:2});
        const tip=document.createElementNS(ns,'title');tip.textContent=labels[i]+': '+formatValue(value)+suffix;rect.append(tip);
        previous=end;
      }
      return;
    }
    const isLine=series.some(s=>s.line);
    for (const [j,s] of series.entries()) {
      if (s.line) {
        const points=s.values.map((v,i)=>v==null?null:`${x(i)},${y(v)}`);
        for (let i=1;i<points.length;i++) if (points[i-1]&&points[i]) item('path',{d:`M${points[i-1]} L${points[i]}`,stroke:seriesColor(j),fill:'none','stroke-width':2});
      }
      for (const [i,v] of s.values.entries()) {
        if (v==null) continue;
        const barWidth=(w-left-right)/labels.length*.62;
        const start=isLine?0:series.slice(0,j).reduce((sum,row)=>sum+(row.values[i]||0),0);
        const mark=s.line?item('circle',{cx:x(i),cy:y(v),r:4,fill:seriesColor(j)}):item('rect',{x:x(i)-barWidth/2,y:y(start+v),width:barWidth,height:y(start)-y(start+v),fill:seriesColor(j)});
        const tip=document.createElementNS(ns,'title');tip.textContent=[labels[i],s.name,formatValue(v)+suffix].filter(Boolean).join(' · ');mark.append(tip);
      }
    }
  };
  new ResizeObserver(draw).observe(box);
  draw();
  if (series.length>1) {
    const legend=node('div',null,'legend');
    for (const [i,s] of series.entries()) {
      const label=node('span'),swatch=node('i',null,'swatch');
      swatch.style.background=seriesColor(i);label.append(swatch,document.createTextNode(s.name));legend.append(label);
    }
    target.append(legend);
  }
}

function renderPromptSchedule(target, rows, timezone) {
  const days = [...new Set(rows.map(row => row.Day))];
  const intervals = [...new Set(rows.map(row => row.Interval))];
  const peak = Math.max(1,...rows.map(row => row['Prompt records']));
  const shades = ['#edf2ef','#cbe9d3','#93d5a7','#50ad78','#20724a'];
  const wrap = node('div',null,'schedule-scroll');
  const grid = node('div',null,'schedule-grid');
  grid.setAttribute('role','img');
  grid.setAttribute('aria-label','Prompt activity by weekday and six-hour interval in '+timezone);
  grid.append(node('span',''));
  for (const interval of intervals) {
    grid.append(node('span',interval,'schedule-hour'));
  }
  for (const day of days) {
    grid.append(node('span',day.slice(0,3),'schedule-day'));
    for (const row of rows.filter(row => row.Day===day)) {
      const count = row['Prompt records'];
      const cell = node('span',null,'schedule-cell');
      const shade = count ? Math.ceil(4 * count / peak) : 0;
      cell.style.background = shades[shade];
      cell.title = `${day}, ${row.Interval} ${timezone} · ${formatValue(count,0)} prompt records`;
      grid.append(cell);
    }
  }
  wrap.append(grid);
  const legend = node('div',null,'schedule-key');
  legend.append(node('span','Fewer'));
  for (const color of shades) {
    const swatch = node('i',null,'swatch');
    swatch.style.background = color;
    legend.append(swatch);
  }
  legend.append(node('span','More'),node('span',timezone,'schedule-zone'));
  target.append(wrap,legend);
}

function chart(target, d) {
  const rows=d.rows;
  const axisNames = rows => rows.map(r=>r.Month ? new Date(r.Month+'T12:00:00Z').toLocaleDateString('en-US',{month:'short',timeZone:'UTC'}) : r.Period?.replace(' · partial','').replace(' 2026',''));
  const simple = (label,field,suffix='',max=null) => renderBars(target,rows.map(r=>({label:r[label],segments:[r[field]],value:formatValue(r[field])+suffix})),max??Math.max(...rows.map(r=>r[field])));
  if(d.id==='revision-breakdown-clear') simple('Revision type','Share (%)','%',100);
  if(d.id==='compaction-median-clear') simple('Context','Median minutes',' min');
  if(d.id==='overlap-clear') renderGraph(target,axisNames(rows),[{values:rows.map(r=>r['Overlap (%)'])}],'%');
  if(d.id==='dissatisfaction-trend-clear') renderGraph(target,axisNames(rows),[{line:true,values:rows.map(r=>r['Share (%)'])}],'%');
  if(d.id==='dissatisfaction-waterfall-clear') renderGraph(target,rows.map(r=>r.Step),[{values:rows.map(r=>r['Rate points'])}], '%',true);
  if(d.id==='tool-friction-clear'){
    const periods=[...new Set(rows.map(r=>r.Month))];
    const series=[...new Set(rows.map(r=>r.Measure))].map(name=>({name,line:true,values:periods.map(p=>rows.find(r=>r.Month===p&&r.Measure===name)?.['Adverse result (%)']??null)}));
    renderGraph(target,axisNames(periods.map(Month=>({Month}))),series,'%');
  }
  if(d.id==='request-progression-clear'){
    const groups=[...new Set(rows.map(r=>r['Opening request']))];
    renderBars(target,groups.map(label=>{const a=rows.filter(r=>r['Opening request']===label);return {label,segments:[a[0]['Share (%)']],value:formatValue(a[0]['Share (%)'])+'%'};}),100);
  }
  if(d.id==='token-composition-clear'){
    renderBars(target,rows.map(r=>({label:r.Period,segments:[r['Cached input']*100],value:formatValue(r['Cached input']*100)+'%'})),100);
  }
  if(d.id==='brief-followup-clear'){
    renderBars(target,rows.map(r=>({label:r.Population,segments:[r['Shorter count']],value:formatValue(100*r['Shorter count']/r.Conversations)+'%'})),rows[0].Conversations);
  }
  if(d.id==='prompt-clock-clear') renderPromptSchedule(target,rows,d.timezone || 'UTC');
}
fetch('/insights/data.json',{cache:'no-cache'}).then(r=>r.json()).then(data=>{
  const available = new Set(data.map(d=>d.id));
  for (const article of document.querySelectorAll('[data-insight]')) article.hidden = !available.has(article.id);
  for (const group of document.querySelectorAll('.insight-group')) group.hidden = !group.querySelector('article:not([hidden])');
  for(const d of data){
    const article=document.getElementById(d.id);
    if(!article)continue;
    article.prepend(node('h4',d.title));
    if (d.contextLabel) article.querySelector('h4').after(node('p',d.contextLabel,'muted insight-context'));
    if (d.coverageNote) article.append(node('p',d.coverageNote,'muted insight-exception'));
    chart(article.querySelector('.native-insight'),d);
    const sources=article.querySelector('.insight-source-content');
    sources.replaceChildren(node('p', d.description),node('p',d.source,'muted'));
    for(const line of [...d.definitions,...d.filters,...d.caveats]) sources.append(node('p',line,'muted'));
    const wrap=node('div',null,'table-wrap'),table=node('table'),head=node('thead'),body=node('tbody');
    const headings=node('tr');
    for(const key of d.columns) headings.append(node('th',key));
    head.append(headings);
    for(const data of d.rows){
      const row=node('tr');
      for(const key of d.columns) row.append(node('td',typeof data[key]==='number'?formatValue(data[key],3):data[key]??'—'));
      body.append(row);
    }
    table.append(head,body);wrap.append(table);sources.append(wrap);
  }
}).catch(()=>{for(const article of document.querySelectorAll('.native-insight')) article.textContent='Chart data unavailable.';});
