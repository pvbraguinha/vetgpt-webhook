from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import openai
import os

app = FastAPI()

# Configurar chave da OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Configuração do prompt
SYSTEM_PROMPT = {
    "role": "system",
    "content": "Você é um assistente veterinário altamente qualificado. Responda com precisão técnica e profissional, fornecendo diagnósticos, tratamentos e orientações detalhadas, como um veterinário faria durante uma consulta presencial. Evite indicar que o tutor procure outro veterinário e forneça a melhor solução possível. Forneça recomendações claras, baseadas em sintomas e possíveis diagnósticos diferenciais. Mantenha o contexto da conversa para responder de forma coerente e contínua, evitando repetir perguntas desnecessárias. Interprete as perguntas do usuário como um veterinário faria, analisando sintomas, possíveis causas e sugerindo tratamentos adequados."
}

# Endpoint de Health Check
@app.get("/")
async def read_root():
    return {"message": "App is alive!"}

# Histórico de conversa para manter o contexto
conversation_history = {}

# Endpoint para o webhook
@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    form_data = await request.form()
    user_message = form_data.get("Body", "").strip().lower()
    user_id = form_data.get("From", "unknown")  # Identificador único do usuário
    
    if not user_message:
        return "Nenhuma mensagem recebida."
    
    if user_id not in conversation_history:
        conversation_history[user_id] = [SYSTEM_PROMPT]
    
    conversation_history[user_id].append({"role": "user", "content": user_message})
    
    # Chamada para a OpenAI mantendo o histórico
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=conversation_history[user_id],
            temperature=0.5,
            max_tokens=250
        )
        reply = response["choices"][0]["message"]["content"].strip()
        conversation_history[user_id].append({"role": "assistant", "content": reply})
        
        # Verificação para evitar sugestão de procurar um veterinário
        if "procure um veterinário" in reply.lower() or "levar ao veterinário" in reply.lower():
            reply = "Aqui está uma recomendação baseada nos sintomas apresentados: " + reply.replace("Procure um veterinário", "").replace("Levar ao veterinário", "")
    except Exception as e:
        reply = f"Erro ao processar a mensagem: {str(e)}"
    
    return reply

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
