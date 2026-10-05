import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # lee el archivo .env

# El "mesero": sabe a qué restaurante ir y con qué tarjeta de socio
client = OpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url=os.getenv("QWEN_BASE_URL"),
)

# El "pedido": un mensaje de sistema (el rol) y uno de usuario (tu pregunta)
respuesta = client.chat.completions.create(
    model=os.getenv("QWEN_MODEL"),
    messages=[
        {"role": "system", "content": "Eres un director deportivo de fútbol. Responde en una frase."},
        {"role": "user", "content": "Hola, preséntate."},
    ],
)

print(respuesta.choices[0].message.content)