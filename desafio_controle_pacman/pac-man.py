import asyncio
import websockets
import pygame
import json

# --- CONFIGURACOES DE REDE ---
# IP do ROBO (Recebe comandos de motor)
URI_ROBO = "ws://192.168.1.116:81"

# IP do SERVIDOR DO JOGO (Envia status de power up/game over)
URI_GAME_SERVER = "ws://127.0.0.1:8765" 

# --- CONFIGURACOES DE CONTROLE ---
TAXA_ENVIO = 0.05    # 20 mensagens por segundo (20Hz)
DEADZONE = 0.15      # Zona morta do analogico
SUAVIDADE = 0.3      # Inercia (0.1 = pesado ... 1.0 = instantaneo)

# --- VELOCIDADES ---
SPEED_NORMAL = 150
SPEED_BOOST = 255    # Velocidade quando Power Up esta ativo

# --- ESTADO GLOBAL COMPARTILHADO ---
class EstadoGlobal:
    def __init__(self):
        self.max_speed = SPEED_NORMAL  # Comeca em 150
        self.power_active = False      # Controle de estado
        self.game_over = False         # Se True, para o robo
        self.rodando = True            # Controle geral do script

estado = EstadoGlobal()

# --- INICIALIZACAO JOYSTICK ---
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("[ERRO] Nenhum controle detectado. Conecte e reinicie.")
    exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()
print(f"[SISTEMA] Controle conectado: {joystick.get_name()}")

# --- FUNCOES MATEMATICAS ---

def interpolar(atual, alvo, fator):
    return atual + (alvo - atual) * fator

def calcular_motores(velocidade_limite):
    pygame.event.pump()
    
    # 1. Leitura dos Botoes (A e B)
    # Acelera para frente (A) ou tras (B)
    btn_a = joystick.get_button(0)
    btn_b = joystick.get_button(1)

    throttle = 0.0
    if btn_a: throttle = 1.0
    elif btn_b: throttle = -1.0

    # 2. Leitura do Analogico (Curva)
    turn = joystick.get_axis(0)
    if abs(turn) < DEADZONE: turn = 0.0
    
    # Aplica curva exponencial para suavizar a direcao
    turn = turn * abs(turn)

    # 3. Mistura (Arcade Drive)
    left = throttle + turn
    right = throttle - turn

    # 4. Normalizacao (Se a soma passar de 1.0, reduz proporcionalmente)
    maior = max(abs(left), abs(right))
    if maior > 1.0:
        left /= maior
        right /= maior

    # 5. Calculo final PWM
    m1 = int(left * velocidade_limite)
    m2 = int(right * velocidade_limite)

    return m1, m2

# ====================================================================
# OUVIR SERVIDOR DO JOGO (Game Server)
# ====================================================================
async def conectar_game_server():
    print(f"[GAME] Tentando conectar ao servidor do jogo: {URI_GAME_SERVER}")
    
    while estado.rodando:
        try:
            async with websockets.connect(URI_GAME_SERVER) as ws:
                print("[GAME] Conectado ao Servidor do Jogo.")
                
                async for message in ws:
                    try:
                        data = json.loads(message)
                        status = data.get("estado_jogo", data)
                        power_now = status.get("power_active", False)
                        
                        if power_now and not estado.power_active:
                            print(f"[GAME] POWER UP ATIVADO! Velocidade ajustada para {SPEED_BOOST}")
                            estado.power_active = True
                            estado.max_speed = SPEED_BOOST
                        
                        elif not power_now and estado.power_active:
                            print(f"[GAME] Power Up finalizado. Velocidade retornou a {SPEED_NORMAL}")
                            estado.power_active = False
                            estado.max_speed = SPEED_NORMAL

                        # --- DETECTAR GAME OVER ---
                        if status.get("game_over", False):
                            if not estado.game_over:
                                print("[GAME] GAME OVER RECEBIDO. Parando motores.")
                                estado.game_over = True
                    
                    except json.JSONDecodeError:
                        pass
        
        except (ConnectionRefusedError, OSError):
            print("[GAME] Falha ao conectar no jogo. Tentando novamente em 3s...", end="\r")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"[GAME] Erro: {e}")
            await asyncio.sleep(1)

# ====================================================================
# CONTROLAR ROBO (Firmware)
# ====================================================================
async def conectar_robo():
    print(f"[ROBO] Tentando conectar ao firmware: {URI_ROBO}")
    m1_atual, m2_atual = 0.0, 0.0

    while estado.rodando:
        try:
            async with websockets.connect(URI_ROBO) as ws:
                print("[ROBO] Conectado ao Robo. Controle ativo.")
                
                while estado.rodando:
                    # Se estiver em Game Over, força parada
                    if estado.game_over:
                        cmd = {"motor1_vel": 0, "motor2_vel": 0}
                        await ws.send(json.dumps(cmd))
                        await asyncio.sleep(0.5)
                        continue

                    # 1. Calcula motores com a velocidade definida pelo Game Server
                    target_m1, target_m2 = calcular_motores(estado.max_speed)

                    # 2. Suavizacao (Ramping)
                    m1_atual = interpolar(m1_atual, target_m1, SUAVIDADE)
                    m2_atual = interpolar(m2_atual, target_m2, SUAVIDADE)

                    # 3. Envia comando
                    cmd = {
                        "motor1_vel": int(m1_atual),
                        "motor2_vel": int(m2_atual)
                    }
                    await ws.send(json.dumps(cmd))

                    # Log no terminal (sobrescreve a linha para nao poluir)
                    status_txt = "BOOST" if estado.power_active else "NORMAL"
                    print(f"[STATUS: {status_txt}] M1: {int(m1_atual):4} | M2: {int(m2_atual):4}", end="\r")

                    await asyncio.sleep(TAXA_ENVIO)

        except (ConnectionRefusedError, OSError):
            print("[ROBO] Falha ao conectar no Robo. Tentando novamente em 0.3s...", end="\r")
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f"[ROBO] Erro critico: {e}")
            await asyncio.sleep(0.3)
# ====================================================================
# LOOP PRINCIPAL
# ====================================================================
async def main():
    # Roda as duas tarefas simultaneamente
    # Se uma cair, a outra continua rodando
    await asyncio.gather(
        conectar_game_server(),
        conectar_robo()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SISTEMA] Encerrando script.")
        pygame.quit()