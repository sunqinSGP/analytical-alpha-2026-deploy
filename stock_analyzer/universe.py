"""
Screening universe for Analytical Alpha — the curated set the screener scans.
Edit the lists below to change coverage. Tickers use Yahoo Finance symbols
(.SI = Singapore/SGX, .HK = Hong Kong/HKEX). ETFs/leveraged funds are excluded
because the fundamental framework can't score them.
"""

US_SOFTWARE = [
    'MSFT', 'ORCL', 'CRM', 'ADBE', 'NOW', 'SAP', 'INTU', 'IBM', 'CSCO', 'ACN',
    'SNOW', 'DDOG', 'CRWD', 'PANW', 'ZS', 'FTNT', 'QLYS', 'NET', 'MDB', 'HUBS',
    'TEAM', 'WDAY', 'ADSK', 'PLTR', 'SHOP', 'UBER', 'ABNB', 'SPOT', 'TWLO', 'OKTA',
    'DOCU', 'GTLB', 'S', 'CFLT', 'DT', 'ESTC', 'DUOL', 'APP', 'TTD',
]
US_SEMI = [
    'NVDA', 'AMD', 'AVGO', 'TSM', 'MU', 'MRVL', 'AMAT', 'LRCX', 'KLAC', 'TXN',
    'QCOM', 'INTC', 'SMCI', 'ANET', 'DELL', 'STX', 'WDC', 'ON', 'MCHP', 'ADI',
    'NXPI', 'MPWR', 'ARM', 'TER',
]
US_MEGA = ['AAPL', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NFLX']
US_ENERGY_INDUSTRIAL = [
    'BE', 'NEE', 'GEV', 'FSLR', 'CEG', 'VST', 'ENPH', 'XOM', 'CVX', 'COP',
    'SLB', 'EOG', 'OXY', 'CAT', 'GE', 'HON', 'EMR', 'ETN', 'DE', 'LMT',
    'RTX', 'BA', 'UNP', 'UPS',
]
US_HEALTHCARE = [
    'LLY', 'NVO', 'UNH', 'JNJ', 'MRK', 'ABBV', 'PFE', 'BMY', 'TMO', 'DHR',
    'ABT', 'ISRG', 'MDT', 'GILD', 'AMGN', 'BSX', 'SYK', 'REGN', 'VRTX', 'MRNA',
    'ALGN', 'CNC', 'SDGR',
]
US_FINANCIAL = [
    'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'BLK', 'SCHW', 'SPGI', 'V',
    'MA', 'AXP', 'COF', 'USB', 'PNC', 'BX', 'KKR', 'CB', 'PGR',
]
US_CONSUMER = [
    'WMT', 'COST', 'HD', 'LOW', 'TGT', 'NKE', 'SBUX', 'MCD', 'CMG', 'BKNG',
    'PG', 'KO', 'PEP', 'MDLZ', 'CL', 'KHC', 'DIS', 'TJX', 'ORLY', 'CPRT',
]
SGX = [
    'D05.SI', 'O39.SI', 'U11.SI', 'Z74.SI', 'S68.SI', 'C52.SI', 'S63.SI', 'F34.SI',
    'BN4.SI', 'C09.SI', 'U96.SI', 'G13.SI', 'Y92.SI', 'C6L.SI', 'BS6.SI', 'H78.SI',
    '9CI.SI', 'V03.SI', 'C38U.SI', 'A17U.SI', 'M44U.SI', 'ME8U.SI', 'N2IU.SI', 'J69U.SI',
    'AJBU.SI', 'CC3.SI',
]
HKEX = [
    '0700.HK', '9988.HK', '3690.HK', '9618.HK', '1299.HK', '0005.HK', '0388.HK', '2318.HK',
    '0941.HK', '0016.HK', '1810.HK', '0981.HK', '1211.HK', '9999.HK', '2020.HK', '0883.HK',
    '0939.HK', '1398.HK', '3988.HK', '2628.HK', '1024.HK', '9888.HK', '0386.HK', '2331.HK',
    '0027.HK', '1928.HK', '0001.HK', '0011.HK', '0002.HK', '1113.HK', '0288.HK', '1109.HK',
    '2382.HK',
]
EU_ADR = [
    'ASML', 'AZN', 'NVS', 'HSBC', 'BHP', 'RIO', 'BP', 'SHEL', 'TM', 'SONY',
    'UL', 'DEO', 'RACE', 'SHG', 'PHG',
]

WATCHLIST = list(dict.fromkeys(
    US_SOFTWARE + US_SEMI + US_MEGA + US_ENERGY_INDUSTRIAL + US_HEALTHCARE
    + US_FINANCIAL + US_CONSUMER + SGX + HKEX + EU_ADR
))
