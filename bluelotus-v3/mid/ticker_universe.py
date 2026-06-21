"""Central ticker universe for BlueLotus MID fetchers.

This module is the single source of truth for the capped research universe.
Keep GRAND_UNIVERSE_200 at or below UNIVERSE_LIMIT so every fetcher, exporter,
and probe uses the same ticker set.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Set

UNIVERSE_LIMIT = 210

GRAND_UNIVERSE_200 = [
    'NVDA', 'AMD', 'AVGO', 'MRVL', 'MU', 'TSM', 'AMAT', 'ARM',
    'CDNS', 'SNPS', 'INTC', 'AMKR', 'ASML', 'QCOM', 'TXN', 'LRCX',
    'KLAC', 'MSFT', 'AAPL', 'GOOGL', 'META', 'AMZN', 'TSLA', 'NFLX',
    'UBER', 'DIS', 'CRWD', 'PANW', 'AXON', 'PLTR', 'ORCL', 'CRM',
    'NOW', 'ADBE', 'FTNT', 'ZS', 'INTU', 'SNOW', 'OKTA', 'S',
    'BAC', 'WFC', 'C', 'SOFI', 'HOOD', 'COIN', 'JPM', 'GS',
    'MS', 'BLK', 'SCHW', 'AXP', 'CB', 'MCO', 'PGR', 'ALL',
    'V', 'MA', 'PYPL', 'MSTR', 'IBIT', 'LLY', 'MRNA', 'ABBV',
    'PFE', 'JNJ', 'UNH', 'MRK', 'AMGN', 'BMY', 'GILD', 'REGN',
    'BIIB', 'RTX', 'NOC', 'LMT', 'HII', 'LDOS', 'BA', 'LHX',
    'HON', 'TDG', 'HEI', 'KTOS', 'ASTS', 'RKLB', 'LUNR', 'BKSY',
    'SATS', 'RDW', 'SIDU', 'IRDM', 'VSAT', 'GSAT', 'SPIR', 'PL',
    'SPCE', 'AMT', 'GLD', 'SLV', 'NEM', 'AU', 'CDE', 'HL',
    'AG', 'PAAS', 'FCX', 'SCCO', 'BHP', 'RIO', 'HBM', 'TECK',
    'VALE', 'NUE', 'AA', 'CLF', 'CAT', 'NTR', 'MOS', 'ADM',
    'MP', 'USAR', 'ALB', 'CEG', 'VST', 'CCJ', 'UUUU', 'OKLO',
    'SMR', 'BWXT', 'DUK', 'WMB', 'KMI', 'GEV', 'NEE', 'ETN',
    'EMR', 'AWK', 'ENPH', 'FSLR', 'FCEL', 'BE', 'PLUG', 'SEDG',
    'ARRY', 'RUN', 'BEP', 'XOM', 'OXY', 'EOG', 'FANG', 'CVX',
    'COP', 'DVN', 'LNG', 'VLO', 'PSX', 'MPC', 'EPD', 'ENB',
    'TLT', 'IEF', 'GDX', 'GDXJ', 'SPY', 'QQQ', 'XLE', 'UUP',
    'VXX', 'UVXY',
    'KO', 'PG', 'WMT', 'COST', 'PEP', 'MCD', 'HD',
    'LOW', 'NKE', 'SBUX', 'TGT', 'CL', 'UPS', 'FDX', 'UNP',
    'CSX', 'DAL', 'DE', 'VZ', 'T', 'O', 'IONQ', 'QBTS',
    'QUBT', 'RGTI', 'QTUM', 'DELL', 'SMCI', 'VRT', 'ANET', 'GE',
]

# Backwards-compatible aliases. Several older modules still refer to these names.
WATCHLIST_83 = GRAND_UNIVERSE_200
WATCHLIST_78 = GRAND_UNIVERSE_200

ETF_TICKERS: Set[str] = {
    'DIA', 'GDX', 'GDXJ', 'GLD', 'IAU', 'IEF', 'IBIT', 'IWM', 'QQQ',
    'QTUM', 'SLV', 'SPY', 'TLT', 'UUP', 'USO', 'UVXY', 'VIXY', 'VXX',
    'XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY',
}

NO_EARNINGS_TICKERS: Set[str] = {
    'DIA', 'GDX', 'GDXJ', 'GLD', 'IAU', 'IEF', 'IBIT', 'IWM', 'QQQ',
    'QTUM', 'SLV', 'SPY', 'TLT', 'UUP', 'USO', 'UVXY', 'VIXY', 'VXX',
    'XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY',
}

HIGH_AMBIGUITY_TICKERS: Set[str] = {
    'AU', 'BA', 'BE', 'C', 'DE', 'GE', 'MP', 'O',
    'S', 'T', 'V',
}

NASDAQ_TICKERS: Set[str] = {
    'AAPL', 'ADBE', 'AMAT', 'AMD', 'AMGN', 'AMKR', 'AMZN', 'ARM',
    'ARRY', 'ASML', 'ASTS', 'AVGO', 'AXON', 'BIIB', 'CDNS', 'COIN',
    'COST', 'CRWD', 'CSX', 'DIA', 'ENPH', 'FCEL', 'FDX', 'FTNT',
    'GDX', 'GDXJ', 'GILD', 'GOOGL', 'HON', 'IAU', 'IBIT', 'INTC',
    'INTU', 'IRDM', 'IWM', 'KLAC', 'LRCX', 'META', 'MRNA', 'MRVL',
    'MSFT', 'MSTR', 'MU', 'NFLX', 'NVDA', 'OKTA', 'PANW', 'PEP',
    'PLUG', 'PYPL', 'QCOM', 'QQQ', 'QTUM', 'QUBT', 'RGTI', 'RUN',
    'S', 'SBUX', 'SEDG', 'SIDU', 'SMCI', 'SNPS', 'SOFI', 'SPIR',
    'SPY', 'TSLA', 'TXN', 'VRT', 'VSAT', 'XLB', 'XLE', 'XLF',
    'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY', 'ZS',
}

COMPANY_TICKER_ALIASES = [
    (['taiwan semiconductor', 'tsmc'], 'TSM'),
    (['applied materials'], 'AMAT'),
    (['advanced micro devices'], 'AMD'),
    (['arm holdings'], 'ARM'),
    (['ge aerospace', 'general electric'], 'GE'),
    (['huntington ingalls'], 'HII'),
    (['northrop grumman'], 'NOC'),
    (['lockheed martin'], 'LMT'),
    (['palo alto networks', 'palo alto'], 'PANW'),
    (['bank of america'], 'BAC'),
    (['wells fargo'], 'WFC'),
    (['eli lilly'], 'LLY'),
    (['constellation energy'], 'CEG'),
    (['williams companies'], 'WMB'),
    (['kinder morgan'], 'KMI'),
    (['eog resources'], 'EOG'),
    (['mp materials'], 'MP'),
    (['first solar'], 'FSLR'),
    (['bloom energy'], 'BE'),
    (['plug power'], 'PLUG'),
    (['rocket lab'], 'RKLB'),
    (['intuitive machines'], 'LUNR'),
    (['redwire'], 'RDW'),
    (['sidus space'], 'SIDU'),
    (['quantum computing inc', 'qubt'], 'QUBT'),
    (['d-wave', 'dwave', 'd wave'], 'QBTS'),
    (['rigetti'], 'RGTI'),
    (['quantinuum'], 'RGTI'),
    (['ionq'], 'IONQ'),
    (['broadcom'], 'AVGO'),
    (['marvell'], 'MRVL'),
    (['crowdstrike'], 'CRWD'),
    (['palantir'], 'PLTR'),
    (['nvidia', 'geforce', 'cuda'], 'NVDA'),
    (['microsoft', 'azure', 'surface'], 'MSFT'),
    (['alphabet', 'google', 'googl'], 'GOOGL'),
    (['meta platforms', 'facebook'], 'META'),
    (['amazon', 'aws'], 'AMZN'),
    (['oracle'], 'ORCL'),
    (['qualcomm', 'snapdragon'], 'QCOM'),
    (['dell'], 'DELL'),
    (['supermicro'], 'SMCI'),
    (['vertiv'], 'VRT'),
    (['arista'], 'ANET'),
    (['raytheon'], 'RTX'),
    (['boeing'], 'BA'),
    (['leidos'], 'LDOS'),
    (['axon'], 'AXON'),
    (['iridium'], 'IRDM'),
    (['blacksky'], 'BKSY'),
    (['spire global'], 'SATS'),
    (['newmont'], 'NEM'),
    (['anglogold'], 'AU'),
    (['freeport'], 'FCX'),
    (['albemarle'], 'ALB'),
    (['cameco'], 'CCJ'),
    (['vistra'], 'VST'),
    (['duke energy'], 'DUK'),
    (['enphase'], 'ENPH'),
    (['fuelcell'], 'FCEL'),
    (['moderna'], 'MRNA'),
    (['abbvie'], 'ABBV'),
    (['pfizer'], 'PFE'),
    (['coinbase'], 'COIN'),
    (['robinhood'], 'HOOD'),
    (['sofi'], 'SOFI'),
    (['exxon', 'exxonmobil'], 'XOM'),
    (['occidental'], 'OXY'),
    (['intel', 'xeon'], 'INTC'),
    (['apple', 'iphone', 'ipad', 'macos', 'wwdc'], 'AAPL'),
    (['micron'], 'MU'),
    (['synopsys'], 'SNPS'),
    (['cadence'], 'CDNS'),
    (['amkor technology', 'amkor'], 'AMKR'),
    (['asml holding', 'asml'], 'ASML'),
    (['texas instruments'], 'TXN'),
    (['lam research'], 'LRCX'),
    (['kla corporation', 'kla'], 'KLAC'),
    (['tesla'], 'TSLA'),
    (['netflix'], 'NFLX'),
    (['uber technologies', 'uber'], 'UBER'),
    (['walt disney', 'disney'], 'DIS'),
    (['salesforce'], 'CRM'),
    (['servicenow', 'service now'], 'NOW'),
    (['adobe'], 'ADBE'),
    (['fortinet'], 'FTNT'),
    (['zscaler'], 'ZS'),
    (['intuit'], 'INTU'),
    (['snowflake'], 'SNOW'),
    (['okta'], 'OKTA'),
    (['sentinelone'], 'S'),
    (['jpmorgan chase', 'jp morgan', 'jpmorgan'], 'JPM'),
    (['goldman sachs'], 'GS'),
    (['morgan stanley'], 'MS'),
    (['blackrock'], 'BLK'),
    (['charles schwab', 'schwab'], 'SCHW'),
    (['american express', 'amex'], 'AXP'),
    (['chubb'], 'CB'),
    (['moodys', "moody's"], 'MCO'),
    (['progressive'], 'PGR'),
    (['allstate'], 'ALL'),
    (['visa'], 'V'),
    (['mastercard'], 'MA'),
    (['paypal'], 'PYPL'),
    (['microstrategy', 'strategy'], 'MSTR'),
    (['ishares bitcoin trust', 'bitcoin trust'], 'IBIT'),
    (['johnson and johnson'], 'JNJ'),
    (['unitedhealth', 'united health'], 'UNH'),
    (['merck'], 'MRK'),
    (['amgen'], 'AMGN'),
    (['bristol myers', 'bristol-myers', 'bristol myers squibb'], 'BMY'),
    (['gilead sciences', 'gilead'], 'GILD'),
    (['regeneron'], 'REGN'),
    (['biogen'], 'BIIB'),
    (['l3harris', 'l3 harris'], 'LHX'),
    (['honeywell'], 'HON'),
    (['transdigm'], 'TDG'),
    (['heico'], 'HEI'),
    (['kratos'], 'KTOS'),
    (['ast spacemobile'], 'ASTS'),
    (['viasat'], 'VSAT'),
    (['globalstar'], 'GSAT'),
    (['planet labs'], 'PL'),
    (['virgin galactic'], 'SPCE'),
    (['american tower'], 'AMT'),
    (['coeur mining'], 'CDE'),
    (['hecla mining', 'hecla'], 'HL'),
    (['first majestic'], 'AG'),
    (['pan american silver'], 'PAAS'),
    (['southern copper'], 'SCCO'),
    (['bhp'], 'BHP'),
    (['rio tinto'], 'RIO'),
    (['hudbay minerals', 'hudbay'], 'HBM'),
    (['teck resources', 'teck'], 'TECK'),
    (['vale'], 'VALE'),
    (['nucor'], 'NUE'),
    (['alcoa'], 'AA'),
    (['cleveland cliffs', 'cleveland-cliffs'], 'CLF'),
    (['caterpillar'], 'CAT'),
    (['nutrien'], 'NTR'),
    (['mosaic'], 'MOS'),
    (['archer daniels midland', 'adm'], 'ADM'),
    (['usa rare earth'], 'USAR'),
    (['oklo'], 'OKLO'),
    (['nuscale', 'nuscale power'], 'SMR'),
    (['bwxt', 'bwx technologies'], 'BWXT'),
    (['ge vernova'], 'GEV'),
    (['nextera energy', 'nextera'], 'NEE'),
    (['eaton'], 'ETN'),
    (['emerson electric', 'emerson'], 'EMR'),
    (['american water works'], 'AWK'),
    (['solaredge'], 'SEDG'),
    (['array technologies'], 'ARRY'),
    (['sunrun'], 'RUN'),
    (['brookfield renewable'], 'BEP'),
    (['chevron'], 'CVX'),
    (['conocophillips', 'conoco'], 'COP'),
    (['devon energy'], 'DVN'),
    (['cheniere energy', 'cheniere'], 'LNG'),
    (['valero'], 'VLO'),
    (['phillips 66'], 'PSX'),
    (['marathon petroleum'], 'MPC'),
    (['enterprise products'], 'EPD'),
    (['enbridge'], 'ENB'),
    (['ishares 20 year treasury bond', 'treasury bond etf'], 'TLT'),
    (['coca cola', 'coca-cola'], 'KO'),
    (['procter gamble', 'procter & gamble'], 'PG'),
    (['walmart'], 'WMT'),
    (['costco'], 'COST'),
    (['pepsico'], 'PEP'),
    (['mcdonalds', "mcdonald's"], 'MCD'),
    (['home depot'], 'HD'),
    (['lowes', "lowe's"], 'LOW'),
    (['nike'], 'NKE'),
    (['starbucks'], 'SBUX'),
    (['target'], 'TGT'),
    (['colgate palmolive', 'colgate-palmolive'], 'CL'),
    (['ups', 'united parcel service'], 'UPS'),
    (['fedex'], 'FDX'),
    (['union pacific'], 'UNP'),
    (['csx'], 'CSX'),
    (['delta air lines', 'delta airlines'], 'DAL'),
    (['deere'], 'DE'),
    (['verizon'], 'VZ'),
    (['at&t', 'att'], 'T'),
    (['realty income'], 'O'),
]

COMPANY_TICKER_ALIAS_DICT = {
    alias: ticker
    for aliases, ticker in COMPANY_TICKER_ALIASES
    for alias in aliases
}


def _env_limit(default: int | None = None) -> int:
    raw = os.getenv('BLUELOTUS_TICKER_LIMIT')
    if raw:
        try:
            return max(1, min(int(raw), UNIVERSE_LIMIT))
        except ValueError:
            pass
    if default is None:
        return UNIVERSE_LIMIT
    return max(1, min(int(default), UNIVERSE_LIMIT))


def normalize_tickers(tickers: Iterable[str]) -> List[str]:
    seen = set()
    clean = []
    for ticker in tickers:
        t = str(ticker).strip().upper()
        if not t or t in seen:
            continue
        seen.add(t)
        clean.append(t)
    return clean


def get_universe(limit: int | None = None, exclude: Iterable[str] | None = None) -> List[str]:
    excluded = {str(t).strip().upper() for t in (exclude or [])}
    tickers = [t for t in GRAND_UNIVERSE_200 if t not in excluded]
    return tickers[:_env_limit(limit)]


def get_equity_universe(limit: int | None = None) -> List[str]:
    return get_universe(limit=limit, exclude=ETF_TICKERS)


def get_earnings_universe(limit: int | None = None) -> List[str]:
    return get_universe(limit=limit, exclude=NO_EARNINGS_TICKERS)


def is_etf(ticker: str) -> bool:
    return str(ticker).strip().upper() in ETF_TICKERS
