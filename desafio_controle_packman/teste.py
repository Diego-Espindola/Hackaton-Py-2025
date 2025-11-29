import asyncio
import websockets
import pygame
import json

# --- CONFIGURAÇÕES ---
URI = "ws://192.168.1.116:81"
DEADZONE = 0.15      # Aumentei um pouco para evitar "drift" se o controle for velho
TAXA_ENVIO = 0.05    # 20hz
STANDARD_SPEED = 150
MAX_BOOST = 255

# [NOVO] Fator de Suavidade (Inércia)
# 0.1 = Muito pesado/lento (robô desliza)
# 0.5 = Médio
# 1.0 = Instantâneo (como estava antes)
SUAVIDADE = 0.2 

# --- CONFIGURAÇÃO PYGAME ---
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("Nenhum controle detectado! Conecte o controle e reinicie.")
    exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()
print(f"Controle detectado: {joystick.get_name()}")

# --- FUNÇÕES AUXILIARES ---

def limitar_pwm(valor, maximo):
    return max(min(valor, maximo), -maximo)

def aplicar_curva(valor):
    """
    Transforma a entrada linear em exponencial.
    Isso faz com que movimentos pequenos no analógico sejam MUITO suaves,
    mas ainda permite velocidade total se empurrar até o fim.
    Matemática: valor * |valor| (preserva o sinal)
    """
    return valor * abs(valor)

def interpolar(atual, alvo, fator):
    """
    Técnica de 'Linear Interpolation' (Lerp) para criar inércia.
    O valor atual tenta alcançar o alvo aos poucos.
    """
    return atual + (alvo - atual) * fator

def calcular_alvo_motores():
    pygame.event.pump()

    # Leitura Bruta
    raw_throttle = -joystick.get_axis(1)  # Analógico Y (cima/baixo)
    raw_turn = joystick.get_axis(0)       # Analógico X (esquerda/direita)

    # 1. Aplica Deadzone
    if abs(raw_throttle) < DEADZONE: raw_throttle = 0
    if abs(raw_turn) < DEADZONE: raw_turn = 0

    # 2. Aplica Curva Exponencial
    turn = aplicar_curva(raw_turn) * 0.7


    # Botões: A acelera, B ré/freia
    acelerar = joystick.get_button(5)  # RT
    re = joystick.get_button(2)        # LT

    dpad = joystick.get_hat(0)  # Retorna (x, y)
    print(f"D-Pad: {dpad}")
    # Boost
    modo_boost = False # IMPLEMENTAR NO FUTURO
    velocidade_max = MAX_BOOST if modo_boost else STANDARD_SPEED

    # Se apertar A ou B, ignora analógico Y e envia aceleração máxima
    if acelerar:
        throttle = 1.0  # Máxima para frente
    elif re:
        throttle = -1.0 # Máxima para trás
    else:
        throttle = 0.0

    if throttle != 0:
        # Acelerando: giro só reduz velocidade de uma roda (invertido)
        motor_esq_target = throttle * velocidade_max * (1.0 + min(0, turn))
        motor_dir_target = throttle * velocidade_max * (1.0 - max(0, turn))
    else:
        # Só girando: rodas opostas (invertido)
        motor_esq_target = -turn * velocidade_max
        motor_dir_target = turn * velocidade_max

    # Limita ao máximo permitido antes de retornar
    motor_esq_target = limitar_pwm(motor_esq_target, velocidade_max)
    motor_dir_target = limitar_pwm(motor_dir_target, velocidade_max)

    return motor_esq_target, motor_dir_target

# --- LOOP ASSÍNCRONO PRINCIPAL ---

async def rodar_controle():
    print(f"Conectando a {URI}...")

    # Variáveis de estado para a suavização (Inércia)
    m1_atual = 0.0
    m2_atual = 0.0

    while True:
        try:
            async with websockets.connect(URI) as websocket:
                print("Conectado! Controle Suavizado Ativo.")

                # Variáveis para evitar envio repetido
                ultimo_m1 = None
                ultimo_m2 = None

                while True:
                    # 1. Calcula onde queremos chegar (Target)
                    alvo_m1, alvo_m2 = calcular_alvo_motores()

                    # 2. [NOVO] Calcula o passo intermediário (Suavização)
                    m1_atual = interpolar(m1_atual, alvo_m1, SUAVIDADE)
                    m2_atual = interpolar(m2_atual, alvo_m2, SUAVIDADE)

                    # Arredonda para inteiro para enviar no JSON
                    m1_int = int(m1_atual)
                    m2_int = int(m2_atual)

                    # Só envia se mudou ou se não for ambos zero
                    if (m1_int != ultimo_m1 or m2_int != ultimo_m2) or (m1_int != 0 or m2_int != 0):
                        comando = {
                            "motor1_vel": m1_int,
                            "motor2_vel": m2_int
                        }
                        mensagem_json = json.dumps(comando)
                        await websocket.send(mensagem_json)
                        ultimo_m1 = m1_int
                        ultimo_m2 = m2_int

                    await asyncio.sleep(TAXA_ENVIO)

        except websockets.exceptions.ConnectionClosed:
            print("Conexão fechada. Tentando reconectar...")
            await asyncio.sleep(0.5)  # Espera curta antes de tentar reconectar
        except KeyboardInterrupt:
            print("\nParando...")
            break
        except Exception as e:
            print(f"Erro inesperado: {e}. Tentando reconectar...")
            await asyncio.sleep(0.5)
    pygame.quit()

if __name__ == "__main__":
    try:
        asyncio.run(rodar_controle())
    except KeyboardInterrupt:
        pass