import re, secrets, hashlib, os
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import HTTPException
from starlette.requests import Request

ph=PasswordHasher(time_cost=2,memory_cost=32768,parallelism=2)
ROLES={'owner':4,'admin':3,'member':2,'viewer':1}
STATUSES={'backlog','todo','in_progress','review','done'}
PRIORITIES={'none','low','medium','high','urgent'}

def hash_password(s): return ph.hash(s)
def valid_password(p):
    if len(p)<10 or len(p)>128 or not re.search('[A-Za-z]',p) or not re.search('[0-9]',p):
        raise HTTPException(422,'A senha precisa ter 10 a 128 caracteres, incluindo letras e números.')

def verify_password(p,h):
    try: return ph.verify(h,p)
    except (VerifyMismatchError,VerificationError): return False

def require_csrf(request:Request):
    val=request.session.get('csrf')
    incoming=request.headers.get('x-csrf-token','')
    if not val or not secrets.compare_digest(incoming,val):
        raise HTTPException(403,'Token CSRF inválido. Atualize a página.')

def init_csrf(request):
    if not request.session.get('csrf'): request.session['csrf']=secrets.token_urlsafe(28)
    return request.session['csrf']

def clean(s, n=250):
    if not isinstance(s,str): return ''
    return s.strip()[:n]

def slugify(s):
    import unicodedata
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode('ascii').lower()
    return re.sub('-+','-',re.sub('[^a-z0-9]+','-',s)).strip('-')[:60] or 'equipe'
