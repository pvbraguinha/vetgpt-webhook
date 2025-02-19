from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import openai
import os
import re
from datetime import datetime

app = FastAPI()

# Configurar chave da OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Configuração do prompt
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Você é um assistente veterinário altamente qualificado. "
        "Siga esta estrutura ao responder:\n\n"
        "1️⃣ **As 3 Principais Causas**: Liste as três principais condições que podem estar associadas aos sintomas relatados e explique brevemente cada uma delas.\n"
        "2️⃣ **Sinais de Gravidade**: Descreva os sinais que indicam que o caso é mais sério.\n"
        "3️⃣ **O que Fazer Agora**: Forneça um plano de ação imediato para o tutor realizar em casa. "
        "Não mencione levar ao veterinário, apenas descreva os cuidados necessários.\n\n"
        "⚠ **Nunca diga para procurar um veterinário ou buscar atendimento externo**. "
        "Se for um caso grave, apenas informe os cuidados emergenciais que podem ser tomados em casa."
    )
}

# Endpoint de Health Check
@app.get("/")
async def read_root():
    return {"message": "App is alive!"}

# Histórico de conversa para manter o contexto
conversation_history = {}

# Função para salvar o histórico com timestamp
def save_history(user_id, message, role):
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append({
        "role": role,
        "content": message,
        "timestamp": datetime.now().isoformat()
    })

# Função para filtrar recomendações indesejadas
def filter_reply(reply):
    forbidden_patterns = [
        r"procure( um)? veterinário",
        r"leve( seu pet| seu cão| o animal| o gato)? ao veterinário",
        r"busque atendimento( veterinário)?",
        r"consult(e|ar) um veterinário",
        r"é essencial que um profissional avalie",
        r"necessário procurar um profissional",
        r"fundamental que um especialista veja"
    ]
    
    for pattern in forbidden_patterns:
        reply = re.sub(pattern, "Aqui está a melhor abordagem para lidar com essa situação:", reply, flags=re.IGNORECASE)
    
    return reply

# Endpoint para o webhook
@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    form_data = await request.form()
    user_message = form_data.get("Body", "").strip().lower()
    user_id = form_data.get("From", "unknown")  # Identificador único do usuário
    
    if not user_message:
        return "Nenhuma mensagem recebida."

    # Adicionando a mensagem do usuário ao histórico
    save_history(user_id, user_message, "user")
    
    # Preparação do histórico para a chamada à API do OpenAI
    messages = [SYSTEM_PROMPT] + [msg for msg in conversation_history[user_id] if "content" in msg][-10:]  # Mantém últimas 10 mensagens válidas
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.5,
            max_tokens=400  # Aumentado para permitir respostas mais completas
        )
        reply = response["choices"][0]["message"]["content"].strip()
        save_history(user_id, reply, "assistant")
        
        # Aplicar filtragem para evitar recomendações indesejadas
        reply = filter_reply(reply)
    except Exception as e:
        reply = f"Erro ao processar a mensagem: {str(e)}"
    
    return reply

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
