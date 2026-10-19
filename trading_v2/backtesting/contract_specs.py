"""Modelado exacto de costes contractuales, tick_value, conversión USD->EUR y dimensionamiento de lotes.

Cumple estrictamente los estándares cuantitativos V2:
- Conversión exacta de divisas (profit_currency USD -> account_currency EUR).
- Redondeo a la BAJA al múltiplo de lot_step (nunca redondear al alza).
- Rechazo estricto si el riesgo excede el presupuesto para el lote mínimo (nunca forzar lot_min).
- Control de stops_level_points del broker.
- Estimación precisa de margen y swap overnight.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    description: str
    point: float
    digits: int
    tick_size: float
    contract_size: float
    profit_currency: str
    margin_currency: str
    lot_min: float
    lot_step: float
    lot_max: float
    stops_level_points: int = 0
    freeze_level_points: int = 0
    calc_mode: int = 4
    swap_long: float = 0.0
    swap_short: float = 0.0
    swap_mode: int = 5  # 5 = SWAP_BY_INTEREST_CURRENT, 0 = SWAP_BY_POINTS
    commission_per_lot: float = 0.0  # Comisión contractual round-trip en USD (ej. 7.0 USD/lote en FX Raw Spread)
    typical_spread_points: float = 0.0  # Spread típico en puntos de precio

    def __post_init__(self):
        if min(self.point, self.tick_size, self.contract_size, self.lot_min, self.lot_step, self.lot_max) <= 0:
            raise ValueError("Parámetros numéricos del contrato deben ser estrictamente positivos")
        if self.lot_min > self.lot_max:
            raise ValueError("lot_min no puede ser superior a lot_max")
        if self.stops_level_points < 0 or self.freeze_level_points < 0:
            raise ValueError("stops_level_points y freeze_level_points no pueden ser negativos")

    def tick_value_in_account_currency(self, eurusd_rate: float, account_currency: str = "EUR") -> float:
        """Calcula el valor en la divisa de la cuenta de un movimiento de 1 tick (tick_size) para 1 lote."""
        if eurusd_rate <= 0:
            raise ValueError("eurusd_rate debe ser positivo")
        # Valor en la divisa del beneficio (profit_currency) para 1.0 lote:
        value_in_profit_ccy = self.contract_size * self.tick_size
        
        acc_ccy = account_currency.upper()
        prof_ccy = self.profit_currency.upper()

        if prof_ccy == acc_ccy:
            return value_in_profit_ccy
        elif prof_ccy == "USD" and acc_ccy == "EUR":
            return value_in_profit_ccy / eurusd_rate
        elif prof_ccy == "EUR" and acc_ccy == "USD":
            return value_in_profit_ccy * eurusd_rate
        elif prof_ccy == "JPY" and acc_ccy == "EUR":
            return value_in_profit_ccy / 162.0
        else:
            raise ValueError(f"Conversión no soportada entre {prof_ccy} y {acc_ccy}")

    def point_value_in_account_currency(self, eurusd_rate: float, account_currency: str = "EUR") -> float:
        """Valor en divisa de cuenta de 1 punto de precio (point) para 1 lote."""
        tick_val = self.tick_value_in_account_currency(eurusd_rate, account_currency)
        return tick_val * (self.point / self.tick_size)


@dataclass(frozen=True)
class LotCalculationResult:
    status: Literal["OK", "REJECTED_BELOW_MIN_LOT", "REJECTED_STOPS_LEVEL", "REJECTED_INVALID_INPUT"]
    lots: float
    raw_lots: float
    risk_budget_account_ccy: float
    actual_risk_account_ccy: float
    stop_distance_price: float
    stop_distance_points: float
    required_margin_account_ccy: float
    reason: str


# Especificaciones canónicas auditadas en AdmiralsGroup-Demo
ADMIRALS_SPECS: dict[str, ContractSpec] = {
    "GERMANY40": ContractSpec(
        symbol="GERMANY40",
        description="Germany 40 Index CFD, cash (EUR)",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=1.0,
        profit_currency="EUR",
        margin_currency="EUR",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=100.0,
        stops_level_points=120,
        calc_mode=4,
        swap_long=-4.94,
        swap_short=-0.06,
        swap_mode=5,
    ),
    "[SP500]": ContractSpec(
        symbol="[SP500]",
        description="Standard and Poor's Index CFD, cash (USD)",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=1.0,
        profit_currency="USD",
        margin_currency="USD",
        lot_min=0.1,
        lot_step=0.1,
        lot_max=500.0,
        stops_level_points=40,
        calc_mode=4,
        swap_long=-6.39,
        swap_short=1.39,
        swap_mode=5,
    ),
    "[DJI30]": ContractSpec(
        symbol="[DJI30]",
        description="Dow Jones Index CFD, cash (USD)",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=1.0,
        profit_currency="USD",
        margin_currency="USD",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=100.0,
        stops_level_points=150,
        calc_mode=4,
        swap_long=-6.38,
        swap_short=1.38,
        swap_mode=5,
    ),
    "GOLD": ContractSpec(
        symbol="GOLD",
        description="Gold (100 oz) vs US Dollar CFD",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=100.0,
        profit_currency="USD",
        margin_currency="USD",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=25.0,
        stops_level_points=25,
        calc_mode=4,
        swap_long=-6.361,
        swap_short=1.825,
        swap_mode=5,
    ),
    "EURUSD": ContractSpec(
        symbol="EURUSD",
        description="Euro vs US Dollar",
        point=0.00001,
        digits=5,
        tick_size=0.00001,
        contract_size=100000.0,
        profit_currency="USD",
        margin_currency="EUR",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=100.0,
        stops_level_points=0,
        calc_mode=0,
        swap_long=-3.87,
        swap_short=-0.83,
        swap_mode=5,
    ),
    "US100": ContractSpec(
        symbol="US100",
        description="US100 Index CFD, cash (USD)",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=1.0,
        profit_currency="USD",
        margin_currency="USD",
        lot_min=0.02,
        lot_step=0.01,
        lot_max=500.0,
        stops_level_points=80,
        calc_mode=4,
        swap_long=-6.39,
        swap_short=1.39,
        swap_mode=5,
    ),
    "[JP225]": ContractSpec(
        symbol="[JP225]",
        description="Nikkei 225 Index CFD, cash (JPY)",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=10.0,
        profit_currency="JPY",
        margin_currency="JPY",
        lot_min=1.0,
        lot_step=1.0,
        lot_max=500.0,
        stops_level_points=900,
        calc_mode=4,
        swap_long=-3.728,
        swap_short=-1.272,
        swap_mode=5,
    ),
}


# Especificaciones canónicas auditadas en IC Markets (Raw Spread / Global 1:500)
ICMARKETS_SPECS: dict[str, ContractSpec] = {
    "DE40": ContractSpec(
        symbol="DE40",
        description="Germany 40 Index CFD (IC Markets Raw)",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=1.0,
        profit_currency="EUR",
        margin_currency="EUR",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=200.0,
        stops_level_points=0,
        calc_mode=4,
        swap_long=-5.50,
        swap_short=0.20,
        swap_mode=5,
        commission_per_lot=0.0,
        typical_spread_points=100.0,  # 1.00 pt típico
    ),
    "US500": ContractSpec(
        symbol="US500",
        description="S&P 500 Index CFD (IC Markets Raw)",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=1.0,
        profit_currency="USD",
        margin_currency="USD",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=200.0,
        stops_level_points=0,
        calc_mode=4,
        swap_long=-6.00,
        swap_short=1.20,
        swap_mode=5,
        commission_per_lot=0.0,
        typical_spread_points=40.0,  # 0.40 pt típico
    ),
    "US30": ContractSpec(
        symbol="US30",
        description="US Wall Street 30 Index CFD (IC Markets Raw)",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=1.0,
        profit_currency="USD",
        margin_currency="USD",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=200.0,
        stops_level_points=0,
        calc_mode=4,
        swap_long=-6.20,
        swap_short=1.20,
        swap_mode=5,
        commission_per_lot=0.0,
        typical_spread_points=150.0,  # 1.50 pt típico
    ),
    "USTEC": ContractSpec(
        symbol="USTEC",
        description="US Tech 100 Index CFD (IC Markets Raw)",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=1.0,
        profit_currency="USD",
        margin_currency="USD",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=200.0,
        stops_level_points=0,
        calc_mode=4,
        swap_long=-6.20,
        swap_short=1.20,
        swap_mode=5,
        commission_per_lot=0.0,
        typical_spread_points=100.0,  # 1.00 pt típico
    ),
    "EURUSD": ContractSpec(
        symbol="EURUSD",
        description="Euro vs US Dollar Raw Spread (IC Markets)",
        point=0.00001,
        digits=5,
        tick_size=0.00001,
        contract_size=100000.0,
        profit_currency="USD",
        margin_currency="EUR",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=200.0,
        stops_level_points=0,
        calc_mode=0,
        swap_long=-4.20,
        swap_short=1.10,
        swap_mode=0,
        commission_per_lot=7.00,  # $7.00 USD round-trip por lote estándar
        typical_spread_points=1.0,  # 0.1 pip típico en Raw Spread
    ),
    "XAUUSD": ContractSpec(
        symbol="XAUUSD",
        description="Gold (100 oz) vs US Dollar (IC Markets)",
        point=0.01,
        digits=2,
        tick_size=0.01,
        contract_size=100.0,
        profit_currency="USD",
        margin_currency="USD",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=100.0,
        stops_level_points=0,
        calc_mode=4,
        swap_long=-6.50,
        swap_short=1.80,
        swap_mode=5,
        commission_per_lot=0.0,
        typical_spread_points=15.0,  # 0.15 USD típico
    ),
    "JP225": ContractSpec(
        symbol="JP225",
        description="Nikkei 225 Index CFD (IC Markets Raw)",
        point=1.0,
        digits=0,
        tick_size=1.0,
        contract_size=100.0,
        profit_currency="JPY",
        margin_currency="JPY",
        lot_min=0.01,
        lot_step=0.01,
        lot_max=100.0,
        stops_level_points=0,
        calc_mode=4,
        swap_long=-3.50,
        swap_short=-1.20,
        swap_mode=5,
        commission_per_lot=0.0,
        typical_spread_points=500.0,
    ),
}

# Tabla de sinónimos inter-broker
SYMBOL_ALIASES: dict[str, dict[str, str]] = {
    "DAX40": {"admirals": "GERMANY40", "icmarkets": "DE40"},
    "GERMANY40": {"admirals": "GERMANY40", "icmarkets": "DE40"},
    "DE40": {"admirals": "GERMANY40", "icmarkets": "DE40"},
    "SP500": {"admirals": "[SP500]", "icmarkets": "US500"},
    "[SP500]": {"admirals": "[SP500]", "icmarkets": "US500"},
    "US500": {"admirals": "[SP500]", "icmarkets": "US500"},
    "DOW30": {"admirals": "[DJI30]", "icmarkets": "US30"},
    "[DJI30]": {"admirals": "[DJI30]", "icmarkets": "US30"},
    "US30": {"admirals": "[DJI30]", "icmarkets": "US30"},
    "NASDAQ100": {"admirals": "US100", "icmarkets": "USTEC"},
    "US100": {"admirals": "US100", "icmarkets": "USTEC"},
    "USTEC": {"admirals": "US100", "icmarkets": "USTEC"},
    "GOLD": {"admirals": "GOLD", "icmarkets": "XAUUSD"},
    "XAUUSD": {"admirals": "GOLD", "icmarkets": "XAUUSD"},
    "EURUSD": {"admirals": "EURUSD", "icmarkets": "EURUSD"},
    "NIKKEI225": {"admirals": "[JP225]", "icmarkets": "JP225"},
    "[JP225]": {"admirals": "[JP225]", "icmarkets": "JP225"},
    "JP225": {"admirals": "[JP225]", "icmarkets": "JP225"},
}


def get_contract_spec(symbol: str, broker: str = "admirals") -> ContractSpec:
    """Devuelve la especificación auditada del símbolo para el bróker indicado ('admirals' o 'icmarkets').
    
    Lanza KeyError si no existe.
    """
    clean = symbol.strip().upper()
    b = broker.strip().lower()

    if b == "icmarkets":
        if clean in ICMARKETS_SPECS:
            return ICMARKETS_SPECS[clean]
        if clean in SYMBOL_ALIASES and "icmarkets" in SYMBOL_ALIASES[clean]:
            target_sym = SYMBOL_ALIASES[clean]["icmarkets"]
            if target_sym in ICMARKETS_SPECS:
                return ICMARKETS_SPECS[target_sym]
        for key, spec in ICMARKETS_SPECS.items():
            if key.replace("[", "").replace("]", "").upper() == clean.replace("[", "").replace("]", ""):
                return spec
        raise KeyError(f"Símbolo no configurado en ICMARKETS_SPECS: {symbol}")

    # Admirals por defecto
    if clean in ADMIRALS_SPECS:
        return ADMIRALS_SPECS[clean]
    if clean in SYMBOL_ALIASES and "admirals" in SYMBOL_ALIASES[clean]:
        target_sym = SYMBOL_ALIASES[clean]["admirals"]
        if target_sym in ADMIRALS_SPECS:
            return ADMIRALS_SPECS[target_sym]
    for key, spec in ADMIRALS_SPECS.items():
        if key.replace("[", "").replace("]", "").upper() == clean.replace("[", "").replace("]", ""):
            return spec
    if clean in ICMARKETS_SPECS:
        return ICMARKETS_SPECS[clean]
    raise KeyError(f"Símbolo no configurado en contract_specs: {symbol}")


def calculate_commission(
    spec: ContractSpec,
    lots: float,
    eurusd_rate: float = 1.12,
    account_currency: str = "EUR"
) -> float:
    """Calcula la comisión contractual del bróker en divisa de cuenta.
    
    En Forex Raw Spread (ej. IC Markets): $7.00 USD por lote round-trip -> convertido a EUR.
    En Índices CFDs: 0.0 EUR (spread puro).
    """
    if lots <= 0 or spec.commission_per_lot <= 0:
        return 0.0
    comm_usd = lots * spec.commission_per_lot
    acc_ccy = account_currency.upper()
    if acc_ccy == "EUR":
        return comm_usd / eurusd_rate
    elif acc_ccy == "USD":
        return comm_usd
    return comm_usd / eurusd_rate


def calculate_lot_size(
    spec: ContractSpec,
    account_equity: float,
    risk_fraction: float,
    stop_distance_price: float,
    entry_price: float,
    eurusd_rate: float = 1.12,
    leverage: float = 100.0,
    account_currency: str = "EUR",
) -> LotCalculationResult:
    """Calcula el tamaño de lote exacto asegurando no rebasar el presupuesto de riesgo.
    
    Aplica redondeo hacia ABAJO a múltiplo de lot_step y rechazo si lots < lot_min.
    """
    if account_equity <= 0 or not 0 < risk_fraction <= 0.05:
        return LotCalculationResult(
            status="REJECTED_INVALID_INPUT", lots=0.0, raw_lots=0.0,
            risk_budget_account_ccy=0.0, actual_risk_account_ccy=0.0,
            stop_distance_price=stop_distance_price, stop_distance_points=0.0,
            required_margin_account_ccy=0.0, reason="Capital negativo o fracción de riesgo fuera de límites (0, 0.05]"
        )

    if stop_distance_price <= 0 or entry_price <= 0 or eurusd_rate <= 0 or leverage <= 0:
        return LotCalculationResult(
            status="REJECTED_INVALID_INPUT", lots=0.0, raw_lots=0.0,
            risk_budget_account_ccy=0.0, actual_risk_account_ccy=0.0,
            stop_distance_price=stop_distance_price, stop_distance_points=0.0,
            required_margin_account_ccy=0.0, reason="Precios, distancias o apalancamiento no positivos"
        )

    stop_distance_points = stop_distance_price / spec.point

    # Validación de stops_level_points del broker
    if stop_distance_points < spec.stops_level_points:
        return LotCalculationResult(
            status="REJECTED_STOPS_LEVEL", lots=0.0, raw_lots=0.0,
            risk_budget_account_ccy=account_equity * risk_fraction,
            actual_risk_account_ccy=0.0, stop_distance_price=stop_distance_price,
            stop_distance_points=stop_distance_points, required_margin_account_ccy=0.0,
            reason=f"Distancia al SL ({stop_distance_points:.1f} pts) es inferior a stops_level ({spec.stops_level_points} pts)"
        )

    risk_budget_acc_ccy = account_equity * risk_fraction
    point_val_acc_ccy = spec.point_value_in_account_currency(eurusd_rate, account_currency)
    
    # Pérdida en divisa de cuenta por cada 1.0 lote si salta el SL
    loss_per_lot_acc_ccy = stop_distance_points * point_val_acc_ccy
    if loss_per_lot_acc_ccy <= 0:
        return LotCalculationResult(
            status="REJECTED_INVALID_INPUT", lots=0.0, raw_lots=0.0,
            risk_budget_account_ccy=risk_budget_acc_ccy, actual_risk_account_ccy=0.0,
            stop_distance_price=stop_distance_price, stop_distance_points=stop_distance_points,
            required_margin_account_ccy=0.0, reason="Pérdida por lote nula o negativa"
        )

    raw_lots = risk_budget_acc_ccy / loss_per_lot_acc_ccy

    # Redondeo estricto hacia ABAJO al múltiplo de lot_step
    steps = math.floor((raw_lots / spec.lot_step) + 1e-12)
    lots = steps * spec.lot_step
    
    # Preservar decimales según step (ej. 0.01 -> 2 decimales, 0.1 -> 1 decimal)
    step_decimals = max(0, -int(math.floor(math.log10(spec.lot_step) + 1e-9)))
    lots = round(lots, step_decimals)

    if lots < spec.lot_min:
        return LotCalculationResult(
            status="REJECTED_BELOW_MIN_LOT", lots=0.0, raw_lots=raw_lots,
            risk_budget_account_ccy=risk_budget_acc_ccy, actual_risk_account_ccy=0.0,
            stop_distance_price=stop_distance_price, stop_distance_points=stop_distance_points,
            required_margin_account_ccy=0.0,
            reason=f"Lote calculado ({raw_lots:.4f}) es inferior al mínimo permitido por el bróker ({spec.lot_min})"
        )

    if lots > spec.lot_max:
        lots = spec.lot_max

    actual_risk_acc_ccy = lots * loss_per_lot_acc_ccy

    # Estimación de margen requerido
    margin_acc_ccy = estimate_margin(spec, lots, entry_price, leverage, eurusd_rate, account_currency)

    return LotCalculationResult(
        status="OK",
        lots=lots,
        raw_lots=raw_lots,
        risk_budget_account_ccy=round(risk_budget_acc_ccy, 4),
        actual_risk_account_ccy=round(actual_risk_acc_ccy, 4),
        stop_distance_price=stop_distance_price,
        stop_distance_points=round(stop_distance_points, 2),
        required_margin_account_ccy=round(margin_acc_ccy, 2),
        reason="Lote calculado cumpliendo límites de riesgo y granularidad del bróker"
    )


def estimate_margin(
    spec: ContractSpec,
    lots: float,
    entry_price: float,
    leverage: float = 100.0,
    eurusd_rate: float = 1.12,
    account_currency: str = "EUR"
) -> float:
    """Estima el margen requerido en divisa de cuenta."""
    if lots <= 0 or entry_price <= 0 or leverage <= 0 or eurusd_rate <= 0:
        return 0.0

    notional_trade_ccy = lots * entry_price * spec.contract_size

    # Conversión a divisa de margen / cuenta
    if spec.margin_currency == "EUR" or (spec.margin_currency == "USD" and account_currency == "USD"):
        notional_acc_ccy = notional_trade_ccy
    elif spec.margin_currency == "USD" and account_currency == "EUR":
        notional_acc_ccy = notional_trade_ccy / eurusd_rate
    elif spec.margin_currency == "EUR" and account_currency == "USD":
        notional_acc_ccy = notional_trade_ccy * eurusd_rate
    else:
        notional_acc_ccy = notional_trade_ccy / eurusd_rate

    return notional_acc_ccy / leverage


def calculate_overnight_swap(
    spec: ContractSpec,
    direction: Literal[1, -1],
    nights: int,
    lots: float,
    close_price: float,
    eurusd_rate: float = 1.12,
    account_currency: str = "EUR"
) -> float:
    """Calcula el swap aproximado devengado en divisa de cuenta.
    
    direction: +1 para LONG, -1 para SHORT.
    Devuelve un valor que suele ser negativo (coste para el trader).
    """
    if nights <= 0 or lots <= 0 or close_price <= 0:
        return 0.0

    raw_rate = spec.swap_long if direction == 1 else spec.swap_short

    # Modo 5: SWAP_BY_INTEREST_CURRENT (tasa anual en %)
    if spec.swap_mode == 5:
        notional_base = lots * close_price * spec.contract_size
        daily_swap_profit_ccy = notional_base * (raw_rate / 100.0) / 360.0 * nights
        if spec.profit_currency == "USD" and account_currency == "EUR":
            return daily_swap_profit_ccy / eurusd_rate
        return daily_swap_profit_ccy

    # Modo 0 o 1: SWAP_BY_POINTS
    point_val = spec.point_value_in_account_currency(eurusd_rate, account_currency)
    return raw_rate * point_val * lots * nights
