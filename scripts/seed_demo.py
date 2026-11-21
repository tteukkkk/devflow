"""Cria SOMENTE dados fictícios de demonstração, sem excluir registros existentes."""
from pathlib import Path
from datetime import date, timedelta
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from sqlalchemy import select
from devflow.db import Base, engine, SessionLocal
from devflow.models import User,Workspace,Membership,Project,ProjectSequence,Task,Label,TaskLabel,Checklist,Comment,Activity,Notification
from devflow.security import hash_password

Base.metadata.create_all(engine)
db=SessionLocal()
try:
    email='demo@devflow.example.com'
    if db.scalar(select(User).where(User.email==email)):
        print('Conta de demonstração já existe; nada foi sobrescrito.')
        raise SystemExit(0)
    people=[('Matheus Felicio','demo@devflow.example.com','#9062ee','owner'),('Laura Costa','laura@devflow.example.com','#2bb29e','admin'),('Ana Ribeiro','ana@devflow.example.com','#ec956b','member'),('Pedro Lima','pedro@devflow.example.com','#599dea','member')]
    users=[]
    for name,email,color,role in people:
        u=User(name=name,email=email,avatar_color=color,password_hash=hash_password('DemoSeguro#2026'))
        db.add(u);db.flush();users.append(u)
    w=Workspace(name='Studio Polaris',slug='studio-polaris',description='Design, tecnologia e boas ideias em movimento.')
    if db.scalar(select(Workspace).where(Workspace.slug==w.slug)):w.slug='studio-polaris-demo'
    db.add(w);db.flush()
    for u,person in zip(users,people):db.add(Membership(workspace_id=w.id,user_id=u.id,role=person[3]))
    projects=[Project(workspace_id=w.id,name='Plataforma Aurora',key='AUR',description='Uma nova experiência digital do início ao fim.',color='#9268e8'),Project(workspace_id=w.id,name='Website Institucional',key='WEB',description='Presença digital com personalidade.',color='#27b8a6'),Project(workspace_id=w.id,name='Aplicativo Mobile',key='APP',description='O próximo passo da experiência mobile.',color='#ec9b68')]
    db.add_all(projects);db.flush()
    tags=[('Design','#a98cec'),('Frontend','#59a9f3'),('Backend','#32bb9d'),('Bug','#ee8597'),('Produto','#f7b46e'),('UI/UX','#bd84eb')]
    labels=[]
    for name,color in tags:
        t=Label(workspace_id=w.id,name=name,color=color);db.add(t);db.flush();labels.append(t)
    label_map={l.name:l.id for l in labels}
    today=date.today()
    items=[
      (0,'Mapear jornada do usuário','todo','high',2,6,['UI/UX','Design'],3),
      (0,'Construir sistema de autenticação','in_progress','urgent',0,2,['Backend'],6),
      (0,'Criar biblioteca de componentes','in_progress','medium',1,8,['Frontend','Design'],5),
      (0,'Implementar API de usuários','review','high',3,1,['Backend'],4),
      (0,'Definir arquitetura de dados','done','high',0,-3,['Backend'],7),
      (0,'Documentar requisitos de produto','done','low',1,-5,['Produto'],2),
      (0,'Wireframes das telas principais','done','medium',2,-6,['UI/UX'],3),
      (0,'Testes de integração e autenticação','todo','medium',3,10,['Bug','Backend'],5),
      (0,'Validar experiência no mobile','backlog','low',2,14,['UI/UX'],3),
      (0,'Criar onboarding de novos usuários','backlog','medium',0,19,['Produto'],5),
      (1,'Redesenhar página inicial','in_progress','high',1,4,['Design','Frontend'],5),
      (1,'Otimizar carregamento de imagens','todo','medium',3,7,['Frontend'],3),
      (1,'Implementar formulário de contato','review','medium',0,1,['Backend','Frontend'],2),
      (1,'Planejar identidade visual','done','low',1,-9,['Design'],3),
      (1,'Auditar acessibilidade das páginas','todo','high',2,9,['Frontend','Bug'],3),
      (1,'Criar páginas institucionais','done','low',2,-4,['Frontend'],2),
      (2,'Criar protótipo navegável','in_progress','high',2,5,['UI/UX'],5),
      (2,'Construir tela de perfil','todo','medium',3,12,['Frontend'],3),
      (2,'Implementar notificações push','backlog','medium',0,17,['Backend'],8),
      (2,'Definir fluxo de navegação','done','high',1,-7,['Design'],3),
      (2,'Documentar endpoints mobile','review','low',3,2,['Backend'],2),
      (2,'Corrigir comportamento do menu','in_progress','urgent',2,-1,['Bug','Frontend'],3),
      (0,'Integrar busca global','backlog','medium',0,16,['Frontend'],5),
      (1,'Configurar monitoramento de erros','backlog','low',3,21,['Backend'],3),
    ]
    counters={p.id:0 for p in projects}
    for p in projects:db.add(ProjectSequence(project_id=p.id,last_number=0))
    for idx,(pi,title,status,priority,assignee,offset,lbs,points) in enumerate(items):
        p=projects[pi];counters[p.id]+=1
        t=Task(workspace_id=w.id,project_id=p.id,number=counters[p.id],title=title,description=f'Objetivo: {title.lower()}.\n\nCritérios de aceite:\n- Validar cenário principal\n- Registrar evidências\n- Revisar com a equipe',status=status,priority=priority,assignee_id=users[assignee].id,created_by=users[(assignee+1)%4].id,due_date=(today+timedelta(days=offset)).isoformat(),position=idx,estimate=points)
        db.add(t);db.flush()
        for name in lbs:db.add(TaskLabel(task_id=t.id,label_id=label_map[name]))
        if idx in (0,1,2,10,15,16,21):
            db.add(Checklist(task_id=t.id,text='Validar requisitos e contexto',checked=status in ('review','done'),position=0))
            db.add(Checklist(task_id=t.id,text='Implementar solução',checked=status in ('review','done'),position=1))
            db.add(Checklist(task_id=t.id,text='Revisão final com a equipe',checked=status=='done',position=2))
        if idx in (1,2,10,16,21):db.add(Comment(task_id=t.id,user_id=users[1].id,body='Deixei algumas observações no planejamento. Podemos revisar na próxima reunião?'))
        db.add(Activity(workspace_id=w.id,actor_id=users[(assignee+1)%4].id,project_id=p.id,task_id=t.id,verb='created_task',detail=f'{p.key}-{t.number} · {t.title}'))
        if status in ('done','review','in_progress'):db.add(Activity(workspace_id=w.id,actor_id=users[assignee].id,project_id=p.id,task_id=t.id,verb='moved_task',detail=t.title))
        if idx in (1,21):db.add(Notification(workspace_id=w.id,user_id=users[0].id,title='Atualização importante',body=f'{p.key}-{t.number} · {title}',task_id=t.id))
    for p in projects:db.get(ProjectSequence,p.id).last_number=counters[p.id]
    db.commit()
    print(f'Demonstração criada: {len(items)} tarefas, {len(projects)} projetos, {len(users)} pessoas.')
    print('E-mail: demo@devflow.example.com | Senha: DemoSeguro#2026')
finally:db.close()
