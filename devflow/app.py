"""DevFlow: multi-workspace task collaboration application.
All workspace access must pass require_workspace(); entity ids are never trusted alone.
"""
import os, csv, io, json, hashlib, secrets, asyncio, re
import httpx
import time
from collections import deque
from pathlib import Path
from datetime import timedelta, datetime
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional, Literal
from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from devflow.db import engine, Base, session, SessionLocal
from devflow import models as m
from devflow.security import init_csrf, require_csrf, hash_password, verify_password, valid_password, clean, slugify, ROLES, STATUSES, PRIORITIES

ROOT=Path(__file__).resolve().parent.parent
BASE_URL=os.getenv('DEVFLOW_BASE_URL','http://127.0.0.1:8010').rstrip('/')
SECRET=os.getenv('DEVFLOW_SECRET_KEY')
if not SECRET:
    SECRET=secrets.token_urlsafe(48)
    print('DevFlow: WARNING: ephemeral session secret. Set DEVFLOW_SECRET_KEY for stable sessions before production.')
SECURE_COOKIES=os.getenv('DEVFLOW_SECURE_COOKIES','0')=='1'

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    yield

app=FastAPI(title='DevFlow',version='1.0.0',lifespan=lifespan,docs_url='/api/docs' if os.getenv('DEVFLOW_ENABLE_API_DOCS','0')=='1' else None,redoc_url=None)
app.add_middleware(SessionMiddleware,secret_key=SECRET,session_cookie='devflow_session',max_age=60*60*24*7,same_site='lax',https_only=SECURE_COOKIES)
app.mount('/static',StaticFiles(directory=str(ROOT/'static')),name='static')

@app.middleware('http')
async def browser_security_headers(request:Request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response

AUTH_FAILURES=defaultdict(deque)
def rate_guard(request:Request,email:str):
    # Process-local safety net; use a shared rate limiter before public deployment.
    key=((request.client.host if request.client else 'unknown'),email.lower())
    current=time.monotonic()
    attempts=AUTH_FAILURES[key]
    while attempts and current-attempts[0]>600:attempts.popleft()
    if len(attempts)>=8:raise HTTPException(429,'Muitas tentativas. Tente novamente mais tarde.')
    return attempts


# Pydantic request models, limits + validation enforced on server
class Register(BaseModel):
    name: str=Field(min_length=2,max_length=120)
    email: EmailStr
    password: str=Field(min_length=10,max_length=128)
    workspace: str=Field(min_length=2,max_length=120)
class Login(BaseModel):
    email: EmailStr
    password: str
class ProjectCreate(BaseModel):
    name: str=Field(min_length=2,max_length=120)
    key: str=Field(min_length=2,max_length=12)
    description: str=Field(default='',max_length=2000)
    color: str=Field(default='#865cf6',max_length=20)
class ProjectPatch(BaseModel):
    name: str|None=Field(default=None,min_length=2,max_length=120)
    description: str|None=Field(default=None,max_length=2000)
    color: str|None=Field(default=None,max_length=20)
    archived: bool|None=None
class TaskCreate(BaseModel):
    project_id: int
    title: str=Field(min_length=2,max_length=240)
    description: str=Field(default='',max_length=8000)
    status: str='todo'
    priority: str='medium'
    assignee_id: int|None=None
    due_date: str|None=None
    estimate: int|None=Field(default=None,ge=0,le=1000)
    label_ids: list[int]=Field(default_factory=list,max_length=12)
class TaskPatch(BaseModel):
    title: str|None=Field(default=None,min_length=2,max_length=240)
    description: str|None=Field(default=None,max_length=8000)
    status: str|None=None
    priority: str|None=None
    assignee_id: int|None=None
    due_date: str|None=None
    estimate: int|None=Field(default=None,ge=0,le=1000)
    position: int|None=Field(default=None,ge=0,le=100000)
    label_ids: list[int]|None=Field(default=None,max_length=12)
    version: int|None=None
class CommentCreate(BaseModel): body: str=Field(min_length=1,max_length=5000)
class ChecklistCreate(BaseModel): text: str=Field(min_length=1,max_length=240)
class ChecklistPatch(BaseModel):
    text: str|None=Field(default=None,min_length=1,max_length=240)
    checked: bool|None=None
class InviteCreate(BaseModel):
    email: EmailStr
    role: Literal['admin','member','viewer']='member'
class LabelCreate(BaseModel):
    name: str=Field(min_length=1,max_length=40)
    color: str=Field(default='#9d73fb',max_length=20)
class GitHubLink(BaseModel):
    repository: str=Field(min_length=3,max_length=220)
class WorkspacePatch(BaseModel):
    name: str|None=Field(default=None,min_length=2,max_length=120)
    description: str|None=Field(default=None,max_length=2000)
class MemberPatch(BaseModel): role: Literal['admin','member','viewer']

# Account preferences belong to the current authenticated user, never a workspace member id.
class ProfilePatch(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    avatar_color: str = Field(min_length=7, max_length=7)
    current_password: str = Field(min_length=1)

class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=10, max_length=128)



class EventHub:
    def __init__(self): self.clients=defaultdict(set)
    async def emit(self,wid,payload):
        for ws in list(self.clients[wid]):
            try: await ws.send_json(payload)
            except Exception: self.clients[wid].discard(ws)
hub=EventHub()

def me(request:Request, db:Session=Depends(session)):
    uid=request.session.get('uid')
    user=db.get(m.User,uid) if isinstance(uid,int) else None
    if not user: raise HTTPException(401,'Entre na sua conta para continuar.')
    return user

def workspace(db,wid,uid,min_role='viewer'):
    w=db.get(m.Workspace,wid)
    membership=db.scalar(select(m.Membership).where(m.Membership.workspace_id==wid,m.Membership.user_id==uid))
    if not w or not membership: raise HTTPException(404,'Espaço não encontrado.')
    if ROLES[membership.role]<ROLES[min_role]: raise HTTPException(403,'Seu perfil não possui essa permissão.')
    return w,membership

def proj(db,wid,pid):
    p=db.scalar(select(m.Project).where(m.Project.id==pid,m.Project.workspace_id==wid))
    if not p: raise HTTPException(404,'Projeto não encontrado neste espaço.')
    return p

def task(db,wid,tid):
    t=db.scalar(select(m.Task).where(m.Task.id==tid,m.Task.workspace_id==wid))
    if not t: raise HTTPException(404,'Tarefa não encontrada neste espaço.')
    return t

def valid_status_priority(status,priority):
    if status not in STATUSES or priority not in PRIORITIES: raise HTTPException(422,'Status ou prioridade inválidos.')

def assignee(db,wid,aid):
    if aid is None: return
    if not db.scalar(select(m.Membership.id).where(m.Membership.workspace_id==wid,m.Membership.user_id==aid)):
        raise HTTPException(422,'Responsável não pertence à equipe.')

def datecheck(date):
    if date is None or date=='':return None
    try: datetime.strptime(date,'%Y-%m-%d')
    except ValueError: raise HTTPException(422,'Data inválida (AAAA-MM-DD).')
    return date

def valid_color(color):
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise HTTPException(422,'Cor inválida.')
    return color

def log(db,wid,uid,verb,detail='',pid=None,tid=None):
    db.add(m.Activity(workspace_id=wid,actor_id=uid,verb=verb,detail=detail[:250],project_id=pid,task_id=tid))

def user_json(u): return {'id':u.id,'name':u.name,'email':u.email,'color':u.avatar_color,'initials': ''.join(x[0] for x in u.name.split()[:2]).upper()}
def project_json(p): return {'id':p.id,'name':p.name,'key':p.key,'description':p.description,'color':p.color,'icon':p.icon,'archived':p.archived}
def task_json(t,db):
    ls=db.scalars(select(m.Label).join(m.TaskLabel,m.TaskLabel.label_id==m.Label.id).where(m.TaskLabel.task_id==t.id)).all()
    cnt=db.scalar(select(func.count(m.Comment.id)).where(m.Comment.task_id==t.id)) or 0
    checks=db.scalars(select(m.Checklist).where(m.Checklist.task_id==t.id)).all()
    return {'id':t.id,'project_id':t.project_id,'number':t.number,'title':t.title,'description':t.description,'status':t.status,
        'priority':t.priority,'assignee_id':t.assignee_id,'created_by':t.created_by,'due_date':t.due_date,'estimate':t.estimate,
        'position':t.position,'version':t.version,'updated_at':t.updated_at.isoformat() if t.updated_at else None,
        'labels':[{'id':x.id,'name':x.name,'color':x.color} for x in ls],'comment_count':cnt,
        'check_count':len(checks),'check_done':sum(c.checked for c in checks)}

def notify(db,wid,uid,title,body,tid=None):
    if uid: db.add(m.Notification(workspace_id=wid,user_id=uid,title=title[:180],body=body[:300],task_id=tid))

@app.get('/',response_class=HTMLResponse)
def home(): return FileResponse(ROOT/'templates'/'landing.html')
@app.get('/entrar',response_class=HTMLResponse)
def auth(): return FileResponse(ROOT/'templates'/'auth.html')

# Compatibilidade com links e iniciadores antigos que usam /login.
@app.get('/login',include_in_schema=False)
def legacy_login(): return RedirectResponse('/entrar',status_code=302)
@app.get('/app',response_class=HTMLResponse)
def app_page(request:Request):
    if not request.session.get('uid'):return RedirectResponse('/entrar',status_code=302)
    return FileResponse(ROOT/'templates'/'app.html')
@app.get('/convite/{token}',response_class=HTMLResponse)
def join_page(token:str):return FileResponse(ROOT/'templates'/'auth.html')

@app.post('/api/auth/register')
def register(data:Register,request:Request,db:Session=Depends(session)):
    email=data.email.strip().lower()
    valid_password(data.password)
    if db.scalar(select(m.User).where(m.User.email==email)):raise HTTPException(409,'E-mail já cadastrado.')
    user=m.User(name=clean(data.name,120),email=email,password_hash=hash_password(data.password))
    db.add(user); db.flush()
    slug=slugify(data.workspace)
    if db.scalar(select(m.Workspace).where(m.Workspace.slug==slug)): slug=f'{slug}-{secrets.token_hex(2)}'
    w=m.Workspace(name=clean(data.workspace,120),slug=slug)
    db.add(w);db.flush()
    db.add(m.Membership(workspace_id=w.id,user_id=user.id,role='owner'))
    p=m.Project(workspace_id=w.id,name='Meu primeiro projeto',key='START',description='Organize o trabalho da sua equipe.')
    db.add(p);db.flush()
    db.add(m.ProjectSequence(project_id=p.id,last_number=0))
    for name,color in [('Design','#a78bfa'),('Bug','#f87171'),('Feature','#34d399'),('Urgente','#fb923c')]:db.add(m.Label(workspace_id=w.id,name=name,color=color))
    log(db,w.id,user.id,'created_workspace',w.name)
    db.commit()
    request.session.clear();request.session['uid']=user.id;init_csrf(request)
    return {'ok':True,'workspace_id':w.id}

@app.post('/api/auth/login')
def login(data:Login,request:Request,db:Session=Depends(session)):
    attempts=rate_guard(request,data.email)
    u=db.scalar(select(m.User).where(m.User.email==data.email.strip().lower()))
    if not u or not verify_password(data.password,u.password_hash):
        attempts.append(time.monotonic())
        raise HTTPException(401,'E-mail ou senha incorretos.')
    attempts.clear()
    request.session.clear();request.session['uid']=u.id;init_csrf(request)
    return {'ok':True}

@app.post('/api/auth/logout')
def logout(request:Request,u:m.User=Depends(me)):
    require_csrf(request);request.session.clear();return {'ok':True}


@app.patch('/api/account/profile')
def update_profile(data:ProfilePatch,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request)
    name=clean(data.name,120)
    if len(name)<2: raise HTTPException(422,'Informe um nome com pelo menos 2 caracteres.')
    email=data.email.strip().lower()
    color=valid_color(data.avatar_color)
    if not verify_password(data.current_password,u.password_hash):
        raise HTTPException(403,'Senha atual incorreta.')
    duplicate=db.scalar(select(m.User.id).where(m.User.email==email,m.User.id!=u.id))
    if duplicate:raise HTTPException(409,'Este e-mail já está cadastrado.')
    u.name=name
    u.email=email
    u.avatar_color=color
    db.commit()
    return {'ok':True,'user':user_json(u)}

@app.post('/api/account/change-password')
def change_password(data:PasswordChange,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request)
    if not verify_password(data.current_password,u.password_hash):
        raise HTTPException(403,'Senha atual incorreta.')
    valid_password(data.new_password)
    if verify_password(data.new_password,u.password_hash):
        raise HTTPException(422,'Escolha uma senha diferente da atual.')
    u.password_hash=hash_password(data.new_password)
    db.commit()
    return {'ok':True}

@app.get('/api/bootstrap')
def bootstrap(request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    membership=db.scalars(select(m.Membership).where(m.Membership.user_id==u.id).order_by(m.Membership.id)).all()
    workspaces=[{'id':w.id,'name':w.name,'slug':w.slug,'description':w.description,'role':x.role} for x in membership if (w:=db.get(m.Workspace,x.workspace_id))]
    return {'user':user_json(u),'workspaces':workspaces,'csrf':init_csrf(request)}

@app.get('/api/workspaces/{wid}/data')
def data(wid:int,u:m.User=Depends(me),db:Session=Depends(session)):
    w,mem=workspace(db,wid,u.id)
    projects=db.scalars(select(m.Project).where(m.Project.workspace_id==wid).order_by(m.Project.id)).all()
    tasks=db.scalars(select(m.Task).where(m.Task.workspace_id==wid).order_by(m.Task.position,m.Task.id)).all()
    members=db.scalars(select(m.Membership).where(m.Membership.workspace_id==wid)).all()
    users={row.user_id:db.get(m.User,row.user_id) for row in members}
    activities=db.scalars(select(m.Activity).where(m.Activity.workspace_id==wid).order_by(m.Activity.id.desc()).limit(80)).all()
    labels=db.scalars(select(m.Label).where(m.Label.workspace_id==wid).order_by(m.Label.name)).all()
    integrations=db.scalars(select(m.GitHubIntegration).where(m.GitHubIntegration.workspace_id==wid)).all()
    notifs=db.scalars(select(m.Notification).where(m.Notification.user_id==u.id,m.Notification.workspace_id==wid).order_by(m.Notification.id.desc()).limit(40)).all()
    return {'workspace':{'id':w.id,'name':w.name,'slug':w.slug,'description':w.description,'role':mem.role},
        'projects':[project_json(x) for x in projects], 'tasks':[task_json(t,db) for t in tasks],
        'members':[dict(user_json(users[x.user_id]),role=x.role,joined=x.created_at.isoformat()) for x in members],
        'labels':[{'id':x.id,'name':x.name,'color':x.color} for x in labels],
        'integrations':{str(x.project_id):x.repository for x in integrations},
        'activities':[{'id':x.id,'verb':x.verb,'detail':x.detail,'actor_id':x.actor_id,'task_id':x.task_id,'project_id':x.project_id,'created_at':x.created_at.isoformat()} for x in activities],
        'notifications':[{'id':x.id,'title':x.title,'body':x.body,'read':x.read,'task_id':x.task_id,'created_at':x.created_at.isoformat()} for x in notifs]}

@app.patch('/api/workspaces/{wid}')
def patch_workspace(wid:int,data:WorkspacePatch,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);w,_=workspace(db,wid,u.id,'admin')
    for k,v in data.model_dump(exclude_unset=True).items():
        if v is not None:setattr(w,k,clean(v,2000))
    log(db,wid,u.id,'updated_workspace',w.name);db.commit();return {'ok':True}

@app.post('/api/workspaces/{wid}/projects')
def create_project(wid:int,data:ProjectCreate,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'member')
    key=re.sub('[^A-Z0-9]','',data.key.upper())[:12]
    if len(key)<2:raise HTTPException(422,'Chave do projeto inválida.')
    if db.scalar(select(m.Project).where(m.Project.workspace_id==wid,m.Project.key==key)):raise HTTPException(409,'Chave de projeto já existente.')
    p=m.Project(workspace_id=wid,name=clean(data.name,120),key=key,description=clean(data.description,2000),color=valid_color(data.color))
    db.add(p);db.flush();db.add(m.ProjectSequence(project_id=p.id,last_number=0));log(db,wid,u.id,'created_project',p.name,pid=p.id)
    db.commit();return project_json(p)

@app.patch('/api/workspaces/{wid}/projects/{pid}')
def patch_project(wid:int,pid:int,data:ProjectPatch,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'admin');p=proj(db,wid,pid)
    for k,v in data.model_dump(exclude_unset=True).items():
        if v is None:continue
        setattr(p,k,valid_color(v) if k=='color' else v)
    log(db,wid,u.id,'updated_project',p.name,pid=pid);db.commit();return project_json(p)

@app.post('/api/workspaces/{wid}/tasks')
async def create_task(wid:int,data:TaskCreate,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'member');p=proj(db,wid,data.project_id)
    if p.archived:raise HTTPException(409,'Projeto arquivado.')
    valid_status_priority(data.status,data.priority);assignee(db,wid,data.assignee_id)
    due=datecheck(data.due_date)
    if data.label_ids:
        actual=set(db.scalars(select(m.Label.id).where(m.Label.workspace_id==wid,m.Label.id.in_(data.label_ids))).all())
        if actual!=set(data.label_ids):raise HTTPException(422,'Etiqueta inválida.')
    seq=db.get(m.ProjectSequence,p.id)
    if seq is None:seq=m.ProjectSequence(project_id=p.id,last_number=0);db.add(seq)
    seq.last_number+=1
    pos=db.scalar(select(func.coalesce(func.max(m.Task.position),0)).where(m.Task.project_id==p.id,m.Task.status==data.status)) or 0
    t=m.Task(workspace_id=wid,project_id=p.id,number=seq.last_number,title=clean(data.title,240),description=clean(data.description,8000),status=data.status,
        priority=data.priority,assignee_id=data.assignee_id,created_by=u.id,due_date=due,estimate=data.estimate,position=pos+1)
    db.add(t);db.flush()
    for lid in set(data.label_ids):db.add(m.TaskLabel(task_id=t.id,label_id=lid))
    log(db,wid,u.id,'created_task',f'{p.key}-{t.number} · {t.title}',p.id,t.id)
    if t.assignee_id and t.assignee_id!=u.id:notify(db,wid,t.assignee_id,'Nova tarefa atribuída',t.title,t.id)
    db.commit()
    result=task_json(t,db)
    await hub.emit(wid,{'kind':'task_changed','id':t.id,'actor':u.id})
    return result

@app.patch('/api/workspaces/{wid}/tasks/{tid}')
async def patch_task(wid:int,tid:int,data:TaskPatch,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'member');t=task(db,wid,tid);p=proj(db,wid,t.project_id)
    if p.archived:raise HTTPException(409,'Projeto arquivado.')
    patch=data.model_dump(exclude_unset=True)
    if patch.get('version') is not None and patch['version']!=t.version:raise HTTPException(409,'Esta tarefa foi atualizada por outra pessoa. Atualize e tente novamente.')
    if 'status' in patch and patch['status'] not in STATUSES:raise HTTPException(422,'Status inválido.')
    if 'priority' in patch and patch['priority'] not in PRIORITIES:raise HTTPException(422,'Prioridade inválida.')
    if 'assignee_id' in patch:assignee(db,wid,patch['assignee_id'])
    if 'due_date' in patch:patch['due_date']=datecheck(patch['due_date'])
    if patch.get('label_ids') is not None:
        lbl=set(db.scalars(select(m.Label.id).where(m.Label.workspace_id==wid,m.Label.id.in_(patch['label_ids']))).all())
        if lbl!=set(patch['label_ids']):raise HTTPException(422,'Etiqueta inválida.')
        db.query(m.TaskLabel).filter(m.TaskLabel.task_id==tid).delete(synchronize_session=False)
        for lid in lbl:db.add(m.TaskLabel(task_id=tid,label_id=lid))
    patch.pop('label_ids',None);patch.pop('version',None)
    prev_status=t.status;prev_assignee=t.assignee_id
    for k,v in patch.items():setattr(t,k,v)
    t.version+=1;t.updated_at=m.now()
    event='moved_task' if prev_status!=t.status else 'updated_task'
    log(db,wid,u.id,event,t.title,p.id,t.id)
    if t.assignee_id and t.assignee_id!=u.id and t.assignee_id!=prev_assignee:notify(db,wid,t.assignee_id,'Tarefa atribuída a você',t.title,t.id)
    db.commit();result=task_json(t,db)
    await hub.emit(wid,{'kind':'task_changed','id':t.id,'actor':u.id})
    return result

@app.get('/api/workspaces/{wid}/tasks/{tid}')
def detail(wid:int,tid:int,u:m.User=Depends(me),db:Session=Depends(session)):
    workspace(db,wid,u.id);t=task(db,wid,tid)
    comments=db.scalars(select(m.Comment).where(m.Comment.task_id==tid).order_by(m.Comment.id)).all()
    checklist=db.scalars(select(m.Checklist).where(m.Checklist.task_id==tid).order_by(m.Checklist.position,m.Checklist.id)).all()
    return {'task':task_json(t,db),
       'comments':[{'id':c.id,'body':c.body,'user_id':c.user_id,'created_at':c.created_at.isoformat()} for c in comments],
       'checklist':[{'id':c.id,'text':c.text,'checked':c.checked} for c in checklist]}

@app.post('/api/workspaces/{wid}/tasks/{tid}/comments')
async def comment(wid:int,tid:int,data:CommentCreate,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'member');t=task(db,wid,tid)
    c=m.Comment(task_id=t.id,user_id=u.id,body=clean(data.body,5000));db.add(c);db.flush()
    log(db,wid,u.id,'commented',t.title,t.project_id,t.id)
    if t.assignee_id and t.assignee_id!=u.id:notify(db,wid,t.assignee_id,'Novo comentário',t.title,t.id)
    db.commit();await hub.emit(wid,{'kind':'comment','id':t.id,'actor':u.id})
    return {'id':c.id,'body':c.body,'user_id':u.id,'created_at':c.created_at.isoformat()}

@app.post('/api/workspaces/{wid}/tasks/{tid}/checklist')
def add_check(wid:int,tid:int,data:ChecklistCreate,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'member');t=task(db,wid,tid)
    count=db.scalar(select(func.count(m.Checklist.id)).where(m.Checklist.task_id==tid)) or 0
    if count>=50:raise HTTPException(422,'Limite de 50 itens por tarefa.')
    c=m.Checklist(task_id=tid,text=clean(data.text,240),position=count);db.add(c)
    log(db,wid,u.id,'updated_checklist',t.title,t.project_id,t.id);db.commit();return {'id':c.id,'text':c.text,'checked':c.checked}

@app.patch('/api/workspaces/{wid}/tasks/{tid}/checklist/{cid}')
def patch_check(wid:int,tid:int,cid:int,data:ChecklistPatch,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'member');task(db,wid,tid)
    c=db.scalar(select(m.Checklist).where(m.Checklist.id==cid,m.Checklist.task_id==tid))
    if not c:raise HTTPException(404,'Item não encontrado.')
    for k,v in data.model_dump(exclude_unset=True).items():setattr(c,k,v)
    db.commit();return {'ok':True}

@app.delete('/api/workspaces/{wid}/tasks/{tid}/checklist/{cid}')
def delete_check(wid:int,tid:int,cid:int,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'member');task(db,wid,tid)
    c=db.scalar(select(m.Checklist).where(m.Checklist.id==cid,m.Checklist.task_id==tid))
    if not c:raise HTTPException(404,'Item não encontrado.')
    db.delete(c);db.commit();return {'ok':True}

@app.post('/api/workspaces/{wid}/labels')
def label(wid:int,data:LabelCreate,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'admin');color=valid_color(data.color)
    if db.scalar(select(m.Label).where(m.Label.workspace_id==wid,m.Label.name==data.name.strip())):raise HTTPException(409,'Etiqueta já existe.')
    l=m.Label(workspace_id=wid,name=clean(data.name,40),color=color);db.add(l);db.commit();return {'id':l.id,'name':l.name,'color':l.color}

@app.post('/api/workspaces/{wid}/invites')
def invite(wid:int,data:InviteCreate,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'admin')
    email=data.email.strip().lower();existing=db.scalar(select(m.User).where(m.User.email==email))
    if existing and db.scalar(select(m.Membership).where(m.Membership.workspace_id==wid,m.Membership.user_id==existing.id)):raise HTTPException(409,'Pessoa já faz parte da equipe.')
    token=secrets.token_urlsafe(32)
    i=m.Invitation(workspace_id=wid,email=email,role=data.role,token_hash=hashlib.sha256(token.encode()).hexdigest(),expires_at=m.now()+timedelta(days=7),created_by=u.id)
    db.add(i);log(db,wid,u.id,'invited_member',email);db.commit()
    # The link is returned to the workspace admin; there is no claim of email delivery.
    return {'link':BASE_URL+'/convite/'+token,'email':email,'expires_in_days':7}

@app.post('/api/invites/{token}/accept')
def accept_invite(token:str,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request)
    inv=db.scalar(select(m.Invitation).where(m.Invitation.token_hash==hashlib.sha256(token.encode()).hexdigest()))
    if not inv or inv.accepted_at or inv.expires_at<m.now():raise HTTPException(404,'Convite inválido ou expirado.')
    if inv.email!=u.email:raise HTTPException(403,'Entre na conta de e-mail indicada no convite.')
    if db.scalar(select(m.Membership).where(m.Membership.workspace_id==inv.workspace_id,m.Membership.user_id==u.id)):raise HTTPException(409,'Já faz parte da equipe.')
    db.add(m.Membership(workspace_id=inv.workspace_id,user_id=u.id,role=inv.role));inv.accepted_at=m.now()
    log(db,inv.workspace_id,u.id,'joined_workspace',u.name);db.commit();return {'ok':True,'workspace_id':inv.workspace_id}

@app.patch('/api/workspaces/{wid}/members/{uid}')
def change_role(wid:int,uid:int,data:MemberPatch,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'owner')
    member=db.scalar(select(m.Membership).where(m.Membership.workspace_id==wid,m.Membership.user_id==uid))
    if not member:raise HTTPException(404,'Membro não encontrado.')
    if member.role=='owner':raise HTTPException(403,'Não é possível mudar o proprietário.')
    member.role=data.role;log(db,wid,u.id,'changed_role',str(uid));db.commit();return {'ok':True}

@app.get('/api/workspaces/{wid}/export.csv')
def export_csv(wid:int,u:m.User=Depends(me),db:Session=Depends(session)):
    workspace(db,wid,u.id)
    tasks=db.scalars(select(m.Task).where(m.Task.workspace_id==wid)).all()
    ids={p.id:p.key for p in db.scalars(select(m.Project).where(m.Project.workspace_id==wid)).all()}
    buf=io.StringIO();writer=csv.writer(buf);writer.writerow(['Projeto','Código','Título','Status','Prioridade','Prazo','Descrição'])
    def escape_csv(s):
        text=str(s or '')
        return "'"+text if text[:1] in ('=','+','-','@') else text
    for t in tasks:writer.writerow([ids.get(t.project_id,''),f'{ids.get(t.project_id, "")}-{t.number}',escape_csv(t.title),t.status,t.priority,t.due_date or '',escape_csv(t.description)])
    return StreamingResponse(iter([buf.getvalue().encode('utf-8-sig')]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="devflow-tarefas.csv"'})

@app.patch('/api/workspaces/{wid}/notifications/{nid}')
def read_notification(wid:int,nid:int,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id)
    notification=db.scalar(select(m.Notification).where(m.Notification.id==nid,m.Notification.workspace_id==wid,m.Notification.user_id==u.id))
    if not notification:raise HTTPException(404,'Notificação não encontrada.')
    notification.read=True;db.commit();return {'ok':True}

def github_issue(repo:str, number:int|None=None):
    """Only access the fixed official API host with validated owner/repo path."""
    if (not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}/[a-zA-Z0-9_.-]{1,100}',repo)) or any(x in ('.','..') for x in repo.split('/')):
        raise HTTPException(422,'Informe o repositório no formato usuario/repositorio.')
    if number is not None and not 0 < number <= 2147483647:raise HTTPException(422,'Número de issue inválido.')
    endpoint=f'https://api.github.com/repos/{repo}/issues'
    url=endpoint+('/'+str(number) if number else '?state=open&per_page=30')
    headers={'Accept':'application/vnd.github+json','User-Agent':'DevFlow-Project-Manager','X-GitHub-Api-Version':'2022-11-28'}
    token=os.getenv('DEVFLOW_GITHUB_TOKEN')
    if token:headers['Authorization']='Bearer '+token
    try:
        response=httpx.get(url,headers=headers,timeout=8.0,follow_redirects=False)
        if response.status_code==404:raise HTTPException(404,'Repositório ou issue não encontrado no GitHub.')
        if response.status_code!=200:raise HTTPException(503,f'GitHub indisponível (HTTP {response.status_code}).')
        return response.json()
    except (httpx.TimeoutException,httpx.RequestError):raise HTTPException(503,'Falha ao consultar o GitHub. Tente mais tarde.')

@app.put('/api/workspaces/{wid}/projects/{pid}/github')
def connect_github(wid:int,pid:int,data:GitHubLink,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'admin');proj(db,wid,pid)
    repo=data.repository.strip()
    if (not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}/[a-zA-Z0-9_.-]{1,100}',repo)) or any(x in ('.','..') for x in repo.split('/')):raise HTTPException(422,'Formato esperado: usuario/repositorio.')
    integration=db.get(m.GitHubIntegration,pid)
    if integration:integration.repository=repo
    else:db.add(m.GitHubIntegration(project_id=pid,workspace_id=wid,repository=repo))
    log(db,wid,u.id,'connected_github',repo,pid=pid);db.commit()
    return {'repository':repo}

@app.get('/api/workspaces/{wid}/projects/{pid}/github/issues')
def list_github_issues(wid:int,pid:int,u:m.User=Depends(me),db:Session=Depends(session)):
    workspace(db,wid,u.id);proj(db,wid,pid)
    integration=db.get(m.GitHubIntegration,pid)
    if not integration or integration.workspace_id!=wid:raise HTTPException(404,'GitHub não conectado ao projeto.')
    issues=github_issue(integration.repository)
    imported={x.issue_number for x in db.scalars(select(m.ImportedGitHubIssue).where(m.ImportedGitHubIssue.project_id==pid)).all()}
    return {'repository':integration.repository,'issues':[{'number':x.get('number'),'title':x.get('title','')[:240],'url':x.get('html_url'),'imported':x.get('number') in imported} for x in issues if isinstance(x,dict) and 'pull_request' not in x]}

@app.post('/api/workspaces/{wid}/projects/{pid}/github/issues/{number}/import')
async def import_github_issue(wid:int,pid:int,number:int,request:Request,u:m.User=Depends(me),db:Session=Depends(session)):
    require_csrf(request);workspace(db,wid,u.id,'member');p=proj(db,wid,pid)
    if p.archived:raise HTTPException(409,'Projeto arquivado.')
    integration=db.get(m.GitHubIntegration,pid)
    if not integration or integration.workspace_id!=wid:raise HTTPException(404,'GitHub não conectado ao projeto.')
    if db.scalar(select(m.ImportedGitHubIssue).where(m.ImportedGitHubIssue.project_id==pid,m.ImportedGitHubIssue.issue_number==number)):
        raise HTTPException(409,'Esta issue já foi importada.')
    issue=github_issue(integration.repository,number)
    if not isinstance(issue,dict) or 'pull_request' in issue:raise HTTPException(422,'Somente issues podem ser importadas.')
    seq=db.get(m.ProjectSequence,pid)
    if not seq:seq=m.ProjectSequence(project_id=pid,last_number=0);db.add(seq)
    seq.last_number+=1
    title=clean(issue.get('title') or f'Issue #{number}',240)
    body=clean(issue.get('body') or '',7200)
    link=f'https://github.com/{integration.repository}/issues/{number}'
    t=m.Task(workspace_id=wid,project_id=pid,number=seq.last_number,title=title,description=(body+'\n\nOrigem: '+link).strip()[:8000],status='backlog',priority='medium',created_by=u.id,position=seq.last_number)
    db.add(t);db.flush()
    db.add(m.ImportedGitHubIssue(project_id=pid,issue_number=number,task_id=t.id))
    log(db,wid,u.id,'imported_github_issue',f'#{number} · {title}',pid=pid,tid=t.id)
    db.commit();await hub.emit(wid,{'kind':'task_changed','id':t.id,'actor':u.id})
    return task_json(t,db)

@app.websocket('/ws/{wid}')
async def websocket_endpoint(ws:WebSocket,wid:int):
    uid=ws.session.get('uid')
    db=SessionLocal()
    try:
        if not isinstance(uid,int):await ws.close(code=1008);return
        try:workspace(db,wid,uid)
        except HTTPException:await ws.close(code=1008);return
        await ws.accept();hub.clients[wid].add(ws)
        while True:
            # Client sends pings only, edits take place exclusively via CSRF protected HTTP endpoints.
            await ws.receive_text()
    except WebSocketDisconnect:pass
    finally:
        hub.clients[wid].discard(ws)
        db.close()

@app.get('/api/health')
def health():return {'status':'ok','service':'DevFlow'}
