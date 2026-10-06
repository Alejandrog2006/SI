import sys

import requests

from comprobadores import main as comprobar_servicios

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
            f"{USER_URL}/user",
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

def modify_user(new_password, token):
        response = requests.patch(
              f"{USER_URL}/user",
              headers = authorization_header(token),
              json={
                     "password" : new_password
              }
        )

        if response.status_code == 401:
              print("Invalid autentificatior or invalid token")
        elif response.status_code == 400:
               print("Password required")
        elif response.status_code == 200:
               print("Password updated successfully")
               print(response.json())
        else:
               print("Unexpected response")
               print(response.status_code)
        return response

def list_docs(uid, token):
       response = requests.get(
              f"{FILE_URL}/file/{uid}",
              headers= authorization_header(token),
       )

       if response.status_code == 401:
              print("Unauthorized user")
       elif response.status_code == 404:
              print("User not found")
       elif response.status_code == 200:
              print("Documents listed successfully")
              print(response.json())
       else:
              print("Unexpected result")
              print(response.status_code)
       return response

def modify_docs(uid, filename, content, token):
       response = requests.put(
              f"{FILE_URL}/file/{uid}/{filename}",
              headers=authorization_header(token),
              json={
                     "content" : content
              }
       )
       if response.status_code == 400:
              print("Content is required")
       elif response.status_code == 401:
              print("Unauthorized access")
       elif response.status_code == 200:
              print("Document modified successfully")
              print(response.json())
       else:
              print("Unexpected request")
              print(response.status_code)
       return response

def restore_docs(uid, filename, token = None):
       header = {}

       if token is not None:
              header = authorization_header(token)
       response = requests.get(
              f"{FILE_URL}/file/{uid}/{filename}",
              headers=header
       )

       if response.status_code == 404:
              print("Document or user not found")
       elif response.status_code == 401:
              print("Document unaccessable private")
       elif response.status_code == 200:
              print("Document returned successfully")
              print(response.json())
       else:
              print("Unexpected response")
              print(response.status_code)
       return response

def delete_docs(uid, filename, token):
       response = requests.delete(
              f"{FILE_URL}/file/{uid}/{filename}",
              headers=authorization_header(token),
       )

       if response.status_code == 401:
              print("Invalid token")
       elif response.status_code == 404:
              print("Document or user not found")
       elif response.status_code == 200:
              print("Document deleted successfully")
              print(response.json())
       else:
              print("Unexpected response")
              print(response.status_code)
       return response

def visibility_docs(uid, filename, token, public):
       response = requests.patch(
              f"{FILE_URL}/file/{uid}/{filename}",
              headers = authorization_header(token),
              json ={
                     "public" : public
              }
       )

       if response.status_code == 400:
              print("Unmatching privacity recived")
       elif response.status_code == 401:
              print("Authentification error")
       elif response.status_code == 404:
              print("Document or user not found")
       elif response.status_code == 200:
              print("Document visivility successfuly modified")
              print(response.json())
       else:
              print("Unexpected response")
              print(response.status_code)
       return response

if __name__ == "__main__":
    sys.exit(comprobar_servicios())
