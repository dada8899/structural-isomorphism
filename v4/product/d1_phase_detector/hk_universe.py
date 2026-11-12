"""Hong Kong stock universe for the Phase Detector.

Coverage:
  * Hang Seng Index (HSI) — ~82 large-cap constituents
  * Hang Seng TECH Index (HSTECH) — ~30 names (heavy overlap with HSI)
  * A small "depth bench" of widely-watched HK names not in the indices
    (selective; biased toward names that matter to mainland/southbound
    flows and have liquidity sufficient for AR(1) to be meaningful).

Two things this module does that matter for a real product:

1. Maps US ADR tickers to their HK dual listings so the universe doesn't
   double-count BABA + 9988 etc. The ADR is dropped in favor of the HK
   primary listing (which is the deeper book for these names since
   2019-2022).

2. Tags each ticker with `market` and `currency` so the frontend can
   render HKD vs USD correctly without guessing from the suffix.

The list is intentionally hand-maintained: HSI changes ~quarterly and a
small static file beats screen-scraping HSIL's PDF each time. Refresh
cadence: confirm against `https://www.hsi.com.hk` once per quarter.

`.HK` suffix is the yfinance convention. HK tickers are zero-padded to
4 digits (HKEX convention: `00700.HK`, `09988.HK`). yfinance accepts both
`0700.HK` and `00700.HK`; we use the 4-digit form to match HKEX.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class HkTicker:
    ticker: str            # yfinance form, e.g. "0700.HK"
    hkex_code: str         # zero-padded 4-digit, e.g. "0700"
    name: str
    name_zh: str
    sector: str            # canonical Phase Detector sector slug
    indices: List[str]     # ["HSI", "HSTECH"] etc.
    adr_ticker: Optional[str] = None  # US dual listing if any, e.g. "BABA"
    currency: str = "HKD"
    market: str = "HK"

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Hang Seng Index constituents (as of 2025-Q3 review, manually curated).
# Sector tags align to lib/labels.ts SECTOR_LABEL_ZH keys when possible.
# ---------------------------------------------------------------------------

_HSI: List[HkTicker] = [
    HkTicker("0001.HK", "0001", "CK Hutchison Holdings", "长江和记实业", "industrials_diversified", ["HSI"]),
    HkTicker("0002.HK", "0002", "CLP Holdings", "中电控股", "utilities", ["HSI"]),
    HkTicker("0003.HK", "0003", "Hong Kong & China Gas", "香港中华煤气", "utilities", ["HSI"]),
    HkTicker("0005.HK", "0005", "HSBC Holdings", "汇丰控股", "financials_bank", ["HSI"]),
    HkTicker("0006.HK", "0006", "Power Assets Holdings", "电能实业", "utilities", ["HSI"]),
    HkTicker("0011.HK", "0011", "Hang Seng Bank", "恒生银行", "financials_bank", ["HSI"]),
    HkTicker("0012.HK", "0012", "Henderson Land Development", "恒基地产", "real_estate", ["HSI"]),
    HkTicker("0016.HK", "0016", "Sun Hung Kai Properties", "新鸿基地产", "real_estate", ["HSI"]),
    HkTicker("0017.HK", "0017", "New World Development", "新世界发展", "real_estate", ["HSI"]),
    HkTicker("0020.HK", "0020", "SenseTime Group", "商汤集团", "tech_software", ["HSI", "HSTECH"]),
    HkTicker("0027.HK", "0027", "Galaxy Entertainment", "银河娱乐", "consumer_discretionary", ["HSI"]),
    HkTicker("0066.HK", "0066", "MTR Corporation", "港铁公司", "industrials_diversified", ["HSI"]),
    HkTicker("0101.HK", "0101", "Hang Lung Properties", "恒隆地产", "real_estate", ["HSI"]),
    HkTicker("0175.HK", "0175", "Geely Automobile", "吉利汽车", "tech_auto", ["HSI"]),
    HkTicker("0241.HK", "0241", "Alibaba Health Information", "阿里健康", "healthcare_retail", ["HSI", "HSTECH"]),
    HkTicker("0267.HK", "0267", "CITIC Limited", "中信股份", "industrials_diversified", ["HSI"]),
    HkTicker("0285.HK", "0285", "BYD Electronic", "比亚迪电子", "tech_hardware", ["HSI", "HSTECH"]),
    HkTicker("0288.HK", "0288", "WH Group", "万洲国际", "consumer_staples", ["HSI"]),
    HkTicker("0291.HK", "0291", "China Resources Beer", "华润啤酒", "consumer_staples", ["HSI"]),
    HkTicker("0316.HK", "0316", "Orient Overseas (OOCL)", "东方海外国际", "industrials_diversified", ["HSI"]),
    HkTicker("0322.HK", "0322", "Tingyi", "康师傅控股", "consumer_staples", ["HSI"]),
    HkTicker("0386.HK", "0386", "Sinopec Corp", "中国石油化工", "energy_refining", ["HSI"]),
    HkTicker("0388.HK", "0388", "Hong Kong Exchanges (HKEX)", "香港交易所", "financials_asset_mgmt", ["HSI"]),
    HkTicker("0669.HK", "0669", "Techtronic Industries", "创科实业", "industrials_diversified", ["HSI"]),
    HkTicker("0688.HK", "0688", "China Overseas Land & Investment", "中国海外发展", "real_estate", ["HSI"]),
    HkTicker("0700.HK", "0700", "Tencent Holdings", "腾讯控股", "tech_internet_china", ["HSI", "HSTECH"]),
    HkTicker("0762.HK", "0762", "China Unicom", "中国联通", "telecom", ["HSI"]),
    HkTicker("0788.HK", "0788", "China Tower", "中国铁塔", "telecom", ["HSI"]),
    HkTicker("0823.HK", "0823", "Link REIT", "领展房产基金", "real_estate", ["HSI"]),
    HkTicker("0857.HK", "0857", "PetroChina", "中国石油天然气", "energy_oil_gas", ["HSI"]),
    HkTicker("0868.HK", "0868", "Xinyi Glass", "信义玻璃", "industrials_diversified", ["HSI"]),
    HkTicker("0883.HK", "0883", "CNOOC", "中国海洋石油", "energy_oil_gas", ["HSI"]),
    HkTicker("0939.HK", "0939", "China Construction Bank", "中国建设银行", "financials_bank", ["HSI"]),
    HkTicker("0941.HK", "0941", "China Mobile", "中国移动", "telecom", ["HSI"]),
    HkTicker("0960.HK", "0960", "Longfor Group", "龙湖集团", "real_estate", ["HSI"]),
    HkTicker("0968.HK", "0968", "Xinyi Solar", "信义光能", "energy_solar", ["HSI"]),
    HkTicker("0981.HK", "0981", "SMIC", "中芯国际", "tech_semiconductor", ["HSI", "HSTECH"]),
    HkTicker("0992.HK", "0992", "Lenovo Group", "联想集团", "tech_hardware", ["HSI"]),
    HkTicker("1024.HK", "1024", "Kuaishou Technology", "快手科技", "tech_internet_china", ["HSI", "HSTECH"]),
    HkTicker("1038.HK", "1038", "CK Infrastructure", "长江基建集团", "utilities", ["HSI"]),
    HkTicker("1044.HK", "1044", "Hengan International", "恒安国际", "consumer_staples", ["HSI"]),
    HkTicker("1088.HK", "1088", "China Shenhua Energy", "中国神华能源", "energy_oil_gas", ["HSI"]),
    HkTicker("1093.HK", "1093", "CSPC Pharmaceutical", "石药集团", "healthcare_pharma", ["HSI"]),
    HkTicker("1099.HK", "1099", "Sinopharm Group", "国药控股", "healthcare_retail", ["HSI"]),
    HkTicker("1109.HK", "1109", "China Resources Land", "华润置地", "real_estate", ["HSI"]),
    HkTicker("1113.HK", "1113", "CK Asset Holdings", "长江实业集团", "real_estate", ["HSI"]),
    HkTicker("1177.HK", "1177", "Sino Biopharmaceutical", "中国生物制药", "healthcare_pharma", ["HSI"]),
    HkTicker("1209.HK", "1209", "CR Mixc Lifestyle Services", "华润万象生活", "real_estate", ["HSI"]),
    HkTicker("1211.HK", "1211", "BYD Company", "比亚迪股份", "tech_auto_ev", ["HSI"]),
    HkTicker("1299.HK", "1299", "AIA Group", "友邦保险", "financials_insurance", ["HSI"]),
    HkTicker("1378.HK", "1378", "China Hongqiao Group", "中国宏桥", "industrials_diversified", ["HSI"]),
    HkTicker("1398.HK", "1398", "ICBC", "中国工商银行", "financials_bank", ["HSI"]),
    HkTicker("1810.HK", "1810", "Xiaomi Corporation", "小米集团", "tech_hardware", ["HSI", "HSTECH"]),
    HkTicker("1876.HK", "1876", "Budweiser APAC", "百威亚太", "consumer_staples", ["HSI"]),
    HkTicker("1928.HK", "1928", "Sands China", "金沙中国", "consumer_discretionary", ["HSI"]),
    HkTicker("1929.HK", "1929", "Chow Tai Fook Jewellery", "周大福珠宝", "consumer_discretionary", ["HSI"]),
    HkTicker("1997.HK", "1997", "Wharf REIC", "九龙仓置业", "real_estate", ["HSI"]),
    HkTicker("2007.HK", "2007", "Country Garden", "碧桂园", "real_estate", ["HSI"]),
    HkTicker("2015.HK", "2015", "Li Auto", "理想汽车", "tech_auto_ev", ["HSI", "HSTECH"], adr_ticker="LI"),
    HkTicker("2018.HK", "2018", "AAC Technologies", "瑞声科技", "tech_hardware", ["HSI", "HSTECH"]),
    HkTicker("2020.HK", "2020", "ANTA Sports Products", "安踏体育", "consumer_discretionary", ["HSI"]),
    HkTicker("2269.HK", "2269", "WuXi Biologics", "药明生物", "healthcare_pharma", ["HSI", "HSTECH"]),
    HkTicker("2313.HK", "2313", "Shenzhou International", "申洲国际", "consumer_discretionary", ["HSI"]),
    HkTicker("2318.HK", "2318", "Ping An Insurance", "中国平安保险", "financials_insurance", ["HSI"]),
    HkTicker("2319.HK", "2319", "Mengniu Dairy", "蒙牛乳业", "consumer_staples", ["HSI"]),
    HkTicker("2331.HK", "2331", "Li Ning", "李宁", "consumer_discretionary", ["HSI"]),
    HkTicker("2382.HK", "2382", "Sunny Optical Technology", "舜宇光学科技", "tech_hardware", ["HSI", "HSTECH"]),
    HkTicker("2388.HK", "2388", "BOC Hong Kong", "中银香港", "financials_bank", ["HSI"]),
    HkTicker("2628.HK", "2628", "China Life Insurance", "中国人寿保险", "financials_insurance", ["HSI"]),
    HkTicker("2688.HK", "2688", "ENN Energy", "新奥能源", "utilities", ["HSI"]),
    HkTicker("3690.HK", "3690", "Meituan", "美团", "tech_internet_china", ["HSI", "HSTECH"]),
    HkTicker("3692.HK", "3692", "Hansoh Pharmaceutical", "翰森制药", "healthcare_pharma", ["HSI"]),
    HkTicker("3968.HK", "3968", "China Merchants Bank", "招商银行", "financials_bank", ["HSI"]),
    HkTicker("3988.HK", "3988", "Bank of China", "中国银行", "financials_bank", ["HSI"]),
    HkTicker("6098.HK", "6098", "Country Garden Services", "碧桂园服务", "real_estate", ["HSI"]),
    HkTicker("6618.HK", "6618", "JD Health", "京东健康", "healthcare_retail", ["HSI", "HSTECH"]),
    HkTicker("6690.HK", "6690", "Haier Smart Home", "海尔智家", "consumer_discretionary", ["HSI"]),
    HkTicker("6862.HK", "6862", "Haidilao", "海底捞", "consumer_discretionary", ["HSI"]),
    HkTicker("9618.HK", "9618", "JD.com", "京东集团", "tech_internet_china", ["HSI", "HSTECH"], adr_ticker="JD"),
    HkTicker("9633.HK", "9633", "Nongfu Spring", "农夫山泉", "consumer_staples", ["HSI"]),
    HkTicker("9888.HK", "9888", "Baidu Inc", "百度集团", "tech_internet_china", ["HSI", "HSTECH"], adr_ticker="BIDU"),
    HkTicker("9961.HK", "9961", "Trip.com Group", "携程集团", "tech_internet_china", ["HSI", "HSTECH"], adr_ticker="TCOM"),
    HkTicker("9988.HK", "9988", "Alibaba Group Holding", "阿里巴巴集团", "tech_internet_china", ["HSI", "HSTECH"], adr_ticker="BABA"),
    HkTicker("9999.HK", "9999", "NetEase", "网易", "tech_software_gaming", ["HSI", "HSTECH"], adr_ticker="NTES"),
]


# ---------------------------------------------------------------------------
# Selective bench — HSTECH names NOT already in HSI + a few liquid
# southbound favorites. Keeps the universe meaningful without bloating
# it with illiquid micro-caps where AR1 is unreliable.
# ---------------------------------------------------------------------------

_BENCH: List[HkTicker] = [
    HkTicker("0522.HK", "0522", "ASMPT", "ASMPT", "tech_semiconductor", ["HSTECH"]),
    HkTicker("0780.HK", "0780", "Tongcheng Travel", "同程旅行", "tech_internet_china", ["HSTECH"]),
    HkTicker("0909.HK", "0909", "Ming Yuan Cloud", "明源云", "tech_software", ["HSTECH"]),
    HkTicker("1347.HK", "1347", "Hua Hong Semiconductor", "华虹半导体", "tech_semiconductor", ["HSTECH"]),
    HkTicker("1797.HK", "1797", "Koolearn / East Buy", "东方甄选", "tech_internet_china", ["HSTECH"]),
    HkTicker("1833.HK", "1833", "Ping An Healthcare", "平安好医生", "healthcare_retail", ["HSTECH"]),
    HkTicker("2400.HK", "2400", "XD Inc", "心动公司", "tech_software_gaming", ["HSTECH"]),
    HkTicker("3888.HK", "3888", "Kingsoft Corp", "金山软件", "tech_software", ["HSTECH"]),
    HkTicker("6060.HK", "6060", "ZhongAn Online", "众安在线", "financials_insurance", ["HSTECH"]),
    HkTicker("6682.HK", "6682", "4Paradigm", "第四范式", "tech_software_data", ["HSTECH"]),
    HkTicker("9626.HK", "9626", "Bilibili", "哔哩哔哩", "tech_internet_china", ["HSTECH"], adr_ticker="BILI"),
    HkTicker("9660.HK", "9660", "Horizon Robotics", "地平线机器人", "tech_semiconductor", ["HSTECH"]),
    HkTicker("9866.HK", "9866", "NIO", "蔚来", "tech_auto_ev", ["HSTECH"], adr_ticker="NIO"),
    HkTicker("9868.HK", "9868", "XPeng", "小鹏汽车", "tech_auto_ev", ["HSTECH"], adr_ticker="XPEV"),
    HkTicker("9987.HK", "9987", "Yum China Holdings", "百胜中国", "consumer_discretionary", ["HSTECH"], adr_ticker="YUMC"),
]


HK_UNIVERSE: List[HkTicker] = _HSI + _BENCH


# ---------------------------------------------------------------------------
# ADR -> HK primary dedup map.
# When BOTH a US ADR and its HK dual listing are in the combined universe,
# prefer the HK primary listing (deeper book post-2022 for these names).
# ---------------------------------------------------------------------------

ADR_TO_HK: Dict[str, str] = {
    t.adr_ticker: t.ticker for t in HK_UNIVERSE if t.adr_ticker
}


def dedup_adr_us_first(tickers: List[str]) -> List[str]:
    """Given a combined US+HK ticker list, drop the US ADRs that have an HK
    dual listing also present. Preserves order; HK primary wins."""
    hk_present = {t for t in tickers if t.endswith(".HK")}
    # Build set of ADRs whose HK form is in the list.
    adr_to_drop = {
        adr for adr, hk in ADR_TO_HK.items()
        if hk in hk_present
    }
    return [t for t in tickers if t not in adr_to_drop]


def market_of(ticker: str) -> str:
    """'HK' for HKEX (.HK), 'US' otherwise. Cheap, no I/O."""
    return "HK" if ticker.upper().endswith(".HK") else "US"


def currency_of(ticker: str) -> str:
    return "HKD" if market_of(ticker) == "HK" else "USD"


def hk_universe_dict() -> List[dict]:
    """JSON-ready list for the ingestion pipeline."""
    return [t.to_dict() for t in HK_UNIVERSE]
