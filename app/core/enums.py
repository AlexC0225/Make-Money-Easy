from enum import Enum


class MarketType(str, Enum):
    tsec = "TSEC"
    otc = "OTC"
    emerging = "EMERGING"
    unknown = "UNKNOWN"


class OrderSide(str, Enum):
    buy = "BUY"
    sell = "SELL"


class OrderType(str, Enum):
    market = "MARKET"


class OrderStatus(str, Enum):
    filled = "FILLED"
