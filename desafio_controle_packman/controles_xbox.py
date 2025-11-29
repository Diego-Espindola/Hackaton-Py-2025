import pygame
import sys

# Inicializa o Pygame
pygame.init()
pygame.joystick.init()

# Verifica se há controles conectados
if pygame.joystick.get_count() == 0:
    print("Nenhum controle detectado!")
    sys.exit()

# Inicializa o primeiro controle detectado
controle = pygame.joystick.Joystick(0)
controle.init()

print(f"Controle conectado: {controle.get_name()}")

def mover_personagem(eixo_x, eixo_y):
    # Eixos geralmente vão de -1.0 a 1.0
    print(f">> Movendo: X={eixo_x:.2f}, Y={eixo_y:.2f}")

# --- Loop Principal ---
try:
    while True:
        # Processa todos os eventos do sistema
        for event in pygame.event.get():
            
            # Se o usuário apertar um botão (Botões A, B, X, Y, LB, RB, etc.)
            if event.type == pygame.JOYBUTTONDOWN:
                if event.button == 0: # Geralmente Botão A
                    print('botao a')
                elif event.button == 1: # Geralmente Botão B
                    print('botao b')
                # Adicione mais 'elif' para outros botões conforme necessário

            # Se o usuário mover os analógicos ou gatilhos (LT/RT)
            elif event.type == pygame.JOYAXISMOTION:
                # Eixo 0 e 1 geralmente são o Analógico Esquerdo
                # É bom colocar um "deadzone" (zona morta) para evitar movimentos fantasmas
                if abs(event.value) > 0.1: 
                    if event.axis == 0 or event.axis == 1:
                        axis_x = controle.get_axis(0)
                        axis_y = controle.get_axis(1)
                        mover_personagem(axis_x, axis_y)

            # Para sair do script (ex: CTRL+C no terminal)
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

except KeyboardInterrupt:
    print("Encerrando...")
    pygame.quit()