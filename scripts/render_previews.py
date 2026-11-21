"""Offline rendered captures using the actual HTML/CSS/JS and authenticated API snapshots.
These previews render the real frontend code with recorded backend fixtures because the
browser in this environment blocks all network navigation by system policy.
"""
import re,json,sys
from pathlib import Path
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from devflow.app import app
PREV=ROOT/'previews';PREV.mkdir(exist_ok=True)
CSS=re.sub(r'^@import[^\n]*\n', '', (ROOT/'static/style.css').read_text(), count=1)
JS=(ROOT/'static/app.js').read_text()
with TestClient(app) as c:
    r=c.post('/api/auth/login',json={'email':'demo@devflow.example.com','password':'DemoSeguro#2026'})
    assert r.status_code==200,r.text
    boot=c.get('/api/bootstrap').json();wid=boot['workspaces'][0]['id']
    data=c.get(f'/api/workspaces/{wid}/data').json()
    print('Grounded API fixture:',len(data['tasks']),'tasks,',len(data['projects']),'projects')

def make_html(path):
    raw=(ROOT/'templates'/path).read_text()
    raw=re.sub(r'<link rel="stylesheet"[^>]*>','',raw)
    raw=re.sub(r'<script src="/static/(app|auth).js" defer></script>','',raw)
    raw=raw.replace('</head>',f'<style>{CSS}</style><style>.reveal{{opacity:1!important;transform:none!important}}</style></head>')
    return raw

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
    errors=[]
    def shot_static(name,path,theme='light',width=1440,height=930,full=True):
        page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
        page.on('pageerror',lambda exc: errors.append((name,str(exc))))
        page.set_content(make_html(path),wait_until='domcontentloaded')
        page.evaluate('(t)=>document.documentElement.dataset.theme=t',theme)
        page.screenshot(path=str(PREV/(name+'.png')),full_page=full,animations='disabled',timeout=15000)
        print(name,'static rendered')
        page.close()
    shot_static('landing-claro','landing.html',full=True)
    shot_static('login-claro','auth.html',full=False)
    shot_static('landing-mobile','landing.html',width=390,height=844,full=True)
    def shot_app(name,view='overview',theme='light',width=1440,height=930,full=False,pid=0,task=False):
        page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
        page.on('pageerror',lambda exc: errors.append((name,str(exc))))
        page.set_content(make_html('app.html'),wait_until='domcontentloaded')
        page.evaluate('''(args)=>{
          const store={};Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>store[k]||null,setItem:(k,v)=>store[k]=v,removeItem:k=>delete store[k]}});
          Object.defineProperty(window,'sessionStorage',{configurable:true,value:{getItem:k=>null,setItem:(k,v)=>{},removeItem:k=>{}}});
          store['devflow-theme']=args.theme;
          window.fetch=(path,opts={})=>{
            const s=String(path);let data;
            if(s==='/api/bootstrap')data=args.boot;
            else if(s.includes('/data'))data=args.data;
            else if(s.includes('/tasks/')){let id=Number(s.split('/').pop());let tk=args.data.tasks.find(t=>t.id===id);data={task:tk,comments:[{id:1,body:'Deixei algumas observações no planejamento. Podemos revisar na próxima reunião?',user_id:args.data.members[1].id,created_at:new Date().toISOString()}],checklist:[{id:1,text:'Validar requisitos',checked:true},{id:2,text:'Implementar a solução',checked:false}]};}
            else data={ok:true};
            return Promise.resolve(new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}}));
          };
        }''',{'boot':boot,'data':data,'theme':theme})
        page.evaluate('(t)=>document.documentElement.dataset.theme=t',theme)
        page.add_script_tag(content=JS)
        
        try:page.wait_for_selector('.stat-card',timeout=7000)
        except Exception:
            print('DEBUG loader:',page.locator('#loading').inner_text())
            print('DEBUG shell:',page.locator('#shell').get_attribute('hidden'))
            print('DEBUG errors:',errors)
            raise
        if view!='overview':page.locator(f'button[data-view="{view}"]').first.click()
        if pid:page.locator(f'[data-filter-project="{pid}"]').first.click()
        if task:page.locator('.ticket').first.click();page.wait_for_selector('#task-sheet:not([hidden])')
        page.wait_for_timeout(200)
        page.screenshot(path=str(PREV/(name+'.png')),full_page=full,animations='disabled',timeout=15000)
        overflow=page.evaluate('({doc:document.documentElement.scrollWidth,window:innerWidth,main:document.querySelector(".main-area").scrollWidth})')
        print(name,'overflow',overflow)
        page.close()
    shot_app('painel-claro')
    shot_app('painel-escuro',theme='dark')
    shot_app('kanban-claro',view='board',pid=data['projects'][0]['id'])
    shot_app('kanban-escuro',view='board',theme='dark',pid=data['projects'][0]['id'])
    shot_app('tarefa-claro',view='board',pid=data['projects'][0]['id'],task=True)
    shot_app('relatorios-escuro',view='insights',theme='dark')
    shot_app('equipe-claro',view='team')
    shot_app('painel-mobile',width=390,height=844)
    browser.close()
    print('JS errors',errors)
