import sys

import requests

USER_URL = "http://localhost:5050"
FILE_URL = "http://localhost:5051"

def authorization_header(token):
       return {
          "Authorization": f"Bearer {token}"
      }
def create_user(name, password):
    response = requests.put(
          f"{USER_URL}/user",
          json={
              "name": name,
              "password": password
          }
      )
    if response.status_code == 400:
        print("Datos incompletos")
    elif response.status_code == 409:
            print("Usuario duplicado")
    elif response.status_code == 201:
            print("Usuario Creado correctamente: ")
            print(response.json())
    else:
           print("Respuesta inesperada")
           print(response.status_code)
    return response

def login(name, password):
    response = requests.post(
            f"{USER_URL}/user/login",
            json={
                "name" : name,
                "password" : password
            }
    )

    if response.status_code == 400:
            print("No name or password given")
    elif response.status_code == 401:
            print("Invalid credentials")
    elif response.status_code == 200:
            print("Succesfull login")
            print(response.json())
    else:
           print("Respuesta inesperada")
           print(response.status_code)
    return response

if __name__ == "__main__":
    sys.exit(comprobar_servicios())
