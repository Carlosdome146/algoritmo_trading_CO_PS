"""
Diagnostic Script: Tests connection to MetaTrader 5 and inspects account info & symbols
"""

import MetaTrader5 as mt5

def check_connection():
    print("=" * 60)
    print("COMPROBACIÓN DE CONEXIÓN CON METATRADER 5")
    print("=" * 60)

    # Initialize connection to MT5
    if not mt5.initialize():
        print(f"[!] Error al inicializar MT5: {mt5.last_error()}")
        print("Asegúrate de que MetaTrader 5 esté abierto en tu ordenador.")
        return False

    print("[+] Conectado con éxito a MetaTrader 5!")
    
    # Terminal info
    term_info = mt5.terminal_info()
    if term_info:
        print(f"    Terminal: {term_info.name} (Build: {term_info.build})")
        print(f"    Ruta: {term_info.path}")
        print(f"    Trading automatizado permitido: {term_info.trade_allowed}")

    # Account info
    acc_info = mt5.account_info()
    if acc_info:
        print("\n[+] INFORMACIÓN DE LA CUENTA:")
        print(f"    Login (Cuenta): {acc_info.login}")
        print(f"    Servidor / Broker: {acc_info.server}")
        print(f"    Moneda: {acc_info.currency}")
        print(f"    Balance: {acc_info.balance:.2f} {acc_info.currency}")
        print(f"    Equidad: {acc_info.equity:.2f} {acc_info.currency}")
        print(f"    Apalancamiento: 1:{acc_info.leverage}")
        print(f"    Modo DEMO: {'SÍ' if acc_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else 'NO (REAL)'}")

    # Search for DAX symbols
    print("\n[+] BUSCANDO SÍMBOLOS DEL DAX 40 EN TU BROKER:")
    symbols = mt5.symbols_get()
    dax_candidates = []
    
    if symbols:
        for s in symbols:
            name_upper = s.name.upper()
            if any(term in name_upper for term in ["DAX", "DE40", "GER40", "GERMANY"]):
                dax_candidates.append(s.name)

        if dax_candidates:
            print(f"    Símbolos encontrados relacionados con DAX: {dax_candidates[:10]}")
        else:
            print("    [i] No se encontraron símbolos con el nombre DAX/GER40 directamente visible.")
            print("    (Podemos buscar en los símbolos disponibles del broker)")

    mt5.shutdown()
    return True

if __name__ == "__main__":
    check_connection()
