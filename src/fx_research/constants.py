"""Project-wide constants reconstructed from the 2025 combined R script."""

from __future__ import annotations

SECTOR_STOCKS: dict[str, tuple[str, ...]] = {
    "반도체": ("SK하이닉스", "삼성전자", "DB하이텍", "한미반도체", "원익IPS"),
    "자동차": ("현대차", "기아", "현대모비스", "현대위아", "SNT모티브"),
    "화학": ("LG화학", "롯데케미칼", "SK케미칼", "한화솔루션", "금호석유화학"),
    "건설": ("현대건설", "GS건설", "DL이앤씨", "대우건설", "HDC현대산업개발"),
    "금융": ("KB금융", "하나금융지주", "우리금융지주", "메리츠금융지주", "신한지주"),
    "유통_소매": ("이마트", "롯데쇼핑", "BGF리테일", "GS리테일", "신세계"),
    "에너지_정유": ("S-Oil", "SK이노베이션", "한국가스공사", "한국전력", "GS"),
    "바이오_제약": ("셀트리온", "삼성바이오로직스", "유한양행", "한미약품", "종근당"),
    "미디어_엔터": ("CJ ENM", "스튜디오드래곤", "JYP Ent.", "iMBC", "콘텐트리중앙"),
    "통신": ("SK텔레콤", "KT", "LG유플러스", "SK스퀘어", "KTis"),
}

STOCK_TO_SECTOR: dict[str, str] = {
    stock: sector for sector, stocks in SECTOR_STOCKS.items() for stock in stocks
}

LEGACY_CORR_SECTORS = {
    "미디어_엔터",
    "반도체",
    "금융",
    "에너지_정유",
    "바이오_제약",
}

REQUIRED_MARKET_COLUMNS = {
    "종목",
    "일자",
    "ret",
    "fore_chg",
    "USD_ret",
    "EUR_ret",
    "JPY100_ret",
    "CNY_ret",
}
