"""Actual minimal SMIC page-9 bbox DATA, never an origin/permission receipt.
The whole original PDF and whole bbox digests are separate from fixture hash.
No raw PDF, whole financial report, private path or source permission is copied.
"""
from copy import deepcopy
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import traceback
import pytest
from research.source_adapters import corporate_locations as loc
RAW_DIGEST="64901d4c50f4dabbc120a6b6ced4da73eafc0472821dca6ed3623c0b773a4854"
SOURCE_BBOX_DIGEST="fa7a0eca33288208e1df0c6e67c3d403ff24d6ae08d2b16894ed567142cef957"
EXTRACTOR="poppler-26.04.0-bbox-layout-research"
_PAGE9_LINES = [(['42.240000', '49.128720', '549.543880', '58.341720'],
  [(['42.240000', '49.128720', '105.934200', '58.341720'], 'CONDENSED'),
   (['108.822600', '49.128720', '187.735680', '58.341720'], 'CONSOLIDATED'),
   (['190.504560', '49.128720', '250.941840', '58.341720'], 'STATEMENT'),
   (['253.860120', '49.128720', '267.724440', '58.341720'], 'OF'),
   (['270.650000', '49.128720', '307.312760', '58.341720'], 'PROFIT'),
   (['310.221080', '49.128720', '325.190960', '58.341720'], 'OR'),
   (['327.959840', '49.128720', '354.513200', '58.341720'], 'LOSS'),
   (['357.242240', '49.128720', '378.327560', '58.341720'], 'AND'),
   (['381.190000', '49.128720', '416.209360', '58.341720'], 'OTHER'),
   (['418.978240', '49.128720', '506.825440', '58.341720'], 'COMPREHENSIVE'),
   (['509.554480', '49.128720', '549.543880', '58.341720'], 'INCOME')]),
 (['257.210000', '60.378000', '334.781000', '68.703000'],
  [(['257.210000', '60.378000', '267.713000', '68.703000'], '(In'),
   (['270.260000', '60.378000', '287.765000', '68.703000'], 'US$'),
   (['290.294000', '60.378000', '334.781000', '68.703000'], 'thousands)')]),
 (['384.190000', '94.718000', '503.251000', '103.043000'],
  [(['384.190000', '94.718000', '398.725000', '103.043000'], 'For'),
   (['401.227000', '94.718000', '414.727000', '103.043000'], 'the'),
   (['417.274000', '94.718000', '439.207000', '103.043000'], 'three'),
   (['441.736000', '94.718000', '474.199000', '103.043000'], 'months'),
   (['476.746000', '94.718000', '503.251000', '103.043000'], 'ended')]),
 (['366.670000', '107.918000', '430.768000', '116.243000'],
  [(['366.670000', '107.918000', '393.256000', '116.243000'], 'March'),
   (['395.686000', '107.918000', '408.250000', '116.243000'], '31,'),
   (['410.779000', '107.918000', '430.768000', '116.243000'], '2026')]),
 (['463.060000', '107.918000', '544.078000', '116.243000'],
  [(['463.060000', '107.918000', '506.602000', '116.243000'], 'December'),
   (['509.104000', '107.918000', '521.668000', '116.243000'], '31,'),
   (['524.089000', '107.918000', '544.078000', '116.243000'], '2025')]),
 (['37.440000', '146.918000', '73.494000', '155.243000'],
  [(['37.440000', '146.918000', '73.494000', '155.243000'], 'Revenue')]),
 (['37.440000', '263.708000', '123.462000', '272.033000'],
  [(['37.440000', '263.708000', '58.527000', '272.033000'], 'Profit'),
   (['61.056000', '263.708000', '78.984000', '272.033000'], 'from'),
   (['81.441000', '263.708000', '123.462000', '272.033000'], 'operations')]),
 (['37.440000', '315.428000', '121.482000', '323.753000'],
  [(['37.440000', '315.428000', '60.939000', '323.753000'], 'Profit'),
   (['63.468000', '315.428000', '75.465000', '323.753000'], 'for'),
   (['77.967000', '315.428000', '91.503000', '323.753000'], 'the'),
   (['94.032000', '315.428000', '121.482000', '323.753000'], 'period')]),
 (['287.090000', '792.888720', '304.826680', '802.101720'],
  [(['287.090000', '792.888720', '290.406680', '802.101720'], '-'),
   (['293.210000', '792.888720', '298.747760', '802.101720'], '9'),
   (['301.510000', '792.888720', '304.826680', '802.101720'], '-')]),
 (['390.670000', '146.918000', '430.783000', '155.243000'],
  [(['390.670000', '146.918000', '430.783000', '155.243000'], '2,505,487')]),
 (['398.110000', '263.708000', '430.681000', '272.033000'],
  [(['398.110000', '263.708000', '430.681000', '272.033000'], '247,792')]),
 (['398.110000', '315.428000', '430.681000', '323.753000'],
  [(['398.110000', '315.428000', '430.681000', '323.753000'], '230,912')]),
 (['503.980000', '146.918000', '544.093000', '155.243000'],
  [(['503.980000', '146.918000', '544.093000', '155.243000'], '2,488,710')]),
 (['511.420000', '263.708000', '543.991000', '272.033000'],
  [(['511.420000', '263.708000', '543.991000', '272.033000'], '298,620')]),
 (['511.420000', '315.428000', '543.991000', '323.753000'],
  [(['511.420000', '315.428000', '543.991000', '323.753000'], '203,375')])]

def box(values):return dict(zip(("x_min","y_min","x_max","y_max"),values))

def fixture_data():
    return {"schema_version":"corporate-bbox-data-v1","profile":loc.PROFILE,"raw_digest":RAW_DIGEST,
        "source_bbox_digest":SOURCE_BBOX_DIGEST,"extractor_revision":EXTRACTOR,"source_page_count":13,
        "pages":[{"page_index":9,"width":"595.320000","height":"841.920000","lines":[
            {"box":box(b),"words":[{"box":box(wb),"text":text} for wb,text in words]} for b,words in _PAGE9_LINES]}]}

def content_digest(data):return hashlib.sha256(loc.canonical(data)).hexdigest()

def parse(data,**overrides):
    args=dict(expected_raw_digest=RAW_DIGEST,expected_source_bbox_digest=SOURCE_BBOX_DIGEST,
        expected_bbox_digest=content_digest(data),expected_extractor_revision=EXTRACTOR);args.update(overrides)
    return loc.parse_corporate_bbox(data,**args)

def line(data,text):return next(v for v in data["pages"][0]["lines"] if " ".join(w["text"] for w in v["words"])==text)

def single(data,old,new):line(data,old)["words"][0]["text"]=new

def move(target,**coords):
    target["box"].update(coords);target["words"][0]["box"].update(coords)

def assert_span(text,location):
    start,end=location["span"];assert text[start:end]==location["quote"]


def test_actual_minimal_bbox_values_units_period_and_offsets():
    result=parse(fixture_data()).data()
    assert [f["metric"] for f in result["facts"]]==["revenue","operating_profit","net_profit"]
    assert [f["value"] for f in result["facts"]]==["2505487","247792","230912"]
    assert all(f["currency"]=="USD" and f["unit"]=="thousand" and f["entity_scope"]=="group" for f in result["facts"])
    assert all(f["period"]=={"start":"2026-01-01","end":"2026-03-31","label":"March 31, 2026"} for f in result["facts"])
    assert result["source_bbox_digest"]==SOURCE_BBOX_DIGEST!=result["bbox_data_digest"]
    assert result["raw_digest"]==RAW_DIGEST and result["extraction_scope"]=="provided_bbox_only"
    assert result["provided_page_indices"]==[9] and result["source_page_count"]==13
    text=result["extracted_text"]
    assert hashlib.sha256(text.encode()).hexdigest()==result["extraction_digest"]
    assert "- 9 -" in text and "-9-" not in text and not text.endswith("\n")
    for fact in result["facts"]:
        where=fact["locator"]
        assert where["page_index"]==9 and where["printed_page_label"]=="- 9 -"
        assert where["printed_page_label"]==where["page_footer"]["quote"]
        for key in ("table_heading","unit_heading","period_heading","row_label","period_column","comparison_column","page_footer","value_cell"):
            assert_span(text,where[key])
    where=result["facts"][0]["locator"]
    assert where["value_cell"]["box"]["x_max"]=="430.783000"
    assert where["period_column"]["box"]["x_max"]=="430.768000"


def test_deterministic_sort_and_copy_readback():
    data=fixture_data();baseline=parse(data).data();data["pages"][0]["lines"].reverse()
    for row in data["pages"][0]["lines"]:row["words"].reverse()
    result=parse(data);changed=result.data()
    assert changed["extracted_text"]==baseline["extracted_text"]
    assert changed["facts"]==baseline["facts"] and changed["extraction_digest"]==baseline["extraction_digest"]
    changed["facts"][0]["value"]="forged"
    assert result.data()["facts"][0]["value"]=="2505487" and "Revenue" not in repr(result)


@pytest.mark.parametrize("old,new,value,reason",[("247,792","(247,792)","-247792",None),
    ("230,912","0","0",None),("2,505,487","—",None,"explicit_dash"),("247,792","-",None,"explicit_dash")])
def test_negative_zero_and_explicit_dash_only(old,new,value,reason):
    data=fixture_data();single(data,old,new);result=parse(data).data()
    fact=next(f for f in result["facts"] if f["raw_literal"]==new)
    assert fact["value"]==value and fact["missing_reason"]==reason
    assert_span(result["extracted_text"],fact["locator"]["value_cell"])


@pytest.mark.parametrize("field",["expected_raw_digest","expected_bbox_digest","expected_source_bbox_digest"])
@pytest.mark.parametrize("bad",[None,True,"x"*64,"b"*64])
def test_independent_digest_domains(field,bad):
    with pytest.raises(loc.CorporateParseError) as err:parse(fixture_data(),**{field:bad})
    assert err.value.reason=="digest"


@pytest.mark.parametrize("label",[loc.TITLE,loc.UNIT,loc.PERIOD,loc.CURRENT,loc.PREVIOUS,"Revenue","Profit from operations","Profit for the period","2,488,710"])
def test_missing_required_table_element_is_whole_failure(label):
    data=fixture_data();data["pages"][0]["lines"].remove(line(data,label))
    with pytest.raises(loc.CorporateParseError) as err:parse(data)
    assert err.value.reason=="ambiguous"


@pytest.mark.parametrize("bad",["", " ", "2,505,487*", "2,505,487¹", "2,50,487", "2 505 487", "−247,792", "２５０５４８７",
    "1e3", "NaN", "(-2)", "1/2", "https://example.invalid/private", "<script>alert(1)</script>", "197,448 group"])
def test_rehashed_number_glyph_footnote_and_code_ambiguities(bad):
    data=fixture_data();single(data,"2,505,487",bad)
    with pytest.raises(loc.CorporateParseError):parse(data)


@pytest.mark.parametrize("mutation",["unit","period","date_swap","duplicate_row","duplicate_value","footnote",
    "blank","cross350","cross448","center350","center448","previous_into_current","y_shift","page_width","page_index","bad_box","footer"])
def test_fixed_geometry_labels_periods_and_boundaries(mutation):
    data=fixture_data();page=data["pages"][0];cell=line(data,"2,505,487")
    if mutation=="unit":line(data,loc.UNIT)["words"][2]["text"]="millions)"
    elif mutation=="period":line(data,loc.PERIOD)["words"][2]["text"]="six"
    elif mutation=="date_swap":
        a=line(data,loc.CURRENT);b=line(data,loc.PREVIOUS);a["words"],b["words"]=b["words"],a["words"]
    elif mutation=="duplicate_row":page["lines"].append(deepcopy(line(data,"Revenue")))
    elif mutation=="duplicate_value":page["lines"].append(deepcopy(cell))
    elif mutation=="footnote":
        extra=deepcopy(cell);move(extra,x_min="432.000000",x_max="435.000000");extra["words"][0]["text"]="1";page["lines"].append(extra)
    elif mutation=="blank":cell["words"]=[]
    elif mutation=="cross350":move(cell,x_min="349.000000",x_max="360.000000")
    elif mutation=="cross448":move(cell,x_min="440.000000",x_max="449.000000")
    elif mutation=="center350":move(cell,x_min="345.000000",x_max="355.000000")
    elif mutation=="center448":move(cell,x_min="444.000000",x_max="452.000000")
    elif mutation=="previous_into_current":move(line(data,"2,488,710"),x_min="432.000000",x_max="445.000000")
    elif mutation=="y_shift":move(cell,y_min="146.919000",y_max="155.244000")
    elif mutation=="page_width":page["width"]="596.000000"
    elif mutation=="page_index":page["page_index"]=8
    elif mutation=="footer":line(data,"- 9 -")["words"][1]["text"]="９"
    else:move(cell,x_max="9999")
    with pytest.raises(loc.CorporateParseError):parse(data)


@pytest.mark.parametrize("mutation",["extra","nested_extra","float","bool","control","nan","duplicate_json","depth","too_large","too_many_pages","revision","surrogate"])
def test_strict_json_bounds_fields_and_versions(mutation):
    data=fixture_data()
    if mutation=="extra":data["trusted"]=True
    elif mutation=="nested_extra":data["pages"][0]["lines"][0]["words"][0]["script"]="code"
    elif mutation=="float":data["pages"][0]["width"]=595.32
    elif mutation=="bool":data["source_page_count"]=True
    elif mutation=="control":single(data,"2,505,487","2,505\u200b,487")
    elif mutation=="nan":data=b'{"n":NaN}'
    elif mutation=="duplicate_json":data=b'{"profile":1,"profile":2}'
    elif mutation=="depth":
        node=data
        for _ in range(20):node["extra"]={};node=node["extra"]
    elif mutation=="too_large":data=b' '*(loc.INPUT_CAP+1)
    elif mutation=="too_many_pages":data["source_page_count"]=201
    elif mutation=="surrogate":single(data,"2,505,487","\ud800")
    else:data["extractor_revision"]="unreviewed"
    with pytest.raises(loc.CorporateParseError):
        if isinstance(data,bytes) or mutation=="surrogate":
            loc.parse_corporate_bbox(data,expected_raw_digest=RAW_DIGEST,expected_bbox_digest="a"*64,
                expected_source_bbox_digest=SOURCE_BBOX_DIGEST,expected_extractor_revision=EXTRACTOR)
        else:parse(data)


@pytest.mark.parametrize("caller",["value","json"])
@pytest.mark.parametrize("action",["digest","schema","cell"])
def test_private_exception_real_slots_and_fixed_safe_error(caller,action):
    canary="PRIVATE-CORPORATE-CANARY"
    try:
        if caller=="value":raise ValueError(canary)
        json.loads(canary)
    except ValueError:
        data=fixture_data()
        if action=="schema":data["private"]=canary
        if action=="cell":single(data,"2,505,487",canary)
        with pytest.raises(loc.CorporateParseError) as stopped:
            parse(data,**({"expected_raw_digest":canary} if action=="digest" else {}))
        safe=stopped.value
        assert BaseException.__dict__["__context__"].__get__(safe) is None
        assert BaseException.__dict__["__cause__"].__get__(safe) is None and safe.__suppress_context__ is False
        assert canary not in str(safe)+repr(vars(safe))+"".join(traceback.format_exception(type(safe),safe,safe.__traceback__))


@pytest.mark.parametrize("count",[300,2100])
def test_real_text_and_output_byte_limits(count):
    data=fixture_data()
    for i in range(count):
        item=deepcopy(line(data,"2,505,487"))
        y=Decimal(600)+Decimal(i)/1000
        move(item,x_min="1",x_max="300",y_min=str(y),y_max=str(y+Decimal("0.0005")))
        item["words"][0]["text"]="观"*200
        data["pages"][0]["lines"].append(item)
    with pytest.raises(loc.CorporateParseError) as err:parse(data)
    assert err.value.reason=="resource"


def test_no_io_source_factories_or_implicit_authority():
    with patch("socket.socket",side_effect=AssertionError("no network")),patch("subprocess.Popen",side_effect=AssertionError("no exec")),patch("sqlite3.connect",side_effect=AssertionError("no DB")):
        result=parse(fixture_data()).data()
        assert result["facts"][2]["value"]=="230912"
    assert not any(k in result for k in ("trusted","authorization_verified","execution_attested","may_send_to_provider","source_id"))
    tree=ast.parse(Path(loc.__file__).read_text());modules=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):modules.update(v.name for v in node.names)
        if isinstance(node,ast.ImportFrom):modules.add(node.module)
    assert modules=={"dataclasses","decimal","hashlib","json","re","unicodedata"}


# Actual attributable-to-parent row, distinct from group net profit.
_PARENT_LINES = [(['42.480000', '434.008000', '139.536000', '442.333000'],
  [(['42.480000', '434.008000', '73.359000', '442.333000'], 'Owners'),
   (['75.915000', '434.008000', '83.466000', '442.333000'], 'of'),
   (['85.995000', '434.008000', '98.550000', '442.333000'], 'the'),
   (['100.971000', '434.008000', '139.536000', '442.333000'], 'Company')]),
 (['398.110000', '434.008000', '430.681000', '442.333000'],
  [(['398.110000', '434.008000', '430.681000', '442.333000'], '197,448')]),
 (['511.420000', '434.008000', '543.991000', '442.333000'],
  [(['511.420000', '434.008000', '543.991000', '442.333000'], '172,851')])]


def test_group_net_not_parent_row_and_decimal_context_independent():
    from decimal import localcontext
    data=fixture_data()
    for b,words in _PARENT_LINES:
        data["pages"][0]["lines"].append({"box":box(b),"words":[{"box":box(wb),"text":text} for wb,text in words]})
    baseline=parse(data).data()
    assert baseline["facts"][2]["value"]=="230912" and "197,448" in baseline["extracted_text"]
    with localcontext() as context:
        context.prec=1
        assert parse(data).data()==baseline


@pytest.mark.parametrize("low,high,accepted",[("350.000000","447.999999",True),("350.000000","448.000000",True),
    ("350.000000","448.000001",False),("349.999999","430.000000",False)])
def test_column_edges_do_not_follow_header_or_add_tolerance(low,high,accepted):
    data=fixture_data();move(line(data,"2,505,487"),x_min=low,x_max=high)
    if accepted:assert parse(data).data()["facts"][0]["value"]=="2505487"
    else:
        with pytest.raises(loc.CorporateParseError) as err:parse(data)
        assert err.value.reason=="ambiguous"
