"""Actual systemd directory modes with public synthetic seed bytes only."""
import ast,os,stat,types,unittest
from pathlib import Path
H=Path(__file__).resolve().parents[1]
source=(H/'scripts/maintain-external-live-materials.py').read_text();node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='read_signer_seed');code=compile(ast.Module(body=[node],type_ignores=[]),'reviewed-read_signer_seed','exec')
class Rejected(ValueError):pass
class FakePath:
 def __init__(self,name,mode,uid=0,physical=True):self.name,self.mode,self.uid,self.physical=name,mode,uid,physical;self.parents=()
 def __str__(self):return self.name
 def resolve(self,strict=True):return self if self.physical else object()
 def stat(self,follow_symlinks=False):return types.SimpleNamespace(st_mode=stat.S_IFDIR|self.mode,st_uid=self.uid)
 def __truediv__(self,name):return self.name+'/'+name
class Tests(unittest.TestCase):
 def run_case(self,mode=0o500,readonly=True,uid=0,physical=True,envok=True,seedlen=32):
  path=FakePath('/run/credentials/structural-external-startup-material.service',mode,uid,physical);path.parents=(FakePath('/run/credentials',0o755),FakePath('/run',0o755),FakePath('/',0o755))
  reads=[]
  def need(ok,code):
   if not ok:raise Rejected(code)
  def fixed(p,cap,**kwargs):reads.append((p,cap,kwargs));return b'X'*seedlen
  materials=types.SimpleNamespace(SIGNER_DIRECTORY=path,SIGNER_ID='structural-external-first-answer-startup-signing-key',need=need,fixed_file=fixed)
  fakeos=types.SimpleNamespace(environ={'CREDENTIALS_DIRECTORY':str(path) if envok else '/other'},ST_RDONLY=os.ST_RDONLY,statvfs=lambda p:types.SimpleNamespace(f_flag=os.ST_RDONLY if readonly else 0))
  scope={'materials':materials,'os':fakeos,'stat':stat};exec(code,scope);return scope['read_signer_seed'],reads
 def test_systemd_private_readonly500_and_legacy700(self):
  for mode in (0o500,0o700):
   fn,reads=self.run_case(mode=mode);self.assertEqual(fn(),bytearray(b'X'*32));self.assertEqual(reads[0][1:],(32,{'mode':0o400}))
 def test_nonprivate_or_missing_execute_modes_before_secret_access(self):
  for mode in (0o400,0o550,0o555,0o600,0o750,0o755,0o770,0o777):
   fn,reads=self.run_case(mode=mode)
   with self.subTest(mode=oct(mode)),self.assertRaises(Rejected):fn()
   self.assertEqual(reads,[])
 def test_writable_mount_foreign_owner_symlink_and_wrong_directory_rejected_before_read(self):
  for change in ({'readonly':False},{'uid':981},{'physical':False},{'envok':False}):
   fn,reads=self.run_case(**change)
   with self.subTest(change=change),self.assertRaises(Rejected):fn()
   self.assertEqual(reads,[])
 def test_seed_length_contract_unchanged(self):
  for n in (0,31,33,64):
   fn,_=self.run_case(seedlen=n)
   with self.subTest(length=n),self.assertRaises(Rejected):fn()
if __name__=='__main__':unittest.main(verbosity=2)
