"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
let groups=0;function check(name,run){run();groups++;console.log("PASS "+name);}
class Element{
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.style={};this.attributes={};this.listeners={};this.className="";this._text="";this.classList={add:(c)=>this.className+=" "+c};}
  set textContent(value){this.children=[];this._text=String(value);}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join("");}
  append(...nodes){nodes.forEach(n=>{if(typeof n==="string")n=new Text(n);n.parentElement=this;this.children.push(n);});}
  replaceChildren(...nodes){this._text="";this.children=[];this.append(...nodes);}
  replaceWith(node){const list=this.parentElement.children;list[list.indexOf(this)]=node;node.parentElement=this.parentElement;this.parentElement=null;}
  setAttribute(k,v){this.attributes[k]=String(v);}
  getAttribute(k){return this.attributes[k]??null;}
  addEventListener(k,fn){(this.listeners[k]??=[]).push(fn);}
  matches(selector){if(selector===":popover-open")return this.open===true;return selector.split(",").some(s=>s[0]==="."?this.className.split(/\s+/).includes(s.slice(1)):s==="[data-repeat-glossary]"?Boolean(this.dataset.repeatGlossary):this.tagName===s.toUpperCase());}
  closest(selector){for(let n=this;n;n=n.parentElement)if(n.matches?.(selector))return n;return null;}
  querySelectorAll(selector){const out=[];for(const n of this.children){if(n.matches?.(selector))out.push(n);if(n.querySelectorAll)out.push(...n.querySelectorAll(selector));}return out;}
  get cellIndex(){return this.parentElement.children.indexOf(this);}
  get isConnected(){return Boolean(this.closest("body"));}
  getBoundingClientRect(){return {left:100,top:100,bottom:120,width:420,height:200};}
  contains(node){return node===this||this.children.some(n=>n.contains?.(node));}
  focus(){document.activeElement=this;}
  showPopover(){this.open=true;}
  hidePopover(){this.open=false;}
  click(){const event={preventDefault(){},stopPropagation(){this.stopped=true;}};for(const fn of this.listeners.click||[])fn(event);this.onclick?.(event);return event;}
}
class Text{constructor(text){this.textContent=text;}}
const document={body:new Element("body"),activeElement:null,createElement:tag=>new Element(tag),createElementNS:(ns,tag)=>{const n=new Element(tag);n.namespaceURI=ns;return n;},createTextNode:s=>new Text(s),addEventListener(){},querySelectorAll:s=>document.body.querySelectorAll(s)};
const window={addEventListener(){},VizData:{element:(tag,cls="",text)=>{const n=new Element(tag);n.className=cls;if(text!==undefined)n.textContent=text;return n;}}};
const context={window,document,innerWidth:1366,innerHeight:768,queueMicrotask};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,"../js/glossary.js"),"utf8"),context);vm.runInContext(fs.readFileSync(path.join(__dirname,"../js/glossary_view.js"),"utf8"),context);const G=window.GlossaryUI;
check("native term button, no icon markup",()=>{const b=G.label("hit","hits");assert.equal(b.tagName,"BUTTON");assert.equal(b.type,"button");assert.ok(b.className.includes("glossary-link"));assert.equal(b.textContent,"hits");assert.ok(!b.textContent.includes("?"));assert.equal(b.children.length,0);});
check("first occurrence per paragraph, reversible with one option",()=>{const p=new Element("p");document.body.append(p);p.append(G.label("hit","hits"),new Text(" and "),G.label("hit","hits"),new Text(" and "),G.label("hit","hits"));G.refresh();assert.equal(p.querySelectorAll(".glossary-link").length,1);assert.equal(p.textContent,"hits and hits and hits");window.GLOSSARY_LINK_FIRST_ONLY_PER_BLOCK=false;G.refresh();assert.equal(p.querySelectorAll(".glossary-link").length,3);window.GLOSSARY_LINK_FIRST_ONLY_PER_BLOCK=true;G.refresh();assert.equal(p.querySelectorAll(".glossary-link").length,1);});
check("table headers and first columns stay linked; other cells deduplicate",()=>{const table=new Element("table"),head=new Element("thead"),hr=new Element("tr"),th=new Element("th"),body=new Element("tbody"),row=new Element("tr"),first=new Element("td"),second=new Element("td");document.body.append(table);table.append(head,body);head.append(hr);hr.append(th);body.append(row);row.append(first,second);for(const cell of [th,first,second])cell.append(...[1,2,3].map(()=>G.label("hit","hits")));G.refresh();assert.equal(th.querySelectorAll(".glossary-link").length,3);assert.equal(first.querySelectorAll(".glossary-link").length,3);assert.equal(second.querySelectorAll(".glossary-link").length,1);});
check("one popover, content retained, focus restored",()=>{const a=G.label("hit","hits"),b=G.label("budget","budget");document.body.append(a,b);a.click();assert.equal(document.querySelectorAll(".glossary-popover").length,1);assert.equal(a.getAttribute("aria-expanded"),"true");b.click();assert.equal(a.getAttribute("aria-expanded"),"false");assert.equal(b.getAttribute("aria-expanded"),"true");G.close();assert.equal(document.activeElement,b);});
check("sort label and arrow are independent native buttons",()=>{const th=new Element("th");document.body.append(th);let sorts=0;G.sortHeader(th,"hit","Hits",()=>sorts++);th.children[0].click();assert.equal(sorts,0);th.children[1].click();assert.equal(sorts,1);th.onclick();assert.equal(sorts,2);G.close();});
check("SVG glossary labels also contain a native button",()=>{const node=document.createElementNS("svg","text");node.textContent="Relevance";node.setAttribute("x",30);node.setAttribute("y",20);const group=G.svgHelp(node,"score_relevance");assert.equal(group.querySelectorAll(".glossary-link")[0].tagName,"BUTTON");assert.equal(group.textContent,"Relevance");});
function rgb(value){let h=value.replace("#","");if(h.length===3||h.length===4)h=h.split("").map(c=>c+c).join("");return [0,2,4].map(i=>parseInt(h.slice(i,i+2),16)).concat(h.length===8?parseInt(h.slice(6,8),16)/255:1);}
function luminosity(c){const a=c.slice(0,3).map(v=>{const s=v/255;return s<=.04045?s/12.92:((s+.055)/1.055)**2.4;});return .2126*a[0]+.7152*a[1]+.0722*a[2];}
function contrast(a,b){const x=luminosity(a),y=luminosity(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
check("blue links pass 4.5:1 on every dark/light text surface and state overlay",()=>{
  const css=fs.readFileSync(path.join(__dirname,"../css/style.css"),"utf8"),dark=css.match(/:root\{([^}]+)\}/)[1],light=css.match(/:root\[data-theme="light"\]\{([^}]+)\}/)[1],vars=text=>Object.fromEntries([...text.matchAll(/(--[\w-]+):([^;]+)/g)].map(m=>[m[1],m[2]]));
  for(const [theme,values] of [["dark",vars(dark)],["light",{...vars(dark),...vars(light)}]]){
    const link=rgb(values["--glossary-link"]),bases=["--bg","--panel","--surface","--canvas","--input","--line"].map(k=>rgb(values[k])),colors=[...bases];
    for(const match of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)){
      // Filled bars and the six-pixel connection dot are decorations, never text backgrounds.
      if(/bar-fill|bar-track|offline-badge i/.test(match[1]))continue;
      for(const b of match[2].matchAll(/background(?:-color)?:([^;}]+)/g)){
        const v=b[1].trim(),resolved=v.startsWith("var(")?values[v.slice(4,-1)]:v;if(!resolved?.startsWith("#"))continue;
        const color=rgb(resolved);if(color[3]===1)colors.push(color);else for(const base of bases)colors.push(color.slice(0,3).map((v,i)=>v*color[3]+base[i]*(1-color[3])));
      }
    }
    const minimum=Math.min(...colors.map(bg=>contrast(link,bg)));assert.ok(minimum>=4.5,theme+" contrast "+minimum);console.log(`CONTRAST ${theme}: minimum ${minimum.toFixed(2)}:1 across ${colors.length} text backgrounds`);
  }
});
console.log(`Glossary view: ${groups} groups passed.`);
