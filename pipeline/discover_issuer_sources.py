"""Discover official issuer source candidates; never auto-approve relationships.

Seed URLs are discovery hints, not proof of publisher identity. Cached HTML and
text belong under ignored outputs only. Verify issuer, actual counterparties,
relationship semantics and date before adding facts to official_relations.json.
Requires pipeline/requirements-audit.txt. Resume by using the same --out.
"""
import requests,json,hashlib,re,time,sys,argparse,unicodedata
from datetime import date
import truststore
truststore.inject_into_ssl()
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--out',type=str,default='outputs/issuer-source-research')
ap.add_argument('--seeds',default='pipeline/ir_crawl/data/sample_urls.json')
ap.add_argument('--companies',default='public/M4_companies.json')
ap.add_argument('--limit',type=int,default=100000)
ap.add_argument('--pages',type=int,default=12)
ap.add_argument('--workers',type=int,default=8)
args=ap.parse_args()
from pathlib import Path
from urllib.parse import urljoin,urlsplit,urldefrag
from concurrent.futures import ThreadPoolExecutor,as_completed
from bs4 import BeautifulSoup
out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
companies=json.load(open(args.companies))['companies']
seeds=[x for x in json.load(open(args.seeds)) if x['code'] in companies and 'jpx.co.jp' not in x['url']]
limit=args.limit
def same_host(host,root):
 return bool(host) and (host==root or host.endswith('.'+root))
kw=re.compile(r'大株主|株式の状況|株主構成|株式情報|株式概要|株式概況|株主・株式|役員一覧|役員紹介|取締役|会社概要|株主・投資家|投資家情報|株主情報|株式基本|/stock|/shareholder|/officer|/director|/ir/?$|/investors/?$',re.I)
strong=re.compile(r'大株主|株主構成|株式の状況|役員一覧|役員紹介|取締役|/stock|/officer|/director',re.I)
def run(seed):
 folder=out/seed['code'];folder.mkdir(exist_ok=True)
 report=folder/'pages.json'
 if report.exists():return json.load(open(report))
 queue=[seed['url']];seen=set();pages=[];root=None
 for _ in range(args.pages):
  if not queue:break
  u=queue.pop(0)
  if u in seen:continue
  seen.add(u)
  try:
   resp=requests.get(u,timeout=(6,12),headers={'User-Agent':'JP-Market-Vis-primary-source-research/1.0'})
   if resp.status_code!=200 or len(resp.content)>5000000:continue
   if root is None:root=urlsplit(resp.url).hostname.removeprefix('www.')
   if not same_host(urlsplit(resp.url).hostname,root):continue
   soup=BeautifulSoup(resp.content,'html.parser')
   for x in soup(['script','style','noscript']):x.decompose()
   text=soup.get_text(' ',strip=True);key=hashlib.sha256(u.encode()).hexdigest()[:20]
   (folder/(key+'.html')).write_bytes(resp.content)
   (folder/(key+'.txt')).write_text(text)
   tables=[t.get_text(' | ',strip=True) for t in soup.select('table') if re.search('大株主|株主名|所有株式数|持株数',t.get_text())]
   pages.append({'url':resp.url,'title':soup.title.get_text(strip=True) if soup.title else None,'key':key,'sha256':hashlib.sha256(resp.content).hexdigest(),'has_stock_table':bool(tables),'table_count':len(tables),'text_length':len(text),'issuer_name_present':seed['name'] in text,'checked_at':date.today().isoformat()})
   links=[]
   for a in soup.select('a[href]'):
    v=urldefrag(urljoin(resp.url,a['href']))[0];t=a.get_text(' ',strip=True)
    if urlsplit(v).scheme not in ['https','http'] or not same_host(urlsplit(v).hostname,root):continue
    if re.search(r'\.(pdf|zip|xls|xlsx)(?:\?|$)',v,re.I):continue
    if v not in seen and v not in queue and kw.search(t+' '+v):links.append((not bool(strong.search(t+' '+v)),v))
   queue=[v for _,v in sorted(set(links))]+queue
   time.sleep(.3)
  except Exception:continue
 result={'code':seed['code'],'name':seed['name'],'pages':pages}
 report.write_text(json.dumps(result,ensure_ascii=False,indent=1));return result
results=[]
with ThreadPoolExecutor(max_workers=args.workers) as pool:
 for i,f in enumerate(as_completed([pool.submit(run,s) for s in seeds[:limit]]),1):
  r=f.result();results.append(r)
  if i%20==0:print(i,'issuers',sum(any(p['has_stock_table'] for p in x['pages']) for x in results),'with stock tables',flush=True)
(out/'index.json').write_text(json.dumps(results,ensure_ascii=False,indent=1))
