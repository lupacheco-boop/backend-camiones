import time
import requests
import random

# Dirección de tu servidor local
URL = "http://127.0.0.1:8000/trucks"

def simular():
    print("Iniciando simulador de odómetro...")
    while True:
        try:
            # Obtener los camiones
            response = requests.get(URL)
            if response.status_code == 200:
                camiones = response.json()
                # Tomamos un camión al azar para simular que avanza
                camion = random.choice(camiones)
                id_camion = camion.get('id')
                km_actual = camion.get('kilometraje_actual', 0)
                
                # Le sumamos entre 10 y 50 km
                nuevos_km = km_actual + random.randint(10, 50)
                
                # Actualizar en el servidor
                update_url = f"{URL}/{id_camion}"
                requests.put(update_url, json={"kilometraje_actual": nuevos_km})
                print(f"🚛 Camión {camion.get('placa')} avanzó a {nuevos_km} km")
                
        except Exception as e:
            print(f"Error: {e}")
        
        # Esperar 5 segundos antes de la siguiente simulación
        time.sleep(5)

if __name__ == "__main__":
    simular()