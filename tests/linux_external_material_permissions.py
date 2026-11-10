"""Disposable Linux-root syscall rehearsal, synthetic temp files only.

Never installs units/reads target paths. Run explicitly in an approved isolated
Linux environment; unsupported CAP_DAC_READ_SEARCH returns77, never PASS.
"""
import ctypes,json,os,shutil,stat,sys,tempfile
from pathlib import Path
class Header(ctypes.Structure):_fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
class Data(ctypes.Structure):_fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
def child(path,cap,web=False):
 os.setgroups([]);os.setresgid(976,976,976)
 if web:os.setresuid(981,981,981)
 libc=ctypes.CDLL(None,use_errno=True);header=Header(0x20080522,0);data=(Data*2)();data[0].effective=data[0].permitted=cap
 if libc.capset(ctypes.byref(header),data)!=0:os._exit(77)
 try:
  if web:
   try:(path/'signer'/'test-seed').read_bytes()
   except PermissionError:os._exit(0)
   os._exit(1)
  fd=os.open(path/('output-'+str(cap)),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  os.fchown(fd,0,976);os.fchmod(fd,0o640);s=os.fstat(fd);os.close(fd)
  assert (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(0,976,0o640)
  try:raw=(path/'auth.sqlite3').read_bytes();read=True
  except PermissionError:read=False
  assert read==(cap==(1<<2))
  assert (path/'signer'/'test-seed').read_bytes()==b'PUBLIC-SYNTHETIC-ONLY'
  os._exit(0)
 except BaseException:os._exit(1)
def main():
 if sys.platform!='linux' or os.geteuid()!=0:raise SystemExit(77)
 path=Path(tempfile.mkdtemp(prefix='structural-material-permission-'));path.chmod(0o755)
 try:
  db=path/'auth.sqlite3';db.write_bytes(b'PUBLIC-SYNTHETIC-DB');db.chmod(0o600);os.chown(db,981,976)
  (path/'signer').mkdir(mode=0o700);seed=path/'signer'/'test-seed';seed.write_bytes(b'PUBLIC-SYNTHETIC-ONLY');seed.chmod(0o400)
  for cap,web in ((0,False),(1<<2,False),(0,True)):
   pid=os.fork()
   if pid==0:child(path,cap,web)
   _,status=os.waitpid(pid,0);code=os.waitstatus_to_exitcode(status)
   if code!=0:raise SystemExit(code)
  print(json.dumps({'status':'LINUX_SYNTHETIC_PERMISSION_REHEARSAL_PASS','real_materials_read':False}))
 finally:shutil.rmtree(path)
if __name__=='__main__':main()
