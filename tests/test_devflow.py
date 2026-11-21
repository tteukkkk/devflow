from __future__ import annotations
import os, sys
from pathlib import Path
from datetime import timedelta
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import devflow.db as database
import devflow.app as mod
from devflow import models as m

@pytest.fixture
def env(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'testing.sqlite3'),connect_args={'check_same_thread':False})
    @event.listens_for(engine,'connect')
    def fk(dbapi,rec):dbapi.execute('PRAGMA foreign_keys=ON')
    factory=sessionmaker(engine,autoflush=False,expire_on_commit=False)
    m.Base.metadata.create_all(engine)
    monkeypatch.setattr(database,'engine',engine)
    monkeypatch.setattr(database,'SessionLocal',factory)
    monkeypatch.setattr(mod,'engine',engine)
    monkeypatch.setattr(mod,'SessionLocal',factory)
    with TestClient(mod.app) as client:
        yield client,factory
    engine.dispose()

def register(c,name='Alice',email='alice@example.com',workspace='Equipe Aurora',password='SenhaSegura123'):
    r=c.post('/api/auth/register',json={'name':name,'email':email,'password':password,'workspace':workspace})
    assert r.status_code==200,r.text
    b=c.get('/api/bootstrap');assert b.status_code==200,b.text
    return b.json()['workspaces'][0]['id'],b.json()['csrf']

def post(c,path,csrf,data=None,method='POST'):
    return c.request(method,path,headers={'x-csrf-token':csrf},json=data if data is not None else {})

def setup(env):
    c,_=env;wid,csrf=register(c)
    data=c.get(f'/api/workspaces/{wid}/data').json();pid=data['projects'][0]['id']
    return c,wid,csrf,pid

def create_task(c,wid,csrf,pid,**kw):
    r=post(c,f'/api/workspaces/{wid}/tasks',csrf,{'project_id':pid,'title':'Criar painel de projetos',**kw})
    assert r.status_code==200,r.text
    return r.json()

def test_health_and_login(env):
    c,_=env;assert c.get('/api/health').json()['status']=='ok'
    assert c.get('/').status_code==200
    assert c.get('/app',follow_redirects=False).status_code==302
    wid,csrf=register(c)
    assert c.get('/app').status_code==200
    assert c.get(f'/api/workspaces/{wid}/data').status_code==200
    assert post(c,'/api/auth/logout',csrf).status_code==200
    assert c.get('/api/bootstrap').status_code==401
    assert c.post('/api/auth/login',json={'email':'alice@example.com','password':'SenhaSegura123'}).status_code==200
    assert c.post('/api/auth/login',json={'email':'alice@example.com','password':'errada'}).status_code==401

def test_password_restrictions_and_duplicate_email(env):
    c,_=env
    a=c.post('/api/auth/register',json={'name':'A','email':'a@example.com','password':'curta','workspace':'AB'})
    assert a.status_code==422
    wid,csrf=register(c)
    a=c.post('/api/auth/register',json={'name':'Outra','email':'alice@example.com','password':'SenhaSegura123','workspace':'Outra equipe'})
    assert a.status_code==409

def test_csrf_and_status_validation(env):
    c,wid,csrf,pid=setup(env)
    url=f'/api/workspaces/{wid}/tasks'
    assert c.post(url,json={'project_id':pid,'title':'Não autorizado'}).status_code==403
    assert post(c,url,'token-ruim',{'project_id':pid,'title':'Não autorizado'}).status_code==403
    assert post(c,url,csrf,{'project_id':pid,'title':'Tarefa','status':'unknown'}).status_code==422
    assert post(c,url,csrf,{'project_id':pid,'title':'Tarefa','due_date':'2026-55-90'}).status_code==422

def test_task_lifecycle_and_conflict(env):
    c,wid,csrf,pid=setup(env)
    task=create_task(c,wid,csrf,pid)
    tid=task['id']
    detail=c.get(f'/api/workspaces/{wid}/tasks/{tid}');assert detail.status_code==200
    changed=post(c,f'/api/workspaces/{wid}/tasks/{tid}',csrf,{'status':'in_progress','version':1},'PATCH')
    assert changed.status_code==200,changed.text
    assert changed.json()['version']==2
    old=post(c,f'/api/workspaces/{wid}/tasks/{tid}',csrf,{'status':'done','version':1},'PATCH')
    assert old.status_code==409
    assert c.get(f'/api/workspaces/{wid}/data').json()['tasks'][0]['status']=='in_progress'

def test_comments_checklists_labels(env):
    c,wid,csrf,pid=setup(env)
    labels=c.get(f'/api/workspaces/{wid}/data').json()['labels']
    t=create_task(c,wid,csrf,pid,label_ids=[labels[0]['id']]);tid=t['id']
    r=post(c,f'/api/workspaces/{wid}/tasks/{tid}/comments',csrf,{'body':'Em revisão pela equipe'})
    assert r.status_code==200,r.text
    checklist=post(c,f'/api/workspaces/{wid}/tasks/{tid}/checklist',csrf,{'text':'Validar filtros'})
    assert checklist.status_code==200
    cid=checklist.json()['id']
    assert post(c,f'/api/workspaces/{wid}/tasks/{tid}/checklist/{cid}',csrf,{'checked':True},'PATCH').status_code==200
    detail=c.get(f'/api/workspaces/{wid}/tasks/{tid}').json()
    assert detail['checklist'][0]['checked'] is True
    assert detail['comments'][0]['body']=='Em revisão pela equipe'
    assert detail['task']['check_done']==1

def test_multi_tenant_isolation(env):
    c,factory=env;wid,csrf=register(c)
    pid=c.get(f'/api/workspaces/{wid}/data').json()['projects'][0]['id']
    t=create_task(c,wid,csrf,pid)
    w2,c2=register(c,name='Bob',email='bob@example.com',workspace='Equipe Boreal')
    assert w2!=wid
    assert c.get(f'/api/workspaces/{wid}/data').status_code==404
    assert c.get(f'/api/workspaces/{w2}/tasks/{t["id"]}').status_code==404
    assert post(c,f'/api/workspaces/{w2}/tasks/{t["id"]}',c2,{'status':'done'},'PATCH').status_code==404
    assert post(c,f'/api/workspaces/{w2}/tasks',c2,{'title':'Vazar','project_id':pid}).status_code==404
    assert c.get(f'/api/workspaces/{wid}/export.csv').status_code==404

def test_viewer_permissions(env):
    c,factory=env;wid,csrf=register(c)
    d=c.get(f'/api/workspaces/{wid}/data').json();pid=d['projects'][0]['id']
    with factory() as db:
        view=m.User(name='Cliente',email='cliente@example.com',password_hash=mod.hash_password('SenhaSegura123'))
        db.add(view);db.flush();db.add(m.Membership(user_id=view.id,workspace_id=wid,role='viewer'));db.commit()
    c.post('/api/auth/login',json={'email':'cliente@example.com','password':'SenhaSegura123'})
    token=c.get('/api/bootstrap').json()['csrf']
    assert c.get(f'/api/workspaces/{wid}/data').status_code==200
    assert post(c,f'/api/workspaces/{wid}/tasks',token,{'title':'Não pode','project_id':pid}).status_code==403
    assert post(c,f'/api/workspaces/{wid}/projects',token,{'name':'Não pode','key':'XX'}).status_code==403
    assert post(c,f'/api/workspaces/{wid}/invites',token,{'email':'x@example.com'}).status_code==403

def test_invite_and_account_binding(env):
    c,factory=env;wid,csrf=register(c)
    i=post(c,f'/api/workspaces/{wid}/invites',csrf,{'email':'bob@example.com','role':'member'})
    assert i.status_code==200
    token=i.json()['link'].split('/')[-1]
    register(c,'Carol','carol@example.com','Equipe Costa')
    cs=c.get('/api/bootstrap').json()['csrf']
    assert post(c,f'/api/invites/{token}/accept',cs).status_code==403
    register(c,'Bob','bob@example.com','Equipe Rio')
    bs=c.get('/api/bootstrap').json()['csrf']
    accept=post(c,f'/api/invites/{token}/accept',bs)
    assert accept.status_code==200,accept.text
    assert c.get(f'/api/workspaces/{wid}/data').status_code==200
    assert post(c,f'/api/invites/{token}/accept',bs).status_code==404

def test_cross_workspace_assignees_and_labels(env):
    c,factory=env;wid,csrf=register(c)
    p=c.get(f'/api/workspaces/{wid}/data').json()['projects'][0]['id']
    wid2,csrf2=register(c,'Bob','bob@example.com','Outra equipe')
    data=c.get(f'/api/workspaces/{wid2}/data').json();invalid_label=data['labels'][0]['id'];invalid_assignee=data['members'][0]['id']
    c.post('/api/auth/login',json={'email':'alice@example.com','password':'SenhaSegura123'})
    csrf=c.get('/api/bootstrap').json()['csrf']
    assert post(c,f'/api/workspaces/{wid}/tasks',csrf,{'title':'Teste','project_id':p,'assignee_id':invalid_assignee}).status_code==422
    assert post(c,f'/api/workspaces/{wid}/tasks',csrf,{'title':'Teste','project_id':p,'label_ids':[invalid_label]}).status_code==422

def test_export_formula_injection(env):
    c,wid,csrf,pid=setup(env)
    create_task(c,wid,csrf,pid,title='=IMPORTXML("http://example.com","//a")')
    resp=c.get(f'/api/workspaces/{wid}/export.csv')
    assert resp.status_code==200
    assert "'=IMPORTXML" in resp.content.decode('utf-8-sig')

def test_archive_blocks_creation(env):
    c,wid,csrf,pid=setup(env)
    assert post(c,f'/api/workspaces/{wid}/projects/{pid}',csrf,{'archived':True},'PATCH').status_code==200
    assert post(c,f'/api/workspaces/{wid}/tasks',csrf,{'title':'Deve bloquear','project_id':pid}).status_code==409

def test_invalid_label_and_assignee_on_patch(env):
    c,wid,csrf,pid=setup(env)
    t=create_task(c,wid,csrf,pid)
    assert post(c,f'/api/workspaces/{wid}/tasks/{t["id"]}',csrf,{'label_ids':[99999]},'PATCH').status_code==422
    assert post(c,f'/api/workspaces/{wid}/tasks/{t["id"]}',csrf,{'assignee_id':99999},'PATCH').status_code==422

def test_notifications_private(env):
    c,factory=env;wid,csrf=register(c)
    with factory() as db:
        db.add(m.Notification(workspace_id=wid,user_id=1,title='Seu recado',body='Privado'));db.commit()
        nid=db.scalar(select(m.Notification.id))
    wid2,csrf2=register(c,'Bob','bob@example.com','Equipe Segunda')
    assert post(c,f'/api/workspaces/{wid2}/notifications/{nid}',csrf2,{},'PATCH').status_code==404

def test_task_number_sequence_per_project(env):
    c,wid,csrf,pid=setup(env)
    a=create_task(c,wid,csrf,pid);b=create_task(c,wid,csrf,pid)
    assert (a['number'],b['number'])==(1,2)
    p2=post(c,f'/api/workspaces/{wid}/projects',csrf,{'name':'Novo projeto','key':'NV'})
    assert p2.status_code==200
    third=create_task(c,wid,csrf,p2.json()['id'])
    assert third['number']==1

def test_owner_role_is_protected(env):
    c,wid,csrf,pid=setup(env)
    uid=c.get('/api/bootstrap').json()['user']['id']
    assert post(c,f'/api/workspaces/{wid}/members/{uid}',csrf,{'role':'viewer'},'PATCH').status_code==403

def test_no_openapi_docs_by_default(env):
    c,_=env
    assert c.get('/api/docs').status_code==404

def test_github_repo_validation_and_isolation(env):
    c,wid,csrf,pid=setup(env)
    bad=post(c,f'/api/workspaces/{wid}/projects/{pid}/github',csrf,{'repository':'http://internal/private'},'PUT')
    assert bad.status_code==422
    valid=post(c,f'/api/workspaces/{wid}/projects/{pid}/github',csrf,{'repository':'tteukkkk/tradeagile'},'PUT')
    assert valid.status_code==200
    assert c.get(f'/api/workspaces/{wid}/data').json()['integrations'][str(pid)]=='tteukkkk/tradeagile'
    newwid,newcsrf=register(c,'Bob','bob@example.com','Equipe Segunda')
    assert c.get(f'/api/workspaces/{newwid}/projects/{pid}/github/issues').status_code==404

def test_github_import_deduplicates(env,monkeypatch):
    c,wid,csrf,pid=setup(env)
    linked=post(c,f'/api/workspaces/{wid}/projects/{pid}/github',csrf,{'repository':'tteukkkk/demo'},'PUT')
    assert linked.status_code==200
    def dummy(repo,number=None):
        assert repo=='tteukkkk/demo'
        if number is None: return [{'number':7,'title':'Melhorar UX','html_url':'https://github.com/tteukkkk/demo/issues/7'}, {'number':8,'title':'Não importar PR','pull_request':{'url':'x'}}]
        return {'number':number,'title':'Melhorar UX','body':'Descrição vinda do GitHub'}
    monkeypatch.setattr(mod,'github_issue',dummy)
    listed=c.get(f'/api/workspaces/{wid}/projects/{pid}/github/issues')
    assert listed.status_code==200 and len(listed.json()['issues'])==1
    imported=post(c,f'/api/workspaces/{wid}/projects/{pid}/github/issues/7/import',csrf)
    assert imported.status_code==200,imported.text
    assert imported.json()['title']=='Melhorar UX'
    assert post(c,f'/api/workspaces/{wid}/projects/{pid}/github/issues/7/import',csrf).status_code==409
    assert c.get(f'/api/workspaces/{wid}/projects/{pid}/github/issues').json()['issues'][0]['imported'] is True

def test_realtime_websocket_receives_task_edits(env):
    c,wid,csrf,pid=setup(env)
    t=create_task(c,wid,csrf,pid)
    with c.websocket_connect(f'/ws/{wid}') as socket:
        r=post(c,f'/api/workspaces/{wid}/tasks/{t["id"]}',csrf,{'status':'review','version':1},'PATCH')
        assert r.status_code==200
        event=socket.receive_json()
        assert event['kind']=='task_changed' and event['id']==t['id']

# DevFlow account settings patch coverage.
def test_account_profile_updates_persist_and_are_private(env):
    c, factory = env
    wid, csrf = register(c, name='Alice Original')
    payload={'name':'Alice Atualizada','email':'ALICE.NOVA@example.com','avatar_color':'#3b82f6','current_password':'SenhaSegura123'}
    assert c.patch('/api/account/profile',json=payload).status_code == 403  # CSRF
    bad=post(c,'/api/account/profile',csrf,{**payload,'current_password':'incorreta'},'PATCH')
    assert bad.status_code==403
    assert c.get('/api/bootstrap').json()['user']['email']=='alice@example.com'
    good=post(c,'/api/account/profile',csrf,payload,'PATCH')
    assert good.status_code==200,good.text
    assert good.json()['user']['name']=='Alice Atualizada'
    assert good.json()['user']['email']=='alice.nova@example.com'
    assert good.json()['user']['color']=='#3b82f6'
    assert c.get('/api/bootstrap').json()['user']['initials']=='AA'
    assert c.get(f'/api/workspaces/{wid}/data').json()['members'][0]['name']=='Alice Atualizada'
    assert c.post('/api/auth/logout',headers={'x-csrf-token':csrf}).status_code==200
    assert c.post('/api/auth/login',json={'email':'alice@example.com','password':'SenhaSegura123'}).status_code==401
    assert c.post('/api/auth/login',json={'email':'alice.nova@example.com','password':'SenhaSegura123'}).status_code==200
    with factory() as db:
        user=db.scalar(select(m.User).where(m.User.email=='alice.nova@example.com'))
        assert user.avatar_color=='#3b82f6'


def test_account_profile_validations_and_duplicate(env):
    c,_=env
    wid,csrf=register(c)
    c.post('/api/auth/logout',headers={'x-csrf-token':csrf})
    register(c,'Bob','bob@example.com','Equipe Segunda')
    c.post('/api/auth/login',json={'email':'alice@example.com','password':'SenhaSegura123'})
    csrf=c.get('/api/bootstrap').json()['csrf']
    base={'name':'Alice','email':'bob@example.com','avatar_color':'#3b82f6','current_password':'SenhaSegura123'}
    assert post(c,'/api/account/profile',csrf,base,'PATCH').status_code==409
    assert post(c,'/api/account/profile',csrf,{**base,'email':'me@example.com','avatar_color':'transparent'},'PATCH').status_code==422
    assert post(c,'/api/account/profile',csrf,{**base,'email':'me@example.com','name':' '},'PATCH').status_code==422
    assert c.get('/api/bootstrap').json()['user']['email']=='alice@example.com'


def test_password_change_requires_current_and_csrf(env):
    c,_=env
    wid,csrf=register(c)
    patch={'current_password':'SenhaSegura123','new_password':'NovaSenha2026Segura'}
    assert c.post('/api/account/change-password',json=patch).status_code==403
    assert post(c,'/api/account/change-password',csrf,{**patch,'current_password':'wrong'}).status_code==403
    assert post(c,'/api/account/change-password',csrf,{**patch,'new_password':'curta'}).status_code==422
    assert post(c,'/api/account/change-password',csrf,{**patch,'new_password':'SenhaSegura123'}).status_code==422
    success=post(c,'/api/account/change-password',csrf,patch)
    assert success.status_code==200,success.text
    assert c.get('/api/bootstrap').status_code==200
    assert post(c,'/api/auth/logout',csrf).status_code==200
    assert c.post('/api/auth/login',json={'email':'alice@example.com','password':'SenhaSegura123'}).status_code==401
    assert c.post('/api/auth/login',json={'email':'alice@example.com','password':'NovaSenha2026Segura'}).status_code==200
    assert c.get('/api/bootstrap').status_code==200


def test_profile_settings_visible_and_logout_button(env):
    c,_=env
    wid,csrf=register(c)
    html=c.get('/app').text
    assert 'sidebar-logout' in html
    assert 'account-profile-btn' in html
    assert 'account-workspace-btn' in html
    js=c.get('/static/app.js').text
    assert "'/api/account/profile'" in js
    assert "'/api/account/change-password'" in js
    assert 'settings-profile-section' in js


def test_login_page_route_and_legacy_alias(env):
    client, _ = env
    login = client.get('/entrar')
    assert login.status_code == 200
    assert 'devflow' in login.text.lower()
    legacy = client.get('/login', follow_redirects=False)
    assert legacy.status_code == 302
    assert legacy.headers['location'] == '/entrar'
    assert client.get('/login').status_code == 200
