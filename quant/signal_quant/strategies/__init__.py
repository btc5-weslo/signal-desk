from signal_quant.strategies.breakout import BreakoutDonchian
from signal_quant.strategies.mean_reversion import MeanReversionRsiBB
from signal_quant.strategies.mtf_confirmation import MtfConfirmation
from signal_quant.strategies.trend import TrendEmaAdx

BASELINE = {
    "trend_ema_adx": TrendEmaAdx,
    "mean_reversion_rsi_bb": MeanReversionRsiBB,
    "breakout_donchian": BreakoutDonchian,
    "mtf_confirmation": MtfConfirmation,
}

__all__ = [
    "BASELINE",
    "BreakoutDonchian",
    "MeanReversionRsiBB",
    "MtfConfirmation",
    "TrendEmaAdx",
]
