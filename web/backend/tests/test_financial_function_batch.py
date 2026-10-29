"""Cold full-module verification controls; no financial execution or authority."""
import ast
import builtins
import os
from pathlib import Path
import struct
import sys
import types

import pytest
from web.backend.research import financial_execution as execution

BASE='''def f():
 raise AssertionError('not called')
def g():
 raise AssertionError('not called')
def h():
 raise AssertionError('not called')
class Gate:
 def a(self):
  raise AssertionError('not called')
 @staticmethod
 def b():
  raise AssertionError('not called')
'''


@pytest.fixture
def native_source(tmp_path,monkeypatch):
    path=tmp_path/'synthetic.py';path.write_text(BASE)
    module=types.ModuleType('_financial_batch_synthetic');module.__file__=str(path)
    exec(compile(BASE,str(path),'exec',dont_inherit=True),vars(module))
    module.bridge=module.f
    monkeypatch.setitem(sys.modules,module.__name__,module)
    monkeypatch.setattr(execution,'__file__',str(tmp_path/'research/financial_execution.py'))
    monkeypatch.setattr(execution,'_FUNCTION_PATHS',{q:'synthetic.py' for q in ('f','g','h','Gate.a','Gate.b')})
    return module,path


def references(module):return ((module,'bridge','f'),(module,'g','g'))


def test_alias_and_plain_static_class_members_and_repeated_batch_compile(native_source,monkeypatch):
    module,path=native_source;calls=[];native_compile=builtins.compile
    def full_compile(raw,filename,mode,**kwargs):
        calls.append((raw,filename,mode,kwargs));return native_compile(raw,filename,mode,**kwargs)
    monkeypatch.setattr(execution,'compile',full_compile,raising=False)
    assert execution._same_source_functions(*references(module))==(module.f,module.g)
    assert len(calls)==1 and calls[0]==(path.read_bytes(),str(path),'exec',{'dont_inherit':True})
    assert execution._same_source_functions((module.Gate,'a','Gate.a',module.Gate.a),(module.Gate,'b','Gate.b',module.Gate.b))==(module.Gate.a,module.Gate.b)
    assert len(calls)==2
    assert execution._same_source_functions((module,'f','f'),(module,'g','g'),(module,'h','h'))==(module.f,module.g,module.h)
    assert len(calls)==3


@pytest.mark.parametrize('kind',['bytes','generation','inode','live_during_read','live_before_second_lookup'])
def test_each_member_reads_fresh_source_and_live_referent(native_source,monkeypatch,kind):
    module,path=native_source;original=Path.read_bytes;reads=[];old=module.g
    def changed_read(candidate):
        if candidate!=path:return original(candidate)
        reads.append(True)
        if kind=='live_before_second_lookup' and len(reads)==1:
            module.g=types.FunctionType(old.__code__,vars(module),'g')
        if len(reads)==2:
            if kind=='bytes':candidate.write_text(BASE+'# changed\n')
            elif kind=='generation':
                info=candidate.stat();os.utime(candidate,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
            elif kind=='inode':
                other=candidate.with_suffix('.replacement');other.write_text(BASE);other.replace(candidate)
            elif kind=='live_during_read':module.g=types.FunctionType(old.__code__,vars(module),'g')
        return original(candidate)
    monkeypatch.setattr(Path,'read_bytes',changed_read)
    if kind=='live_before_second_lookup':
        result=execution._same_source_functions(*references(module))
        assert result[1] is module.g and result[1] is not old
    else:
        with pytest.raises(PermissionError):execution._same_source_functions(*references(module))
    assert len(reads)==2


@pytest.mark.parametrize('kind',['globals','module','alias','filename','expected','mixed_source','property','callback','coldcode','mutable_ref','empty','module_name_callback','class_for_top_function','metaclass'])
def test_closed_locator_rejects_stale_or_user_behavior(native_source,monkeypatch,kind):
    module,path=native_source;refs=references(module);called=[]
    if kind=='globals':module.g=types.FunctionType(module.g.__code__,dict(vars(module)),'g')
    elif kind=='module':monkeypatch.setitem(sys.modules,module.__name__,types.ModuleType(module.__name__))
    elif kind=='alias':module.bridge=module.g
    elif kind=='filename':
        full=compile(BASE,str(path.parent)+'/./'+path.name,'exec',dont_inherit=True)
        code=next(x for x in full.co_consts if type(x) is types.CodeType and x.co_name=='g')
        module.g=types.FunctionType(code,vars(module),'g')
    elif kind=='expected':
        old=module.g;module.g=types.FunctionType(old.__code__,vars(module),'g');refs=(refs[0],(module,'g','g',old))
    elif kind=='mixed_source':
        other=types.ModuleType('_financial_batch_other');other.__file__=str(path.with_name('other.py'));Path(other.__file__).write_text('def other():\n return None\n');exec(compile(Path(other.__file__).read_bytes(),other.__file__,'exec',dont_inherit=True),vars(other));monkeypatch.setitem(sys.modules,other.__name__,other);execution._FUNCTION_PATHS['other']='other.py';refs=(refs[0],(other,'other','other'))
    elif kind=='property':
        def forbidden(self):called.append(True);raise AssertionError('property called')
        module.Gate.b=property(forbidden);refs=((module.Gate,'a','Gate.a'),(module.Gate,'b','Gate.b'))
    elif kind=='callback':refs=(lambda:called.append(True),refs[1])
    elif kind=='coldcode':refs=(compile('pass','<cold>','exec'),refs[1])
    elif kind=='mutable_ref':refs=(list(refs[0]),refs[1])
    elif kind=='empty':refs=()
    elif kind=='class_for_top_function':
        old=module.f;module.f=type('f',(),{'__module__':module.__name__,'__qualname__':'f','a':staticmethod(old)})
        refs=((module.f,'a','f'),refs[1])
    elif kind=='module_name_callback':
        class Poison:
            def __eq__(self,other):called.append(True);raise AssertionError('comparison called')
            def __hash__(self):called.append(True);raise AssertionError('hash called')
        module.__name__=Poison();refs=((module.Gate,'a','Gate.a'),(module.Gate,'b','Gate.b'))
    else:
        class Meta(type):
            def __getattribute__(self,name):called.append(True);raise AssertionError('metaclass called')
        value=Meta('Gate',(),{});refs=((value,'a','Gate.a'),refs[1])
    with pytest.raises((PermissionError,TypeError)):execution._same_source_functions(*refs)
    assert called==[]


INVALID={
 'duplicate_args':'def unrelated(x,x):\n pass\n',
 'async_generator_return':'async def unrelated():\n yield 1\n return 2\n',
 'module_return':'return 1\n','module_break':'break\n','module_yield':'yield 1\n',
 'module_await':'await f()\n','late_future':'x=1\nfrom __future__ import annotations\n',
 'unknown_future':'from __future__ import missing_feature\n',
 'nonlocal':'def unrelated():\n nonlocal absent\n','debug_assignment':'__debug__=False\n',
 'except_star_return':'def unrelated():\n try: pass\n except* Exception:\n  return 1\n',
}
@pytest.mark.parametrize('kind',INVALID)
def test_full_module_compile_preserves_original_syntax_rejection_domain(native_source,kind):
    module,path=native_source;raw=INVALID[kind]+BASE;path.write_text(raw)
    with pytest.raises(SyntaxError):compile(raw,str(path),'exec',dont_inherit=True)
    with pytest.raises(SyntaxError):execution._same_source_functions(*references(module))


def test_twenty_six_whitelist_targets_full_code_fields_and_nested_constants_are_exact(monkeypatch):
    root=Path(execution.__file__).resolve().parents[1];nested=0
    def codes(code):
        yield code
        for value in code.co_consts:
            if type(value) is types.CodeType:yield from codes(value)
    def same(left,right):
        count=0
        for name in dir(left):
            if name.startswith('co_') and name not in ('co_consts','co_lines','co_positions'):
                assert getattr(left,name)==getattr(right,name)
        assert tuple(left.co_lines())==tuple(right.co_lines()) and tuple(left.co_positions())==tuple(right.co_positions())
        for a,b in zip(left.co_consts,right.co_consts):
            assert type(a) is type(b)
            if type(a) is types.CodeType:count+=1+same(a,b)
            elif type(a) is float:assert struct.pack('!d',a)==struct.pack('!d',b)
            elif type(a) is complex:assert struct.pack('!dd',a.real,a.imag)==struct.pack('!dd',b.real,b.imag)
            else:assert a==b
        assert len(left.co_consts)==len(right.co_consts) and left==right
        return count
    assert len(execution._FUNCTION_PATHS)==26 and len(set(execution._FUNCTION_PATHS.values()))==11
    native_compile=builtins.compile;compiled=[]
    def capture(raw,filename,mode,**kwargs):
        result=native_compile(raw,filename,mode,**kwargs);compiled.append((raw,filename,result));return result
    monkeypatch.setattr(execution,'compile',capture,raising=False)
    for index,(name,relative) in enumerate(execution._FUNCTION_PATHS.items()):
        path=root/relative;raw=path.read_bytes();first=native_compile(raw,str(path),'exec',dont_inherit=True)
        selected=tuple(x for x in codes(first) if x.co_qualname==name);assert len(selected)==1
        module=types.ModuleType('_financial_code_ledger_'+str(index));module.__file__=str(path)
        monkeypatch.setitem(sys.modules,module.__name__,module)
        assert selected[0].co_freevars==()
        function=types.FunctionType(selected[0],vars(module),selected[0].co_name)
        if '.' in name:
            owner,member=name.rsplit('.',1)
            container=type(owner,(),{'__module__':module.__name__,'__qualname__':owner,member:staticmethod(function)})
            vars(module)[owner]=container
        else:container=module;member=name;vars(module)[member]=function
        assert execution._function(function) is function
        compiled.clear()
        result=execution._same_source_functions((container,member,name),(container,member,name))
        assert result==(function,function) and len(compiled)==1
        assert compiled[0][:2]==(raw,str(path))
        candidate=tuple(x for x in codes(compiled[0][2]) if x.co_qualname==name)
        assert len(candidate)==1;nested+=same(function.__code__,candidate[0])
    assert nested==56
