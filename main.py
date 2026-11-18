import ipaddress
import json
import os
import socket
from urllib.parse import urlparse

import httpx
import trafilatura
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Article Research Reader")
MAX_BYTES = 3_000_000

class Request(BaseModel):
    url: str

def validate_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400, "Enter a valid public HTTP(S) URL.")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in ("localhost",) or hostname.endswith((".localhost", ".local", ".internal")):
        raise HTTPException(400, "Local network addresses are not supported.")
    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError()
    except (socket.gaierror, ValueError):
        raise HTTPException(400, "URL must resolve to a public internet address.")
    return url.strip()

@app.post("/api/extract")
async def extract(req: Request):
    url = validate_url(req.url)
    try:
        # Disable redirects to avoid following a URL into private network destinations.
        async with httpx.AsyncClient(follow_redirects=False, timeout=15, headers={"User-Agent": "ArticleResearchReader/1.0 (text extraction for accessible pages)"}) as client:
            async with client.stream("GET", url) as response:
                if 300 <= response.status_code < 400:
                    raise HTTPException(422, "This URL redirects. Please paste the final article URL.")
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type", ""):
                    raise HTTPException(422, "This URL does not serve an HTML page.")
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, "Page is too large to process.")
                    chunks.append(chunk)
        html = b"".join(chunks).decode("utf-8", errors="replace")
        result = trafilatura.bare_extraction(html, url=url, with_metadata=True, include_comments=False, include_tables=True, favor_precision=True)
        if not result or not result.text or len(result.text.strip()) < 100:
            raise HTTPException(422, "No accessible article text was found. The page may require login, payment, or JavaScript rendering.")
        markdown = trafilatura.extract(html, url=url, output_format="markdown", include_comments=False, include_tables=True, favor_precision=True) or result.text
        return {"title": result.title or "Untitled article", "author": result.author or "", "date": result.date or "", "site": result.sitename or urlparse(url).hostname, "url": url, "text": result.text, "markdown": markdown}
    except httpx.HTTPError:
        raise HTTPException(502, "Could not retrieve that page. Try a different public article URL.")

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#101827"><title>Article Research Reader</title>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;color-scheme:dark;background:#0b1220;color:#f2f5fa}*{box-sizing:border-box}body{margin:0}main{max-width:760px;margin:auto;padding:28px 18px 90px}h1{font-size:clamp(27px,7vw,38px);margin:0 0 7px}p.muted{color:#a7b4c8;margin:0 0 25px;line-height:1.5}.panel{background:#162235;border:1px solid #2d3c51;border-radius:18px;padding:18px;margin-bottom:20px}label{font-weight:700;display:block;margin-bottom:9px}input{width:100%;border-radius:12px;border:1px solid #4b5e76;background:#0c1727;color:white;font-size:16px;padding:15px;outline-offset:3px}button{min-height:48px;border:0;border-radius:12px;padding:12px 17px;font-weight:750;font-size:15px;cursor:pointer;background:#9bdbff;color:#071321}button.secondary{background:#2a3b52;color:#f5f7fb}button:disabled{opacity:.6;cursor:wait}.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}.status{min-height:24px;color:#c9d5e6;margin-top:13px;line-height:1.5}.error{color:#ffb4b4}.article{display:none}.article h2{font-size:clamp(24px,6vw,34px);line-height:1.18;margin:0 0 12px}.meta{color:#a9bdd1;font-size:14px;line-height:1.6;margin-bottom:18px}.reading{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.75;font-size:17px;color:#f1f3f8}.small{font-size:13px;color:#99a8bc;line-height:1.6}.sites{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.site{font-size:13px;padding:8px 10px;border-radius:10px;background:#273a51;color:#e5edf7;border:0;min-height:38px}a{color:#9bdbff}footer{margin-top:24px}
</style></head><body><main><h1>Article Research Reader</h1><p class="muted">Read accessible articles without clutter. Export clean Markdown with source attribution.</p>
<section class="panel"><form id="form"><label for="url">Article URL</label><input id="url" type="url" placeholder="https://example.com/article" autocomplete="url" inputmode="url" required><div class="actions"><button id="extract" type="submit">Extract article</button><button id="saveSite" type="button" class="secondary">Save website</button></div></form><div id="status" class="status" role="status" aria-live="polite"></div><div id="sites" class="sites"></div></section>
<section id="article" class="panel article"><h2 id="title"></h2><div class="meta" id="meta"></div><div class="actions"><button id="download">Download Markdown</button><button id="copy" class="secondary">Copy Markdown</button><button id="source" class="secondary">Original source ↗</button></div><hr style="border:0;border-top:1px solid #34465c;margin:22px 0"><div class="reading" id="reading"></div></section>
<footer class="small">Only publicly accessible HTML is extracted. This reader does not log in, defeat access controls, or retrieve subscriber-only content. Saved website names remain on this device.</footer></main>
<script>
const $=id=>document.getElementById(id);let current=null;
const safe=(s)=>String(s||'').replace(/[\\<>]/g,'');
const slug=s=>s.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,70)||'article';
const sites=()=>{try{return JSON.parse(localStorage.getItem('reader-sites')||'[]')}catch{return []}};
function renderSites(){const root=$('sites');root.replaceChildren();sites().forEach(host=>{const b=document.createElement('button');b.type='button';b.className='site';b.textContent=host+' ×';b.title='Remove saved website';b.onclick=()=>{localStorage.setItem('reader-sites',JSON.stringify(sites().filter(x=>x!==host)));renderSites()};root.appendChild(b)})}
$('saveSite').onclick=()=>{try{const u=new URL($('url').value);if(!['https:','http:'].includes(u.protocol))throw Error();const a=[...new Set([...sites(),u.hostname])].slice(-20);localStorage.setItem('reader-sites',JSON.stringify(a));renderSites();$('status').textContent='Website saved on this device.'}catch{$('status').textContent='Paste a valid article URL first.'}};
function buildMarkdown(a){return `# ${a.title}\n\n${a.author?'**Author:** '+a.author+'\n':''}${a.date?'**Date:** '+a.date+'\n':''}**Source:** ${a.site}\n**Original URL:** ${a.url}\n\n---\n\n${a.markdown}\n`}
$('form').onsubmit=async e=>{e.preventDefault();$('extract').disabled=true;$('status').className='status';$('status').textContent='Extracting article…';$('article').style.display='none';current=null;try{const r=await fetch('/api/extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:$('url').value})});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Could not extract article.');current=data;$('title').textContent=data.title;$('meta').textContent=[data.site,data.author,data.date].filter(Boolean).join(' · ');$('reading').textContent=data.text;$('article').style.display='block';$('status').textContent='Article ready.'}catch(err){$('status').className='status error';$('status').textContent=err.message}finally{$('extract').disabled=false}};
$('download').onclick=()=>{if(!current)return;const blob=new Blob([buildMarkdown(current)],{type:'text/markdown;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=slug(current.title)+'.md';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)};
$('copy').onclick=async()=>{if(!current)return;try{await navigator.clipboard.writeText(buildMarkdown(current));$('status').textContent='Markdown copied.'}catch{$('status').textContent='Clipboard unavailable; use Download Markdown.'}};
$('source').onclick=()=>{if(current)window.open(current.url,'_blank','noopener,noreferrer')};renderSites();
</script></body></html>'''
