from typing import AsyncGenerator, Dict, List

from . import pairs
from .api import ApiProvider
from .structs import (
    Candle,
    DefaultPairDict,
    MarketTicker,
    MarketTrade,
    OrderBook,
    OrderInBook,
    OrderSide,
    Pair,
    Period,
)


class Exchange:
    """Interface to base exchange methods."""

    def __init__(self, api: ApiProvider = None):
        self.api = api or ApiProvider(auth_required=False)
        self.pairs = DefaultPairDict(
            **{pair.name: pair for pair in pairs.all()}
        )

    async def sync_pairs(self):
        """Use this method to sync pairs if you have issues with missing
        pairs in library side."""
        self.pairs = DefaultPairDict(
            **{pair.name: pair for pair in (await self.get_pairs())}
        )

    async def get_pairs(self) -> List[Pair]:
        """List all available market pairs and store to provide pairs info."""
        data = await self.api.get("public/get-instruments")
        return [
            Pair(
                i["instrument_name"],
                quote_currency=i["quote_currency"],
                base_currency=i["base_currency"],
                price_precision=i["price_decimals"],
                quantity_precision=i["quantity_decimals"],
                margin_trading_enabled=i["margin_trading_enabled"],
                margin_trading_enabled_5x=i["margin_trading_enabled_5x"],
                margin_trading_enabled_10x=i["margin_trading_enabled_10x"],
                max_quantity=i["max_quantity"],
                min_quantity=i["min_quantity"],
                max_price=i["max_price"],
                min_price=i["min_price"],
                last_update_date=i["last_update_date"],
                quantity_tick_size=i["quantity_tick_size"],
                price_tick_size=i["price_tick_size"]
            )
            for i in data["instruments"]
        ]

    async def get_ticker(self, pair: Pair) -> MarketTicker:
        """Get ticker in for provided pair."""
        data = await self.api.get(
            "public/get-ticker", {"instrument_name": pair.name}
        )
        return MarketTicker.from_api(pair, data[0])

    async def get_tickers(self) -> Dict[Pair, MarketTicker]:
        """Get tickers in all available markets."""
        data = await self.api.get("public/get-ticker")
        return {
            self.pairs[ticker["i"]]: MarketTicker.from_api(
                self.pairs[ticker["i"]], ticker
            )
            for ticker in data
            if ticker["i"] in self.pairs
        }

    async def get_price(self, pair: Pair) -> float:
        """Get latest price of pair."""
        return (await self.get_ticker(pair)).trade_price

    async def get_trades(self, pair: Pair) -> List[MarketTrade]:
        """Get last 200 trades in a specified market."""
        data = await self.api.get(
            "public/get-trades", {"instrument_name": pair.name}
        )
        return [MarketTrade.from_api(pair, trade) for trade in reversed(data)]

    async def get_orderbook(self, pair: Pair) -> OrderBook:
        """Get the order book for a particular market, depth always 150."""
        data = await self.api.get(
            "public/get-book", {"instrument_name": pair.name}
        )
        buys = [
            OrderInBook.from_api(order, pair, OrderSide.BUY)
            for order in data[0]["bids"]
        ]
        sells = [
            OrderInBook.from_api(order, pair, OrderSide.SELL)
            for order in reversed(data[0]["asks"])
        ]
        return OrderBook(buys, sells, pair)

    async def get_candles(self, pair: Pair, period: Period) -> List[Candle]:
        data = await self.api.get(
            "public/get-candlestick",
            {"instrument_name": pair.name, "timeframe": period.value},
        )
        return [Candle.from_api(pair, candle) for candle in data]

    async def listen_candles(
        self, period: Period, *pairs: List[Pair]
    ) -> AsyncGenerator[Candle, None]:
        if not isinstance(period, Period):
            raise ValueError(f"Provide Period enum not {period}")

        channels = [f"candlestick.{period}.{pair.name}" for pair in pairs]

        async for data in self.api.listen("market", *channels):
            pair = self.pairs[data["instrument_name"]]
            for candle in data["data"]:
                yield Candle.from_api(pair, candle)

    async def listen_trades(self, *pairs: List[Pair]) -> MarketTrade:
        channels = [f"trade.{pair.name}" for pair in pairs]
        async for data in self.api.listen("market", *channels):
            for trade in data["data"]:
                pair = self.pairs[data["instrument_name"]]
                yield MarketTrade.from_api(pair, trade)

    async def listen_orderbook(self, *pairs: List[Pair]) -> OrderBook:
        channels = [f"book.{pair.name}.50" for pair in pairs]
        async for data in self.api.listen("market", *channels):
            pair = self.pairs[data["instrument_name"]]
            buys = [
                OrderInBook.from_api(order, pair, OrderSide.BUY)
                for order in data["data"][0]["bids"]
            ]
            sells = [
                OrderInBook.from_api(order, pair, OrderSide.SELL)
                for order in reversed(data["data"][0]["asks"])
            ]
            yield OrderBook(buys, sells, pair)
