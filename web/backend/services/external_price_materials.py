"""Pure stdlib official-price observations; no issuer/crypto/key/app imports."""
import base64,hashlib,json,re
from decimal import Decimal
from html.parser import HTMLParser
URL='https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'
MAX_DOCUMENT=32768
MAX_MATERIAL=65536
TTL=86400
class MaterialError(ValueError):pass
def need(v,code):
 if not v:raise MaterialError(code)
def canonical(d):return (json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def ceiling():
 return {'model':'deepseek-flash','currency':'CNY','scale':6,'max_prompt_tokens':1000000,'max_output_tokens':768,
  'peak_input_miss_ceil_units_per_million':2000000,'peak_output_ceil_units_per_million':8000000,'source_url':URL}
def ceiling_digest():return sha(canonical(ceiling()))
class _Table(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
 def handle_starttag(self,tag,attrs):
  if tag=='tr':self.row=[]
  if tag in ('td','th'):self.cell=[]
 def handle_data(self,data):
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag in ('td','th') and self.cell is not None:
   if self.row is not None:self.row.append(''.join(self.cell).strip())
   self.cell=None
  if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None

def parse_official_document(raw):
 need(type(raw) is bytes and 0<len(raw)<=MAX_DOCUMENT,'official_document_bound')
 parser=_Table();parser.feed(raw.decode('utf-8','strict'));rows=parser.rows
 headers=[r for r in rows if r and r[0]=='模型'];need(len(headers)==1 and len(headers[0])==3
  and re.fullmatch(r'deepseek-flash(?:\(\d+\))?',headers[0][1]) is not None,'official_model_table')
 versions=[r for r in rows if r and r[0]=='模型版本'];need(len(versions)==1 and len(versions[0])==3
  and 0<len(versions[0][1])<=100,'official_model_version')
 base=[r for r in rows if r and r[0]=='BASE URL (OpenAI 格式)'];need(base==[['BASE URL (OpenAI 格式)','https://api.deepseek.com']],'official_base')
 context=[r for r in rows if r and r[0]=='上下文长度'];need(context==[['上下文长度','1M']],'official_context')
 found={};metric=None
 for row in rows:
  joined=' '.join(row)
  if '百万tokens输入（缓存未命中）' in row:metric='input'
  elif '百万tokens输入（缓存命中）' in row:metric='cache'
  elif '百万tokens输出' in row:metric='output'
  if row and row[0]=='高峰时段' and metric in ('input','output'):
   need(metric not in found and len(row)==3 and re.fullmatch(r'[0-9]+(?:\.[0-9]{1,6})?元',row[1]) is not None,'official_peak_price')
   amount=Decimal(row[1][:-1])*1000000
   need(amount==int(amount) and 0<int(amount)<=1000000000,'official_price_units');found[metric]=int(amount)
 need(set(found)=={'input','output'},'official_peak_prices_missing')
 return {'actual_peak_input_miss_units_per_million':found['input'],'actual_peak_output_units_per_million':found['output'],
  'provider_model_version':versions[0][1]}

def observe_document(raw,*,now,ttl=TTL):
 need(type(now) is int and now>0 and type(ttl) is int and 1<=ttl<=TTL,'observation_time')
 actual=parse_official_document(raw);facts=ceiling()
 status='valid' if actual['actual_peak_input_miss_units_per_million']<=facts['peak_input_miss_ceil_units_per_million'] and actual['actual_peak_output_units_per_million']<=facts['peak_output_ceil_units_per_million'] else 'closed'
 return {'schema':'external-price-observation-v1','status':status,'ceiling':facts,'ceiling_sha256':ceiling_digest(),
  'official_document_b64':base64.b64encode(raw).decode('ascii'),
  'observation':actual|{'official_document_sha256':sha(raw),'issued_at':now,'valid_until':now+ttl}}

def closed_material(reason,*,now):
 need(reason in ('missing','observation_failed','over_ceiling','configuration_unbound'),'closed_reason')
 return {'schema':'external-price-observation-v1','status':'closed','reason':reason,'issued_at':now}

def validate_observation(raw,expected_ceiling,*,now,upper_units):
 need(type(raw) is bytes and 0<len(raw)<=MAX_MATERIAL,'price_material_bound')
 def unique(pairs):
  d={}
  for k,v in pairs:need(k not in d,'price_duplicate_key');d[k]=v
  return d
 material=json.loads(raw,object_pairs_hook=unique)
 need(type(material) is dict and material.get('status')=='valid','price_material_closed')
 need(set(material)=={'schema','status','ceiling','ceiling_sha256','official_document_b64','observation'}
  and material['schema']=='external-price-observation-v1' and material['ceiling']==ceiling()
  and material['ceiling_sha256']==expected_ceiling==ceiling_digest(),'price_ceiling_unbound')
 need(type(material['official_document_b64']) is str and len(material['official_document_b64'])<=4*((MAX_DOCUMENT+2)//3),'price_document_encoding')
 document=base64.b64decode(material['official_document_b64'],validate=True);actual=parse_official_document(document)
 obs=material['observation'];need(type(obs) is dict and set(obs)==set(actual)|{'official_document_sha256','issued_at','valid_until'},'price_observation_shape')
 need(all(obs[k]==v for k,v in actual.items()) and obs['official_document_sha256']==sha(document),'mixed_price_snapshot')
 need(type(now) is int and type(obs['issued_at']) is int and type(obs['valid_until']) is int
  and obs['issued_at']<=now<obs['valid_until']<=obs['issued_at']+TTL,'price_observation_expired')
 need(actual['actual_peak_input_miss_units_per_million']<=ceiling()['peak_input_miss_ceil_units_per_million']
  and actual['actual_peak_output_units_per_million']<=ceiling()['peak_output_ceil_units_per_million'],'price_observed_over_ceiling')
 cost=(1000000*actual['actual_peak_input_miss_units_per_million']+768*actual['actual_peak_output_units_per_million']+999999)//1000000
 ceil_cost=(1000000*ceiling()['peak_input_miss_ceil_units_per_million']+768*ceiling()['peak_output_ceil_units_per_million']+999999)//1000000
 need(type(upper_units) is int and 1<=upper_units<=2129920 and ceil_cost<=upper_units and cost<=upper_units,'price_upper_insufficient')
 return {'valid_until':obs['valid_until'],'max_prompt_tokens':1000000,'actual_upper_units':cost,'observation_sha256':sha(raw)}
