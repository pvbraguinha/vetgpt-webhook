from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import openai
import os

app = FastAPI()

# Configurar a chave da OpenAI (no Railway, configure como variável OPENAI_API_KEY)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Endpoint de Health Check
@app.get("/")
async def read_root():
    return {"message": "App is alive!"}

# Endpoint para o webhook
@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    # Twilio envia os dados como form-data, então usamos request.form()
    form_data = await request.form()
    user_message = form_data.get("Body", "")
    
    if not user_message:
        return "Nenhuma mensagem recebida."

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um assistente veterinário altamente qualificado. Responda com precisão técnica e profissional, fornecendo diagnósticos, tratamentos e orientações detalhadas, como um veterinário faria durante uma consulta presencial."},
                {"role": "user", "content": user_message}
            ]
        )
        reply = response["choices"][0]["message"]["content"]
    except Exception as e:
        reply = f"Erro ao processar a mensagem: {str(e)}"
    
    return reply

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
