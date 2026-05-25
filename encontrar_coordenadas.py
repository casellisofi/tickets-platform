"""
Mini utilidad para encontrar coordenadas en pantalla.
Mostra X,Y del mouse en tiempo real. Ctrl+C para salir.

USO:
  1. Abri WhatsApp Web en el navegador, abierto en un chat cualquiera.
  2. Corre este script: python encontrar_coordenadas.py
  3. Llevá el mouse al icono del CLIP (📎) sin clickear y anota X,Y.
  4. Después llevá el mouse a la opción "Documento" del menú que aparece
     al hacer click en el clip (tenés que abrirlo primero a mano), anota X,Y.
"""
import pyautogui
import time

print("Mové el mouse al ícono del CLIP 📎 de WhatsApp Web.")
print("Cuando esté apuntando bien, anotá el X,Y que ves abajo.")
print("Después hacé lo mismo con la opción 'Documento' del menú.")
print("Ctrl+C para salir.\n")

try:
    while True:
        x, y = pyautogui.position()
        print(f"\rX: {x:4d}   Y: {y:4d}   ", end="", flush=True)
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nListo.")
