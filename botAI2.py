from iqoptionapi.stable_api import IQ_Option
import logging
import time
import numpy as np
import talib
import requests
import getpass

# Credenciales
usuario = input("Correo: ")
contrasena = getpass.getpass("Contraseña: ")

# Telegram
TOKEN = "7440916537:AAFin-seOCN4j6uzLMbUryXCGdgF4OItcZY"
CHAT_ID = "1628307192"

# Configuración
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
iq = IQ_Option(usuario, contrasena)
iq.connect()

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": mensaje}
    try:
        requests.post(url, data=data)
    except Exception as e:
        logging.error(f"Error al enviar mensaje a Telegram: {e}")

if iq.check_connect():
    saldo_inicial = iq.get_balance()
    enviar_telegram(f"✅ Conectado a IQ Option\n💰 Saldo inicial: ${saldo_inicial:.2f}")
    logging.info("Conectado exitosamente")
else:
    logging.error("No se pudo conectar a IQ Option")
    exit()

def get_assets():
    iq.update_ACTIVES_OPCODE()
    all_assets = iq.get_all_open_time()
    activos = [
        asset for tipo in ['binary', 'digital']
        for asset, info in all_assets.get(tipo, {}).items() if info['open']
    ]
    permitidas = ['EUR', 'USD', 'GBP', 'JPY', 'CHF', 'AUD']
    return [a for a in activos if any(p in a for p in permitidas)]

def obtener_indicadores(candles):
    closes = np.array([c['close'] for c in candles])
    if len(closes) < 50:
        return None, None, None, None, None
    upper, middle, lower = talib.BBANDS(closes, timeperiod=20)
    ema_50 = talib.EMA(closes, timeperiod=50)
    return upper[-1], middle[-1], lower[-1], closes[-1], ema_50[-1]

def detectar_senal(candles):
    if candles is None or len(candles) < 50:
        return None
    upper, _, lower, close, ema = obtener_indicadores(candles)
    if upper is None:
        return None

    # Señal por Bandas de Bollinger y EMA
    if close < lower and close > ema:
        return "CALL"
    elif close > upper and close < ema:
        return "PUT"
    return None

def confirmar_senal_30m(par, tipo):
    candles_30m = iq.get_candles(par, 1800, 60, time.time())  # 60 velas de 30m
    if len(candles_30m) < 50:
        return False

    closes = np.array([c['close'] for c in candles_30m])
    ema_50 = talib.EMA(closes, timeperiod=50)
    ema = ema_50[-1]
    vela_actual = candles_30m[-1]
    open_price = vela_actual['open']
    close_price = vela_actual['close']

    if tipo == "CALL":
        vela_verde = close_price > open_price
        precio_sobre_ema = close_price > ema
        return vela_verde and precio_sobre_ema

    elif tipo == "PUT":
        vela_roja = close_price < open_price
        precio_bajo_ema = close_price < ema
        return vela_roja and precio_bajo_ema

    return False

def check_resultado(id_op):
    while True:
        check, resultado = iq.check_win_v4(id_op)
        if check:
            return "Ganada" if resultado > 0 else "Perdida", resultado
        time.sleep(1)

entrada_base = 1
ganancia_total = 0

def operar(par, tipo):
    global ganancia_total
    entrada_actual = entrada_base
    intentos = 0
    max_intentos = 3

    while intentos < max_intentos:
        duracion = 3 if intentos == 0 else 5
        success, id_op = iq.buy(entrada_actual, par, tipo.lower(), duracion)
        if success:
            resultado, ganancia = check_resultado(id_op)
            capital = iq.get_balance()
            ganancia_total = capital - saldo_inicial

            enviar_telegram(
                f"📈 Operación #{intentos+1} ejecutada\n"
                f"🔹 Par: {par}\n"
                f"🔹 Tipo: {tipo}\n"
                f"⏳ Duración: {duracion} min\n"
                f"🔹 Resultado: {resultado}\n"
                f"🔹 $ {'+' if ganancia >= 0 else ''}{ganancia:.2f}\n"
                f"🏦 Capital actual: ${capital:.2f}\n"
                f"{'📉 Pérdida' if ganancia_total < 0 else '📈 Ganancia'} acumulada: ${ganancia_total:.2f}"
            )

            if resultado == "Ganada":
                break
            else:
                intentos += 1
                entrada_actual = round(entrada_actual * 2, 2)
                time.sleep(5)
        else:
            logging.error(f"No se pudo ejecutar operación en {par}")
            break
    else:
        enviar_telegram(f"🚫 Máximo de intentos de martingala alcanzado en {par}.")

def revisar(par):
    candles = iq.get_candles(par, 60, 60, time.time())
    if candles is None or len(candles) < 50:
        logging.warning(f"Datos de velas insuficientes para {par}")
        return

    senal = detectar_senal(candles)
    if senal:
        logging.info(f"📊 Señal en {par}: {senal}")
        if confirmar_senal_30m(par, senal):
            logging.info(f"✅ Confirmación 30m para {par}: {senal}")
            enviar_telegram(f"📡 Señal detectada\n🔹 Par: {par}\n🔹 Dirección: {senal}\n⏳ Ejecutando operación...")
            operar(par, senal)
        else:
            logging.info(f"❌ Sin confirmación 30m para {senal} en {par}")

def main():
    while True:
        activos = get_assets()
        if not activos:
            logging.warning("⚠️ No hay activos disponibles para operar.")
            time.sleep(60)
            continue

        for activo in activos:
            revisar(activo)
        time.sleep(60)

if __name__ == "__main__":
    main()
